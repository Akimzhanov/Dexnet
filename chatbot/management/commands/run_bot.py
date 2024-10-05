from django.core.management.base import BaseCommand
import asyncio
from chatbot.bots import start_bot  # Импортируем функцию для запуска бота

class Command(BaseCommand):
    help = 'Запуск Telegram-бота'

    def handle(self, *args, **kwargs):
        # Запускаем бота в основном потоке
        asyncio.run(start_bot())
