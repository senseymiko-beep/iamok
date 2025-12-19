import asyncio
import os
import sqlite3
from datetime import datetime, time

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

# ---------------- НАСТРОЙКИ ----------------
DEFAULT_CHECK_HOUR = 9
DEFAULT_TIMEOUT = 30  # минут

# ---------------- БАЗА ----------------
conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    is_active INTEGER DEFAULT 1,
    check_hour INTEGER,
    timeout_minutes INTEGER,
    last_lat REAL,
    last_lon REAL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    type TEXT,
    value TEXT
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

# ---------------- СТАРТ ----------------

@dp.message(Command("start"))
async def start(message: types.Message):
    cursor.execute("""
    INSERT OR IGNORE INTO users
    (user_id, username, check_hour, timeout_minutes)
    VALUES (?, ?, ?, ?)
    """, (
        message.from_user.id,
        message.from_user.username,
        DEFAULT_CHECK_HOUR,
        DEFAULT_TIMEOUT
    ))
    conn.commit()

    await message.answer(
        "👋 Бот заботы активен.\n\n"
        "/add_contact — добавить контакт\n"
        "/contacts — список контактов\n"
        "/checkin — проверка сейчас\n"
        "/pause /resume — пауза\n"
        "/settings — настройки"
    )

# ---------------- КОНТАКТЫ ----------------

@dp.message(Command("contacts"))
async def list_contacts(message: types.Message):
    cursor.execute(
        "SELECT id, type, value FROM contacts WHERE user_id=?",
        (message.from_user.id,)
    )
    rows = cursor.fetchall()

    if not rows:
        await message.answer("📭 Контактов пока нет")
        return

    text = "📇 Твои контакты:\n\n"
    for cid, t, v in rows:
        label = "Telegram" if t == "telegram" else "Телефон"
        text += f"{cid}. {label}: {v}\n"

    await message.answer(text)

@dp.message(Command("remove_contact"))
async def remove_contact(message: types.Message):
    await message.answer("✍️ Напиши ID контакта из списка")

@dp.message(lambda m: m.text and m.text.isdigit())
async def delete_contact(message: types.Message):
    cursor.execute(
        "DELETE FROM contacts WHERE id=? AND user_id=?",
        (int(message.text), message.from_user.id)
    )
    conn.commit()
    await message.answer("🗑 Контакт удалён")

# ---------------- ДОБАВЛЕНИЕ ----------------

@dp.message(Command("add_contact"))
async def add_contact(message: types.Message):
    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="📲 Telegram", callback_data="ct_tg")],
            [types.InlineKeyboardButton(text="☎️ Телефон", callback_data="ct_phone")]
        ]
    )
    await message.answer("Как добавить контакт?", reply_markup=kb)

@dp.callback_query(lambda c: c.data == "ct_tg")
async def add_tg(callback: types.CallbackQuery):
    await callback.message.answer(
        "👉 Перешли сообщение человека.\nОн должен написать боту /start."
    )

@dp.callback_query(lambda c: c.data == "ct_phone")
async def add_phone(callback: types.CallbackQuery):
    await callback.message.answer("📞 Отправь номер телефона")

@dp.message(lambda m: m.forward_from)
async def save_tg_contact(message: types.Message):
    cursor.execute(
        "INSERT INTO contacts (user_id, type, value) VALUES (?, 'telegram', ?)",
        (message.from_user.id, message.forward_from.id)
    )
    conn.commit()
    await message.answer("✅ Telegram-контакт добавлен")

@dp.message(lambda m: m.text and m.text.startswith("+"))
async def save_phone(message: types.Message):
    cursor.execute(
        "INSERT INTO contacts (user_id, type, value) VALUES (?, 'phone', ?)",
        (message.from_user.id, message.text)
    )
    conn.commit()
    await message.answer("📞 Телефон сохранён")

# ---------------- ГЕОЛОКАЦИЯ ----------------

@dp.message(content_types=types.ContentType.LOCATION)
async def save_location(message: types.Message):
    cursor.execute(
        "UPDATE users SET last_lat=?, last_lon=? WHERE user_id=?",
        (message.location.latitude, message.location.longitude, message.from_user.id)
    )
    conn.commit()
    await message.answer("📍 Геолокация сохранена")

# ---------------- ПРОВЕРКИ ----------------

@dp.message(Command("checkin"))
async def checkin(message: types.Message):
    await create_check(message.from_user.id)

async def create_check(user_id):
    cursor.execute(
        "INSERT INTO checks (user_id, created_at) VALUES (?, ?)",
        (user_id, datetime.utcnow().isoformat())
    )
    conn.commit()

    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="✅ Я в порядке", callback_data="ok")],
            [types.InlineKeyboardButton(text="🆘 Мне нужна помощь", callback_data="help")]
        ]
    )

    await bot.send_message(user_id, "💬 Ты в порядке?", reply_markup=kb)
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
        await callback.message.answer("🚨 Я уведомил контакты")
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
    if cursor.fetchone()[0] == 0:
        await notify_contacts(user_id, urgent=False)

# ---------------- УВЕДОМЛЕНИЯ ----------------

async def notify_contacts(user_id, urgent):
    cursor.execute(
        "SELECT type, value FROM contacts WHERE user_id=?",
        (user_id,)
    )
    contacts = cursor.fetchall()

    cursor.execute(
        "SELECT last_lat, last_lon FROM users WHERE user_id=?",
        (user_id,)
    )
    lat, lon = cursor.fetchone()

    text = (
        "🆘 Пользователь запросил помощь!"
        if urgent else
        "⚠️ Пользователь не ответил на проверку."
    )

    for t, v in contacts:
        if t == "telegram":
            try:
                await bot.send_message(int(v), text)
                if lat and lon:
                    await bot.send_location(int(v), lat, lon)
            except:
                pass

# ---------------- ДНЕВНЫЕ ПРОВЕРКИ ----------------

async def daily_checks():
    while True:
        now = datetime.now()
        cursor.execute(
            "SELECT user_id, check_hour FROM users WHERE is_active=1"
        )
        users = cursor.fetchall()

        for uid, hour in users:
            if now.hour == hour and now.minute == 0:
                await create_check(uid)

        await asyncio.sleep(60)

# ---------------- ЗАПУСК ----------------

async def main():
    asyncio.create_task(daily_checks())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
