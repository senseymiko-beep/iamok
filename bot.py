import asyncio
import os
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ---------------- НАСТРОЙКИ ----------------
DEFAULT_CHECK_HOUR = 9
DEFAULT_TIMEOUT = 30

# ---------------- БАЗА ----------------
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    is_active INTEGER DEFAULT 1,
    check_hour INTEGER,
    timeout_minutes INTEGER
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

cursor.execute("""
CREATE TABLE IF NOT EXISTS checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    created_at TEXT,
    responded INTEGER DEFAULT 0
)
""")

conn.commit()

# ---------------- КНОПКИ ----------------

def main_menu():
    return types.ReplyKeyboardMarkup(
        keyboard=[
            ["❤️ Я в порядке", "🚨 Мне нужна помощь"],
            ["📇 Контакты", "⚙️ Настройки"]
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

def settings_menu(active=True):
    return types.ReplyKeyboardMarkup(
        keyboard=[
            ["⏰ Время проверки", "⌛ Ожидание ответа"],
            ["⏸ Пауза" if active else "▶️ Возобновить"],
            ["⬅️ Назад"]
        ],
        resize_keyboard=True
    )

def check_buttons():
    return types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="❤️ Я в порядке", callback_data="ok")],
            [types.InlineKeyboardButton(text="🚨 Мне нужна помощь", callback_data="help")]
        ]
    )

# ---------------- START ----------------

@dp.message(Command("start"))
async def start(message: types.Message):
    cursor.execute("""
    INSERT OR IGNORE INTO users
    (user_id, name, check_hour, timeout_minutes)
    VALUES (?, ?, ?, ?)
    """, (
        message.from_user.id,
        message.from_user.full_name,
        DEFAULT_CHECK_HOUR,
        DEFAULT_TIMEOUT
    ))
    conn.commit()

    await message.answer(
        f"👋 Привет, {message.from_user.full_name}!\n\n"
        "Я буду регулярно спрашивать:\n"
        "«Ты в порядке?»\n\n"
        "Если ты не ответишь — я уведомлю твоих близких.",
        reply_markup=main_menu()
    )

# ---------------- ГЛАВНЫЕ КНОПКИ ----------------

@dp.message(lambda m: m.text == "❤️ Я в порядке")
async def i_am_ok(message: types.Message):
    await message.answer("❤️ Отлично. Я рядом.", reply_markup=main_menu())

@dp.message(lambda m: m.text == "🚨 Мне нужна помощь")
async def need_help(message: types.Message):
    await notify_contacts(message.from_user.id, urgent=True)
    await message.answer("🚨 Я уведомил твоих близких", reply_markup=main_menu())

# ---------------- КОНТАКТЫ ----------------

@dp.message(lambda m: m.text == "📇 Контакты")
async def contacts(message: types.Message):
    await message.answer("📇 Управление контактами", reply_markup=contacts_menu())

@dp.message(lambda m: m.text == "➕ Добавить контакт")
async def add_contact(message: types.Message):
    await message.answer(
        "👉 Перешли сообщение от человека.\n"
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
    await message.answer("🏠 Главное меню", reply_markup=main_menu())

# ---------------- ПРОВЕРКА ----------------

async def create_check(user_id):
    cursor.execute(
        "INSERT INTO checks (user_id, created_at) VALUES (?, ?)",
        (user_id, datetime.utcnow().isoformat())
    )
    conn.commit()

    await bot.send_message(
        user_id,
        "💬 Ты в порядке?",
        reply_markup=check_buttons()
    )
    asyncio.create_task(wait_timeout(user_id))

@dp.callback_query(lambda c: c.data in ["ok", "help"])
async def response(callback: types.CallbackQuery):
    cursor.execute(
        "UPDATE checks SET responded=1 WHERE user_id=?",
        (callback.from_user.id,)
    )
    conn.commit()

    if callback.data == "help":
        await notify_contacts(callback.from_user.id, urgent=True)
        await callback.message.answer("🚨 Я уведомил твоих близких")
    else:
        await callback.message.answer("❤️ Спасибо, что ответил")

# ---------------- ТАЙМЕР ----------------

async def wait_timeout(user_id):
    cursor.execute(
        "SELECT timeout_minutes FROM users WHERE user_id=?",
        (user_id,)
    )
    timeout = cursor.fetchone()[0]

    await asyncio.sleep(timeout * 60)

    cursor.execute(
        "SELECT responded FROM checks WHERE user_id=? ORDER BY id DESC LIMIT 1",
        (user_id,)
    )
    row = cursor.fetchone()

    if row and row[0] == 0:
        await notify_contacts(user_id, urgent=False)

# ---------------- УВЕДОМЛЕНИЯ ----------------

async def notify_contacts(user_id, urgent):
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
        f"🚨 ТРЕВОГА\n\n{username} запросил помощь."
        if urgent else
        f"⚠️ ТРЕВОГА\n\n{username} не ответил на проверку состояния."
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
