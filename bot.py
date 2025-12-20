import asyncio
import os
import sqlite3

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ---------------- БАЗА ----------------
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    tg_id INTEGER,
    name TEXT
)
""")

conn.commit()

# ---------------- КНОПКИ ----------------

def main_menu():
    return types.ReplyKeyboardMarkup(
        keyboard=[
            ["🚨 Мне нужна помощь"],
            ["📇 Контакты"]
        ],
        resize_keyboard=True
    )

def contacts_menu():
    return types.ReplyKeyboardMarkup(
        keyboard=[
            ["➕ Добавить контакт"],
            ["📄 Список контактов"],
            ["⬅️ Назад"]
        ],
        resize_keyboard=True
    )

# ---------------- START ----------------

@dp.message(Command("start"))
async def start(message: types.Message):
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, name) VALUES (?, ?)",
        (message.from_user.id, message.from_user.full_name)
    )
    conn.commit()

    await message.answer(
        f"👋 Привет, {message.from_user.full_name}\n\n"
        "Если тебе станет плохо — нажми кнопку ниже.\n"
        "Я уведомлю твоих близких.",
        reply_markup=main_menu()
    )

# ---------------- ГЛАВНОЕ МЕНЮ ----------------

@dp.message(lambda m: m.text == "🚨 Мне нужна помощь")
async def help_now(message: types.Message):
    await notify_contacts(message.from_user.id)
    await message.answer(
        "🚨 Я уведомил твоих близких",
        reply_markup=main_menu()
    )

@dp.message(lambda m: m.text == "📇 Контакты")
async def contacts(message: types.Message):
    await message.answer(
        "📇 Управление контактами",
        reply_markup=contacts_menu()
    )

# ---------------- КОНТАКТЫ ----------------

@dp.message(lambda m: m.text == "➕ Добавить контакт")
async def add_contact(message: types.Message):
    await message.answer(
        "👉 Перешли сообщение человека.\n"
        "Он должен написать боту /start."
    )

@dp.message(lambda m: m.forward_from is not None)
async def save_contact(message: types.Message):
    tg = message.forward_from

    cursor.execute(
        "INSERT INTO contacts (user_id, tg_id, name) VALUES (?, ?, ?)",
        (message.from_user.id, tg.id, tg.full_name)
    )
    conn.commit()

    await message.answer(
        f"✅ Контакт добавлен: {tg.full_name}",
        reply_markup=contacts_menu()
    )

@dp.message(lambda m: m.text == "📄 Список контактов")
async def list_contacts(message: types.Message):
    cursor.execute(
        "SELECT name FROM contacts WHERE user_id=?",
        (message.from_user.id,)
    )
    rows = cursor.fetchall()

    if not rows:
        await message.answer("📭 Контактов пока нет")
        return

    text = "📇 Твои контакты:\n\n"
    for (name,) in rows:
        text += f"• {name}\n"

    await message.answer(text, reply_markup=contacts_menu())

@dp.message(lambda m: m.text == "⬅️ Назад")
async def back(message: types.Message):
    await message.answer(
        "🏠 Главное меню",
        reply_markup=main_menu()
    )

# ---------------- УВЕДОМЛЕНИЯ ----------------

async def notify_contacts(user_id):
    cursor.execute(
        "SELECT name FROM users WHERE user_id=?",
        (user_id,)
    )
    username = cursor.fetchone()[0]

    cursor.execute(
        "SELECT tg_id FROM contacts WHERE user_id=?",
        (user_id,)
    )
    contacts = cursor.fetchall()

    text = (
        "🚨 ТРЕВОГА\n\n"
        f"{username} просит о помощи.\n"
        "Пожалуйста, срочно свяжитесь с ним."
    )

    for (cid,) in contacts:
        try:
            await bot.send_message(cid, text)
        except:
            pass

# ---------------- ЗАПУСК ----------------

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
