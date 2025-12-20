import asyncio
import os
import sqlite3
from datetime import datetime, date

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ================== БАЗА ==================

conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    check_hour INTEGER DEFAULT 9,
    last_check_date TEXT,
    waiting INTEGER DEFAULT 0,
    timeout_minutes INTEGER DEFAULT 30
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

# ================== КНОПКИ ==================

def main_menu():
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="🚨 Мне нужна помощь")],
            [types.KeyboardButton(text="📇 Контакты")],
            [types.KeyboardButton(text="⏰ Время проверки")]
        ],
        resize_keyboard=True
    )

def contacts_menu():
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="➕ Добавить контакт")],
            [types.KeyboardButton(text="📄 Список контактов")],
            [types.KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )

def check_menu():
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="❤️ Я в порядке")],
            [types.KeyboardButton(text="🚨 Мне нужна помощь")]
        ],
        resize_keyboard=True
    )

# ================== START ==================

@dp.message(Command("start"))
async def start(message: Message):
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id, name) VALUES (?, ?)",
        (message.from_user.id, message.from_user.full_name)
    )
    conn.commit()

    await message.answer(
        "👋 Привет!\n\n"
        "Я буду регулярно спрашивать:\n"
        "«Ты в порядке?»\n\n"
        "Если ты не ответишь — я уведомлю твоих близких.",
        reply_markup=main_menu()
    )

# ================== ОСНОВНОЙ ОБРАБОТЧИК ==================

@dp.message()
async def handle_messages(message: Message):
    text = (message.text or "").strip()

    # ❤️ ответил — всё хорошо
    if text.startswith("❤️"):
        cursor.execute(
            "UPDATE users SET waiting=0 WHERE user_id=?",
            (message.from_user.id,)
        )
        conn.commit()

        await message.answer(
            "❤️ Отлично. Рад, что ты в порядке.",
            reply_markup=main_menu()
        )
        return

    # 🚨 запрос помощи
    if text.startswith("🚨"):
        cursor.execute(
            "UPDATE users SET waiting=0 WHERE user_id=?",
            (message.from_user.id,)
        )
        conn.commit()

        await notify_contacts(message.from_user.id)

        await message.answer(
            "🚨 Я уведомил твоих близких",
            reply_markup=main_menu()
        )
        return

    # пересланный контакт
    if message.forward_from is not None:
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
        return

    if text.startswith("📇"):
        await message.answer("📇 Управление контактами", reply_markup=contacts_menu())
        return

    if text.startswith("➕"):
        await message.answer(
            "👉 Перешли мне сообщение человека.\n"
            "Он должен написать боту /start."
        )
        return

    if text.startswith("📄"):
        cursor.execute(
            "SELECT name FROM contacts WHERE user_id=?",
            (message.from_user.id,)
        )
        rows = cursor.fetchall()

        if not rows:
            await message.answer("📭 Контактов пока нет", reply_markup=contacts_menu())
            return

        msg = "📇 Твои контакты:\n\n"
        for (name,) in rows:
            msg += f"• {name}\n"

        await message.answer(msg, reply_markup=contacts_menu())
        return

    if text.startswith("⬅️"):
        await message.answer("🏠 Главное меню", reply_markup=main_menu())
        return

    if text.startswith("⏰"):
        keyboard = types.ReplyKeyboardMarkup(
            keyboard=[
                [types.KeyboardButton(text=f"{h:02d}:00")]
                for h in range(6, 23)
            ] + [[types.KeyboardButton(text="⬅️ Назад")]],
            resize_keyboard=True
        )
        await message.answer(
            "⏰ Во сколько тебе писать «Ты в порядке?»",
            reply_markup=keyboard
        )
        return

    if ":" in text and text.endswith(":00"):
        try:
            hour = int(text.split(":")[0])
        except ValueError:
            return

        cursor.execute(
            "UPDATE users SET check_hour=? WHERE user_id=?",
            (hour, message.from_user.id)
        )
        conn.commit()

        await message.answer(
            f"✅ Я буду писать тебе каждый день в {hour:02d}:00",
            reply_markup=main_menu()
        )
        return

# ================== АВТОПРОВЕРКА ==================

async def daily_checks():
    while True:
        try:
            now = datetime.now()
            today = date.today().isoformat()

            cursor.execute(
                "SELECT user_id, check_hour, last_check_date FROM users"
            )
            users = cursor.fetchall()

            for user_id, hour, last_date in users:
                if now.hour == hour and last_date != today:
                    await bot.send_message(
                        user_id,
                        "💬 Ты в порядке?",
                        reply_markup=check_menu()
                    )
                    cursor.execute(
                        "UPDATE users SET last_check_date=?, waiting=1 WHERE user_id=?",
                        (today, user_id)
                    )
                    conn.commit()

                    asyncio.create_task(wait_for_answer(user_id))

        except Exception as e:
            print("daily_checks error:", e)

        await asyncio.sleep(60)

# ================== ОЖИДАНИЕ ОТВЕТА ==================

async def wait_for_answer(user_id: int):
    try:
        cursor.execute(
            "SELECT timeout_minutes FROM users WHERE user_id=?",
            (user_id,)
        )
        timeout = cursor.fetchone()[0]

        await asyncio.sleep(timeout * 60)

        cursor.execute(
            "SELECT waiting FROM users WHERE user_id=?",
            (user_id,)
        )
        waiting = cursor.fetchone()[0]

        if waiting == 1:
            await notify_contacts(user_id)

            cursor.execute(
                "UPDATE users SET waiting=0 WHERE user_id=?",
                (user_id,)
            )
            conn.commit()

    except Exception as e:
        print("wait_for_answer error:", e)

# ================== УВЕДОМЛЕНИЯ ==================

async def notify_contacts(user_id: int):
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
        f"{username} не ответил на проверку «Ты в порядке?».\n"
        "Пожалуйста, срочно свяжитесь с ним."
    )

    for (cid,) in contacts:
        try:
            await bot.send_message(cid, text)
        except:
            pass

# ================== ЗАПУСК ==================

async def main():
    print("Bot polling started")
    asyncio.create_task(daily_checks())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
