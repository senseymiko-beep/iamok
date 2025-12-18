import asyncio
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TOKEN = os.getenv(8166137355:AAEjmCtksJaKPeJjx4cWYtCNeGUTCk9gkw8)

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

USERS = {}

@dp.message(Command("start"))
async def start(message: types.Message):
    USERS[message.from_user.id] = {"responded": True}
    await message.answer(
        "💬 Ты в порядке?",
        reply_markup=types.InlineKeyboardMarkup(
            inline_keyboard=[
                [types.InlineKeyboardButton(text="✅ Я в порядке", callback_data="ok")],
                [types.InlineKeyboardButton(text="🆘 Мне нужна помощь", callback_data="help")]
            ]
        )
    )

@dp.callback_query(lambda c: c.data == "ok")
async def ok(callback: types.CallbackQuery):
    USERS[callback.from_user.id]["responded"] = True
    await callback.message.answer("❤️ Рад слышать")

@dp.callback_query(lambda c: c.data == "help")
async def help_me(callback: types.CallbackQuery):
    await callback.message.answer("🚨 Я уведомляю контакты")

async def daily_check():
    for user_id in USERS:
        USERS[user_id]["responded"] = False
        await bot.send_message(user_id, "💬 Ты в порядке?")

scheduler.add_job(daily_check, "interval", hours=24)

async def main():
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
