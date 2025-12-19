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
DEFAULT_CHECK_HOUR = 9        # 09:00
DEFAULT_TIMEOUT = 30          # минут

# ---------------- БАЗА ----------------
conn = sqlite3.connect("data.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    is_active INTEGER DEFAULT 1,
    check_hour INTEGER,
    timeout_minutes INTEGER
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

# ---------------- КОМАНДЫ ----------------

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
        "👋 Я бот заботы.\n\n"
        "📌 Команды:\n"
        "/add_contact — добавить близкого\n"
        "/checkin — проверить сейчас\n"
        "/settings — настройки\n"
        "/pause — пауза\n"
        "/resume — включить обратно"
    )

# ---------- КОНТАКТЫ ----------

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
        "👉 Перешли мне сообщение от человека.\n"
        "Он должен написать боту /start."
    )

@dp.callback_query(lambda c: c.data == "ct_phone")
async def add_phone(callback: types.CallbackQuery):
    await callback.message.answer("📞 Отправь номер телефона текстом")

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
    await message.answer("📞 Телефон сохранён (SMS подключим позже)")

# ---------- ПРОВЕРКА ----------

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
        await callback.message.answer("🚨 Я уведомил близких")
    else:
        await callback.message.answer("❤️ Спасибо, что ответил")

# ---------- ТАЙМЕР ----------

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

# ---------- УВЕДОМЛЕНИЯ ----------

async def notify_contacts(user_id, urgent):
    cursor.execute(
        "SELECT type, value FROM contacts WHERE user_id=?",
        (user_id,)
    )
    contacts = cursor.fetchall()

    text = (
        "🆘 Пользователь запросил помощь!"
        if urgent else
        "⚠️ Пользователь не ответил на проверку состояния."
    )

    for t, v in contacts:
        if t == "telegram":
            try:
                await bot.send_message(int(v), text)
            except:
                pass

# ---------- НАСТРОЙКИ ----------

@dp.message(Command("pause"))
async def pause(message: types.Message):
    cursor.execute("UPDATE users SET is_active=0 WHERE user_id=?", (message.from_user.id,))
    conn.commit()
    await message.answer("⏸ Проверки приостановлены")

@dp.message(Command("resume"))
async def resume(message: types.Message):
    cursor.execute("UPDATE users SET is_active=1 WHERE user_id=?", (message.from_user.id,))
    conn.commit()
    await message.answer("▶️ Проверки возобновлены")

# ---------------- ЗАПУСК ----------------

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
