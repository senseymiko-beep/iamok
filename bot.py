import asyncio
import os
import sqlite3
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- НАСТРОЙКИ ---
CHECK_TIMEOUT_MINUTES = 1  # для теста, потом поставишь 30

# --- БАЗА ---
conn = sqlite3.connect("data.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    contact_id INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS checks (
    user_id INTEGER,
    check_time TEXT,
    responded INTEGER
)
""")

conn.commit()

# --- КОМАНДЫ ---

@dp.message(Command("start"))
async def start(message: types.Message):
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
        (message.from_user.id, message.from_user.username)
    )
    conn.commit()
    await message.answer(
        "👋 Я помогу твоим близким узнать, что с тобой всё в порядке.\n\n"
        "1️⃣ Добавь контакт: /add_contact\n"
        "2️⃣ Запусти проверку: /checkin"
    )

@dp.message(Command("add_contact"))
async def add_contact(message: types.Message):
    await message.answer(
        "✍️ Перешли МНЕ сообщение от человека, которого хочешь добавить.\n"
        "Он должен хоть раз написать боту."
    )

@dp.message(lambda m: m.forward_from)
async def save_contact(message: types.Message):
    contact_id = message.forward_from.id
    cursor.execute(
        "INSERT INTO contacts (user_id, contact_id) VALUES (?, ?)",
        (message.from_user.id, contact_id)
    )
    conn.commit()
    await message.answer("✅ Контакт добавлен")

@dp.message(Command("checkin"))
async def checkin(message: types.Message):
    now = datetime.utcnow().isoformat()
    cursor.execute(
        "INSERT INTO checks (user_id, check_time, responded) VALUES (?, ?, 0)",
        (message.from_user.id, now)
    )
    conn.commit()

    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="✅ Я в порядке", callback_data="ok")],
            [types.InlineKeyboardButton(text="🆘 Мне нужна помощь", callback_data="help")]
        ]
    )

    await message.answer("💬 Ты в порядке?", reply_markup=keyboard)
    asyncio.create_task(wait_for_response(message.from_user.id, now))

@dp.callback_query(lambda c: c.data in ["ok", "help"])
async def handle_response(callback: types.CallbackQuery):
    cursor.execute(
        "UPDATE checks SET responded=1 WHERE user_id=?",
        (callback.from_user.id,)
    )
    conn.commit()

    if callback.data == "ok":
        await callback.message.answer("❤️ Отлично. Спасибо, что ответил.")
    else:
        await notify_contacts(callback.from_user.id, urgent=True)
        await callback.message.answer("🚨 Я уведомил твоих близких.")

# --- ЛОГИКА ТАЙМЕРА ---

async def wait_for_response(user_id, check_time):
    await asyncio.sleep(CHECK_TIMEOUT_MINUTES * 60)

    cursor.execute(
        "SELECT responded FROM checks WHERE user_id=? AND check_time=?",
        (user_id, check_time)
    )
    row = cursor.fetchone()

    if row and row[0] == 0:
        await notify_contacts(user_id, urgent=False)

async def notify_contacts(user_id, urgent=False):
    cursor.execute(
        "SELECT contact_id FROM contacts WHERE user_id=?",
        (user_id,)
    )
    contacts = cursor.fetchall()

    text = (
        "🚨 Тревога!\nПользователь не ответил на проверку состояния."
        if not urgent else
        "🆘 Срочно!\nПользователь запросил помощь!"
    )

    for (contact_id,) in contacts:
        try:
            await bot.send_message(contact_id, text)
        except:
            pass

# --- ЗАПУСК ---

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
