from aiogram import Bot, types
from aiogram.dispatcher import dispatcher
import os

bot = Bot(token=os.environ['BOT_TOKEN'])
dp = dispatcher(bot)
