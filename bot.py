import asyncio
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set. Add it in Railway Variables.")

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start(message: types.Message):
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
    await callback.message.answer("❤️ Рад слышать")

@dp.callback_query(lambda c: c.data == "help")
async def help_me(callback: types.CallbackQuery):
    await callback.message.answer("🚨 Я уведомлю близких (следующий шаг)")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
