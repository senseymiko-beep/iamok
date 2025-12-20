import asyncio
import os
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ---------------- НАСТРОЙКИ ----------------
TOKEN = os.getenv("BOT_TOKEN")

DEFAULT_CHECK_HOUR = 9     # ежедневная проверка в 09:00
DEFAULT_TIMEOUT = 30       # минут ожидания ответа

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ---------------- БАЗА ----------------
conn = sqlite3.connect("data.db", check_same_thread=False)
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
    value TEXT,
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

# ---------------- START ----------------

@dp.message(Command("start"))
async def start(message: types.Message):
    cursor.execute("""
    INSERT OR IGNORE INTO users
    (user_id, username, check_hour, timeout_minutes)
    VALUES (?, ?, ?, ?)
    """, (
        message.from_user.id,
        message.from_user.full_name,
        DEFAULT_CHECK_HOUR,
        DEFAULT_TIMEOUT
    ))
    conn.commit()

    await message.answer(
        "👋 Бот заботы активен.\n\n"
        "📌 Команды:\n"
        "/add_contact — добавить контакт\n"
        "/contacts — список контактов\n"
        "/remove_contact — удалить контакт\n"
        "/checkin — проверка сейчас\n"
        "/pause — пауза\n"
        "/resume — продолжить"
    )

# ---------------- КОНТАКТЫ ----------------

@dp.message(Command("add_contact"))
async def add_contact(message: types.Message):
    await message.answer(
        "👉 Перешли мне сообщение от человека.\n"
        "Он должен написать боту /start."
    )

@dp.message(lambda m: m.forward_from is not None)
async def save_contact(message: types.Message):
    tg = message.forward_from

    cursor.execute(
        "INSERT INTO contacts (user_id, type, value, name) VALUES (?, 'telegram', ?, ?)",
        (message.from_user.id, tg.id, tg.full_name)
    )
    conn.commit()

    await message.answer(f"✅ Контакт добавлен: {tg.full_name}")

@dp.message(Command("contacts"))
async def list_contacts(message: types.Message):
    cursor.execute(
        "SELECT id, name FROM contacts WHERE user_id=?",
        (message.from_user.id,)
    )
    rows = cursor.fetchall()

    if not rows:
        await message.answer("📭 Контактов пока нет")
        return

    text = "📇 Твои контакты:\n\n"
    for cid, name in rows:
        text += f"{cid}. {name}\n"

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

# ---------------- ПРОВЕРКА ----------------

@dp.message(Command("checkin"))
async def checkin(message: types.Message):
    await create_check(message.from_user.id)

async def create_check(user_id):
    cursor.execute(
        "INSERT INTO checks (user_id, created_at) VALUES (?, ?)",
        (user_id, datetime.utcnow().isoformat())
    )
    conn.commit()

    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(text="✅ Я в порядке", callback_data="ok")],
            [types.InlineKeyboardButton(text="🆘 Мне нужна помощь", callback_data="help")]
        ]
    )

    await bot.send_message(user_id, "💬 Ты в порядке?", reply_markup=keyboard)
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
        "SELECT username FROM users WHERE user_id=?",
        (user_id,)
    )
    username = cursor.fetchone()[0] or "Пользователь"

    cursor.execute(
        "SELECT value FROM contacts WHERE user_id=? AND type='telegram'",
        (user_id,)
    )
    contacts = cursor.fetchall()

    text = (
        f"🆘 Срочно!\n\n{username} запросил помощь."
        if urgent else
        f"⚠️ Тревога!\n\n{username} не ответил на проверку состояния."
    )

    for (contact_id,) in contacts:
        try:
            await bot.send_message(int(contact_id), text)
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

        for user_id, hour in users:
            if now.hour == hour and now.minute == 0:
                await create_check(user_id)

        await asyncio.sleep(60)

# ---------------- ПАУЗА ----------------

@dp.message(Command("pause"))
async def pause(message: types.Message):
    cursor.execute(
        "UPDATE users SET is_active=0 WHERE user_id=?",
        (message.from_user.id,)
    )
    conn.commit()

    await message.answer("⏸ Проверки приостановлены")

@dp.message(Command("resume"))
async def resume(message: types.Message):
    cursor.execute(
        "UPDATE users SET is_active=1 WHERE user_id=?",
        (message.from_user.id,)
    )
    conn.commit()

    await message.answer("▶️ Проверки возобновлены")

# ---------------- ЗАПУСК ----------------

async def main():
    asyncio.create_task(daily_checks())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
