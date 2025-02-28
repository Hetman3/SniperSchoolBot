import os
import asyncio
import nest_asyncio
import json
import time
import datetime
import pytz
import asyncpg
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
DATABASE_URL = os.getenv("DATABASE_URL")

# ✅ Функція підключення до бази даних
async def connect_to_db():
    try:
        return await asyncpg.create_pool(DATABASE_URL)
    except Exception as e:
        print(f"❌ Помилка підключення до бази даних: {e}")
        return None

# ✅ Ініціалізація бази даних
async def initialize_db(pool):
    async with pool.acquire() as conn:
        try:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    message TEXT NOT NULL,
                    is_user BOOLEAN NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            print("✅ Таблиця chat_history готова!")
        except Exception as e:
            print(f"❌ Помилка створення таблиці: {e}")

# ✅ Функція очищення кешу
async def clear_old_cache(context: ContextTypes.DEFAULT_TYPE):
    if "chat_history" in context.chat_data:
        current_time = time.time()
        before_cleaning = len(context.chat_data["chat_history"])
        context.chat_data["chat_history"] = {
            user_id: data for user_id, data in context.chat_data["chat_history"].items()
            if current_time - data["timestamp"] < 86400
        }
        after_cleaning = len(context.chat_data["chat_history"])
        print(f"✅ Очищено кеш: {before_cleaning - after_cleaning} користувачів.")

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
