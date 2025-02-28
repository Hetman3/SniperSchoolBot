import os
import asyncio
import nest_asyncio
import json
import time
import datetime
import pytz
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openai import AsyncOpenAI

# ✅ Запобігання конфліктів асинхронного циклу
nest_asyncio.apply()

# ✅ Часовий пояс Києва
TZ_KYIV = pytz.timezone("Europe/Kiev")

# ✅ Ініціалізація API
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# ✅ Функція обробки повідомлень
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_message = update.message.text
        user_id = update.message.chat_id

        print(f"🟢 Отримано повідомлення від {user_id}: {user_message}")

        # Додано визначення змінної messages
        messages = [{"role": "system", "content": "Ти Дорослий та мудрий чоловік, твоє імʼя Джон..."}]
        messages.append({"role": "user", "content": user_message})

        response = await client.chat.completions.create(model="gpt-4o", messages=messages)
        bot_response_text = response.choices[0].message.content

        print(f"🟢 Відповідь бота: {bot_response_text}")
        await update.message.reply_text(bot_response_text)

    except Exception as e:
        print(f"❌ Неочікувана помилка: {e}")

# ✅ Головна функція запуску бота
async def start_bot():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Використання вебхуків для уникнення конфліктів
    webhook_url = os.getenv("WEBHOOK_URL")
    application.bot.set_webhook(webhook_url)
    
    print("✅ Бот працює! Натисніть Stop, щоб зупинити.")
    await application.start_webhook(listen="0.0.0.0", port=int(os.getenv("PORT", 8443)), url_path=webhook_url)

if __name__ == "__main__":
    asyncio.run(start_bot())
