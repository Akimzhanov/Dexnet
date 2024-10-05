import asyncio, os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from chatbot.models import FAQ, UserQuery, FAQLearning
import openai
from openai import AsyncOpenAI
from django.conf import settings
from asgiref.sync import sync_to_async
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from aiogram.filters import Command  # Фильтр для команд

# Настроим логирование
logging.basicConfig(level=logging.INFO)

bot = Bot(token=os.getenv('BOT_TOKEN'))
dp = Dispatcher(storage=MemoryStorage())

openai.api_key = os.getenv('CHAT_GPT_API_KEY')

# Состояния FSM для бота
class FAQStates(StatesGroup):
    awaiting_clarification = State()  # Ожидание выбора пользователя

# Поиск по базе данных с использованием полнотекстового поиска PostgreSQL
@sync_to_async
def search_faq_with_postgres(query):
    try:
        search_query = SearchQuery(query)
        faqs = FAQ.objects.annotate(
            rank=SearchRank(SearchVector('question'), search_query)
        ).filter(rank__gte=0.1).order_by('-rank')  # Отфильтруем по рангу и отсортируем
        return list(faqs)  # Приводим к списку для удобства обработки
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

# Обработка сообщений
async def handle_message(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    query = message.text

    # Если команда /start, игнорируем сохранение
    if query == '/start':
        await message.answer("Привет! Чем могу помочь?")
        return

    # Получаем предыдущий запрос пользователя, если он есть
    previous_query = await sync_to_async(UserQuery.objects.filter(user_id=user_id).order_by('-created_at').first)()
    # Показываем, что бот "печатает"
    await bot.send_chat_action(message.chat.id, action="typing")
    
    try:

        faq_answer = await search_faq_or_chatgpt(query)  # Используем await для асинхронного вызова
        similar_faqs = await search_faq_with_postgres(query)  # Используем асинхронный вызов для поиска схожих вопросов
        if faq_answer:
            await message.answer(faq_answer)
            # Сохраняем новый запрос и связываем с предыдущим
            await sync_to_async(UserQuery.objects.create)(user_id=user_id, query=query, response=faq_answer, parent=previous_query)
        else:        
            if similar_faqs:
                if len(similar_faqs) > 1:
                    # Создаем словарь для сопоставления опций с вопросами
                    faq_options = {str(i+1): faq for i, faq in enumerate(similar_faqs)}
                    # Генерируем строку для отправки пользователю
                    options = "\n".join([f"{key}. {value.question}" for key, value in faq_options.items()])
                    await message.answer(f"Я нашел несколько вариантов, уточните, пожалуйста:\n{options}")
                    
                    # Сохраняем список схожих вопросов как словарь и активируем состояние ожидания выбора
                    await state.update_data(faq_options=faq_options)
                    await state.set_state(FAQStates.awaiting_clarification)
                # else:
                    # # Если найден только один похожий вопрос, отвечаем сразу
                    # faq_answer = similar_faqs[0].answer
                    # await message.answer(faq_answer)
                    # # Сохраняем новый запрос и связываем с предыдущим
                    # await sync_to_async(UserQuery.objects.create)(user_id=user_id, query=query, response=faq_answer)
            else:
                # Если похожих вопросов нет, отправляем запрос к ChatGPT
                old_query = await state.get_data()
                
                try:
                    query = old_query['faq_options'][query]
                    faq_answer = await search_faq_or_chatgpt(query)  # Используем await для асинхронного вызова
                    
                    if faq_answer:
                        await message.answer(faq_answer)
                        # Сохраняем новый запрос и связываем с предыдущим
                        await sync_to_async(UserQuery.objects.create)(user_id=user_id, query=query, response=faq_answer, parent=previous_query)


                except Exception as e:
                    await bot.send_chat_action(message.chat.id, action="typing")
                    chatgpt_answer = await asyncio.wait_for(get_chatgpt_response(query), timeout=15.0)
                    
                    await message.answer(chatgpt_answer)
                    # Сохраняем новый запрос и связываем с предыдущим
                    await sync_to_async(UserQuery.objects.create)(user_id=user_id, query=query, response=chatgpt_answer)
                    await sync_to_async(FAQLearning.objects.create)(question=query, answer=chatgpt_answer)
                    print(f'44444444444444444444444444444444444444{e}')
    
    except asyncio.TimeoutError:
        await message.answer("Произошла задержка при получении ответа. Пожалуйста, попробуйте позже.")
    except Exception as e:
        logging.error(f"Error while handling message: {e}")
        await message.answer("Произошла ошибка при обработке вашего запроса.")

# Регистрация обработчика команды /start
dp.message.register(handle_message, Command(commands=["start"]))

# Регистрация обработчика для обычных сообщений
dp.message.register(handle_message)

# Логика запроса к ChatGPT
client = AsyncOpenAI(api_key=os.environ['CHAT_GPT_API_KEY'])

async def get_chatgpt_response(query):
    try:
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты — полезный ассистент, отвечай всегда на русском языке."},
                {"role": "user", "content": query}
            ],
            max_tokens=150
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"Error while getting response from ChatGPT: {e}")
        return "Извините, не удалось получить ответ от сервера."

# Функция для запуска бота
async def start_bot():
    await dp.start_polling(bot)
