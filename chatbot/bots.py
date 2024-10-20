import asyncio
import os
import logging, openai
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from chatbot.models import FAQ, UserQuery, FAQLearning
from asgiref.sync import sync_to_async
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from aiogram.filters import Command, StateFilter

# Настроим логирование
logging.basicConfig(level=logging.INFO)

bot = Bot(token=os.getenv('BOT_TOKEN'))
dp = Dispatcher(storage=MemoryStorage())

class FAQStates(StatesGroup):
    awaiting_clarification = State()  # Ожидание выбора пользователя



@sync_to_async
def search_faq_with_postgres(query):
    try:
        search_query = SearchQuery(query)
        faqs = FAQ.objects.annotate(
            rank=SearchRank(SearchVector('question'), search_query)
        ).filter(rank__gte=0.1).order_by('-rank')
        return list(faqs)
    except Exception as e:
        logging.error(f"Error while searching FAQ: {e}")
        return []



@sync_to_async
def search_faq_or_chatgpt(query):
    try:
        faqs = FAQ.objects.filter(question__icontains=query)
        if faqs.exists():
            return faqs.first().answer
        return None
    except Exception as e:
        logging.error(f"Error while searching FAQ: {e}")
        return None



# Форматирование вариантов с нумерацией
def format_faq_list(faqs):
    return "\n".join([f"{i + 1}. {faq.question}" for i, faq in enumerate(faqs)])



# Обработка сообщений
async def handle_message(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    query = message.text

    if query == '/start':
        await message.answer("Привет! Чем могу помочь?")
        return

    previous_query = await sync_to_async(UserQuery.objects.filter(user_id=user_id).order_by('-created_at').first)()
    await bot.send_chat_action(message.chat.id, action="typing")

    try:
        faq_answer = await search_faq_or_chatgpt(query)
        similar_faqs = await search_faq_with_postgres(query)

        if faq_answer:
            await message.answer(faq_answer)
            await sync_to_async(UserQuery.objects.create)(
                user_id=user_id, query=query, response=faq_answer, parent=previous_query
            )
        else:
            if similar_faqs:
                # Отправляем список вариантов с нумерацией
                faq_list = format_faq_list(similar_faqs)
                await message.answer(f"Я нашел несколько вариантов:\n\n{faq_list}")

                keyboard = InlineKeyboardMarkup(row_width=3,inline_keyboard=[])  # Устанавливаем максимальное количество кнопок в строке

                # Формируем кнопки и добавляем их в группы по 3
                buttons = [
                    InlineKeyboardButton(text=str(i + 1), callback_data=f"faq_{faq.id}")
                    for i, faq in enumerate(similar_faqs)
                ]

                # Группируем кнопки по 3 в строке
                for i in range(0, len(buttons), 3):
                    keyboard.inline_keyboard.append(buttons[i:i + 3])  # Добавляем группы кнопок по 3


                await message.answer(
                    "Выберите один или несколько вариантов:", reply_markup=keyboard
                )

                # Сохраняем варианты в состоянии
                await state.update_data(faq_options={faq.id: faq.question for faq in similar_faqs})
                await state.set_state(FAQStates.awaiting_clarification)

            else:
                old_query = await state.get_data()
                try:
                    query = old_query['faq_options'][query]
                    faq_answer = await search_faq_or_chatgpt(query)
                    if faq_answer:
                        await message.answer(faq_answer)
                        await sync_to_async(UserQuery.objects.create)(
                            user_id=user_id, query=query, response=faq_answer, parent=previous_query
                        )
                except Exception as e:
                    chatgpt_answer = await asyncio.wait_for(get_chatgpt_response(user_id,query), timeout=15.0)
                    await message.answer(chatgpt_answer)
                    await sync_to_async(UserQuery.objects.create)(
                        user_id=user_id, query=query, response=chatgpt_answer
                    )
                    await sync_to_async(FAQLearning.objects.create)(
                        question=query, answer=chatgpt_answer
                    )
    except asyncio.TimeoutError:
        await message.answer("Произошла задержка при получении ответа. Пожалуйста, попробуйте позже.")
    except Exception as e:
        logging.error(f"Error while handling message: {e}")
        await message.answer("Произошла ошибка при обработке вашего запроса.")



# Обработка выбора кнопки
@dp.callback_query(StateFilter(FAQStates.awaiting_clarification))
async def process_faq_selection(callback_query: types.CallbackQuery, state: FSMContext):
    faq_id = int(callback_query.data.split('_')[1])
    selected_faq = await sync_to_async(FAQ.objects.get)(id=faq_id)

    await callback_query.message.answer(selected_faq.answer)

    # Сохраняем выбор
    # await state.clear()

# Регистрация обработчиков
dp.message.register(handle_message, Command(commands=["start"]))
dp.message.register(handle_message)



client = openai.AsyncOpenAI(api_key=os.getenv('CHAT_GPT_API_KEY'))
content = '''
GPT должен отвечать только на те вопросы которые связаны с компанией Dexfreedom,Dexnet.one,Dexsafe,Dexcard,DexMobile,Dexnoda, 
ты должен отвечать как консультант и искать максимально похожие вопросы у себя на базе и задавать уточняющие вопросы. 
Все сторонние вопросы не должен отвечать ничего кроме "Я не могу ответить на вопрос".
'''


@sync_to_async
def get_user_conversation(user_id, limit=5):
    return list(UserQuery.objects.filter(user_id=user_id).order_by('-created_at')[:limit])



# Формирование контекста для запроса в ChatGPT
async def build_context(user_id):
    messages = await get_user_conversation(user_id)
    context = [{"role": "system", "content": content}]
    for message in reversed(messages):
        context.append({"role": "user", "content": message.query})
        context.append({"role": "assistant", "content": message.response})
    return context



# Основная функция для обработки запроса к ChatGPT и поиска в файлах
async def get_chatgpt_response(user_id, query):
    assistant_id = os.getenv('ASSISTANT_ID')
    try:
        # Формируем контекст из предыдущих сообщений
        context = await build_context(user_id)
        context.append({"role": "user", "content": query})

        # Добавляем системное сообщение для идентификации ассистента
        system_message = {
            "role": "system",
            "content": f"Вы используете ассистента с ID: {assistant_id}. {content}"
        }
        context.insert(0, system_message)


        # Отправляем запрос в OpenAI API с настройкой ассистента
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=context,
            stream=True  # Включаем потоковый режим
        )

        response_text = ""

        # Обрабатываем потоковый ответ
        async for chunk in response:
            try:
                content_chunk = chunk.choices[0].delta.content  # Явный доступ к атрибуту
            except AttributeError:
                logging.error(f"Ошибка при обработке фрагмента: {chunk}")
                continue  # Пропускаем фрагмент, если он некорректный

            if content_chunk:
                response_text += content_chunk

        # Проверяем, что ответ не пустой
        if not response_text.strip():
            warning_msg = "Ответ от ассистента пустой."
            return warning_msg

        return response_text

    except Exception as e:
        error_msg = f"Ошибка при запросе к ассистенту {assistant_id}: {str(e)}"
        logging.error(error_msg)
        return f"Извините, произошла ошибка: {error_msg}"



async def start_bot():
    await dp.start_polling(bot)


