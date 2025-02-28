import os
import asyncio
import nest_asyncio
import json
import asyncpg
import time
import datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from openai import AsyncOpenAI

# ✅ Запобігання конфліктів асинхронного циклу
nest_asyncio.apply()

# ✅ Часовий пояс Києва
TZ_KYIV = pytz.timezone("Europe/Kiev")

# ✅ Ініціалізація API
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# ✅ ID адміністратора
ADMINS = {479486294}

# ✅ Термін зберігання кешу (24 години)
CACHE_EXPIRATION_TIME = 24 * 60 * 60  # 86400 секунд

# ✅ Час очищення кеш ▋
