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

# ✅ Час очищення кешу (03:00 GMT+3)
CACHE_CLEANUP_HOUR = 3  

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

# ✅ Функція збереження повідомлень у базу
async def save_message_to_db(pool, user_id, message, is_user=True):
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                """
                INSERT INTO chat_history (user_id, message, is_user, timestamp)
                VALUES ($1, $2, $3, NOW());
                """,
                user_id, message, is_user
            )
            print(f"✅ Повідомлення збережено в БД: {message}")
        except Exception as e:
            print(f"❌ Помилка запису в БД: {e}")

# ✅ Функція отримання історії чату з кешем або бази
async def get_chat_history_cached(context: ContextTypes.DEFAULT_TYPE, pool, user_id):
    if "chat_history" not in context.chat_data:
        context.chat_data["chat_history"] = {}

    if user_id in context.chat_data["chat_history"]:
        history_data = context.chat_data["chat_history"][user_id]
        if time.time() - history_data["timestamp"] < CACHE_EXPIRATION_TIME:
            return history_data["history"]

    # Якщо кеш застарів або його немає – отримуємо повну історію з PostgreSQL
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch("""
                SELECT message, is_user FROM chat_history
                WHERE user_id = $1
                ORDER BY timestamp ASC;
            """, user_id)
            context.chat_data["chat_history"][user_id] = {"history": rows, "timestamp": time.time()}
            return rows
        except Exception as e:
            print(f"❌ Помилка отримання історії чату: {e}")
            return []

# ✅ Функція очищення кешу щодня о 03:00 (GMT+3)
async def clear_old_cache(context: ContextTypes.DEFAULT_TYPE):
    if "chat_history" in context.chat_data:
        current_time = time.time()
        before_cleaning = len(context.chat_data["chat_history"])
        context.chat_data["chat_history"] = {
            user_id: data for user_id, data in context.chat_data["chat_history"].items()
            if current_time - data["timestamp"] < CACHE_EXPIRATION_TIME
        }
        after_cleaning = len(context.chat_data["chat_history"])
        print(f"✅ Очищено кеш: {before_cleaning - after_cleaning} користувачів.")

# ✅ Функція перевірки кешу
async def cache_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMINS:
        await update.message.reply_text("❌ У вас немає прав для перегляду кешу.")
        return

    if "chat_history" not in context.chat_data or not context.chat_data["chat_history"]:
        await update.message.reply_text("📂 Кеш порожній або не ініціалізований.")
        return

    total_users = len(context.chat_data["chat_history"])
    await update.message.reply_text(f"📊 **Кількість користувачів у кеші:** {total_users}")

# ✅ Функція очищення історії чату
async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMINS:
        await update.message.reply_text("❌ У вас немає прав для очищення історії.")
        return

    user_id = update.message.chat_id
    pool = context.bot_data["db_pool"]

    if "chat_history" in context.chat_data:
        context.chat_data["chat_history"].pop(user_id, None)

    async with pool.acquire() as conn:
        try:
            await conn.execute("DELETE FROM chat_history WHERE user_id = $1;", user_id)
            await update.message.reply_text("✅ Історію чату очищено!")
            print(f"✅ Історія чату користувача {user_id} була очищена.")
        except Exception as e:
            print(f"❌ Помилка при видаленні історії: {e}")
            await update.message.reply_text("❌ Помилка при очищенні історії.")

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

# ✅ Функція для видачі анкети
async def send_survey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Почати анкету", callback_data='start_survey')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Натисніть "Почати анкету" для початку:', reply_markup=reply_markup)

# ✅ Обробка натискання кнопки "Почати анкету"
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Анкета почалася. Відповідайте на наступні питання:")

    questions = [
        "Яке ваше ім'я?",
        "Скільки вам років?",
        "Який ваш email?",
        "Розкажіть про себе"
    ]

    for question in questions:
        await context.bot.send_message(chat_id=query.message.chat_id, text=question)
        # Тут можна додати логіку для збору відповідей

# ✅ Головна функція запуску бота
async def start_bot():
    db_pool = await connect_to_db()
    await initialize_db(db_pool)

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.bot_data["db_pool"] = db_pool
    application.add_handler(CommandHandler("cache_status", cache_status))
    application.add_handler(CommandHandler("clear_history", clear_history))
    application.add_handler(CommandHandler("survey", send_survey))  # Додаємо обробник для команди /survey
    application.add_handler(CallbackQueryHandler(button))  # Додаємо обробник для натискання кнопки
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.job_queue.run_daily(clear_old_cache, time=datetime.time(hour=3, tzinfo=TZ_KYIV))

    print("✅ Бот працює! Натисніть Stop, щоб зупинити.")
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(start_bot())
