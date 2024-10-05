import asyncio, os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from chatbot.models import FAQ, UserQuery, FAQLearning
import openai
from openai import AsyncOpenAI
from django.conf import settings
from aiogram.filters import Command  # Фильтр для команд
from asgiref.sync import sync_to_async  # Импортируем sync_to_async

# Настроим логирование
logging.basicConfig(level=logging.INFO)

bot = Bot(token=os.getenv('BOT_TOKEN'))
dp = Dispatcher(storage=MemoryStorage())

openai.api_key = os.getenv('CHAT_GPT_API_KEY')

# Поиск по базе данных
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
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    query = message.text

    # Показываем, что бот "печатает"
    await bot.send_chat_action(message.chat.id, action="typing")
    
    try:
        faq_answer = await search_faq_or_chatgpt(query)  # Используем await для асинхронного вызова
        
        if faq_answer and faq_answer != '/start':
            await message.answer(faq_answer)
            await sync_to_async(UserQuery.objects.create)(user_id=user_id, query=query, response=faq_answer)  # Оборачиваем сохранение в БД
        else:
            # Показываем, что бот продолжает "печатать", пока ждет ответ от ChatGPT
            await bot.send_chat_action(message.chat.id, action="typing")
            
            # Добавим таймаут на 15 секунд для запроса к ChatGPT
            chatgpt_answer = await asyncio.wait_for(get_chatgpt_response(query), timeout=15.0)
            
            await message.answer(chatgpt_answer)
            await sync_to_async(UserQuery.objects.create)(user_id=user_id, query=query, response=chatgpt_answer)  # Сохранение результата в БД
            await sync_to_async(FAQLearning.objects.create)(question=query, answer=chatgpt_answer)  # Сохранение для обучения
    
    except asyncio.TimeoutError:
        await message.answer("Произошла задержка при получении ответа. Пожалуйста, попробуйте позже.")
    except Exception as e:
        logging.error(f"Error while handling message: {e}")
        await message.answer("Произошла ошибка при обработке вашего запроса.")

# Регистрация обработчика команды /start
dp.message.register(handle_message, Command(commands=["start"]))

# Регистрация обработчика для любых текстовых сообщений
dp.message.register(handle_message)  # Регистрация для всех сообщений

# Логика запроса к ChatGPT
client = AsyncOpenAI(api_key=os.environ['CHAT_GPT_API_KEY'])

async def get_chatgpt_response(query):
    try:
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты — полезный ассистент, отвечай всегда на русском языке."},  # Указываем, что бот должен отвечать на русском
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
