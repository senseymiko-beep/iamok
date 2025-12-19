import asyncio
import os
import sqlite3
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

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
    contact TEXT
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
    await message.answer("👋 Я буду заботиться о тебе. Добавь близких: /add_contact")

@dp.message(Command("add_contact"))
async def add_contact(message: types.Message):
    await message.answer("✍️ Напиши Telegram username или номер телефона")

@dp.message(lambda msg: msg.text and not msg.text.startswith("/"))
async def save_contact(message: types.Message):
    cursor.execute(
        "INSERT INTO contacts (user_id, contact) VALUES (?, ?)",
        (message.from_user.id, message.text)
    )
    conn.commit()
    await message.answer("✅ Контакт сохранён")

@dp.message(Command("checkin"))
async def checkin(message: types.Message):
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="✅ Я в порядке", callback_data="ok")],
            [types.InlineKeyboardButton(text="🆘 Мне нужна помощь", callback_data="help")]
        ]
    )
    await message.answer("💬 Ты в порядке?", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data == "ok")
async def ok(callback: types.CallbackQuery):
    await callback.message.answer("❤️ Отлично. Я рядом.")

@dp.callback_query(lambda c: c.data == "help")
async def help_me(callback: types.CallbackQuery):
    cursor.execute(
        "SELECT contact FROM contacts WHERE user_id=?",
        (callback.from_user.id,)
    )
    contacts = cursor.fetchall()
    for c in contacts:
        print("🚨 ALERT TO:", c[0])  # пока заглушка
    await callback.message.answer("🚨 Я уведомил близких")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
