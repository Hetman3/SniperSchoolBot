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
        pool = context.bot_data["db_pool"]

        print(f"🟢 Отримано повідомлення від {user_id}: {user_message}")

        await save_message_to_db(pool, user_id, user_message, is_user=True)

        history = await get_chat_history_cached(context, pool, user_id)
        messages = [{"role": "system", "content": "Ти Дорослий та мудрий чоловік, твоє імʼя Джон..."}]

        for record in history:
            role = "user" if record["is_user"] else "assistant"
            messages.append({"role": role, "content": record["message"]})

        messages.append({"role": "user", "content": user_message})

        response = await client.chat.completions.create(model="gpt-4o", messages=messages)
        bot_response_text = response.choices[0].message.content

        print(f"🟢 Відповідь бота: {bot_response_text}")
        await update.message.reply_text(bot_response_text)

        await save_message_to_db(pool, user_id, bot_response_text, is_user=False)

    except Exception as e:
        print(f"❌ Неочікувана помилка: {e}")

# ✅ Головна функція запуску бота
async def start_bot():
    db_pool = await connect_to_db()
    await initialize_db(db_pool)

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.bot_data["db_pool"] = db_pool
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.job_queue.run_daily(clear_old_cache, time=datetime.time(hour=3, tzinfo=TZ_KYIV))

    print("✅ Бот працює! Натисніть Stop, щоб зупинити.")
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(start_bot())
