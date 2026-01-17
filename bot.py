import asyncio
import os
import re
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ChatPermissions
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN not set")

bot = Bot(token=TOKEN)
dp = Dispatcher()

USERNAME_RE = re.compile(r"@(\w+)", re.IGNORECASE)

# ================== WEB SERVER (для Render) ==================

async def handle(request):
    return web.Response(text="Bot is running")

async def start_web():
    app = web.Application()
    app.router.add_get("/", handle)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

# ============================================================

async def get_user_by_username(username: str):
    try:
        return await bot.get_chat(username)
    except:
        return None

# ======================= МУТ =======================

@dp.message(F.text.lower().startswith("мут"))
async def mute_user(message: Message):
    target = None

    if message.reply_to_message:
        target = message.reply_to_message.from_user
    else:
        m = USERNAME_RE.search(message.text)
        if m:
            target = await get_user_by_username("@" + m.group(1))

    if not target:
        return await message.answer("Укажи пользователя ответом или через @username")

    try:
        await bot.restrict_chat_member(
            message.chat.id,
            target.id,
            permissions=ChatPermissions(can_send_messages=False)
        )
        await message.answer(f"🔇 Мут: {target.full_name}")
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")

# ======================= РАЗМУТ =======================

@dp.message(F.text.lower().startswith("размут"))
async def unmute_user(message: Message):
    target = None

    if message.reply_to_message:
        target = message.reply_to_message.from_user
    else:
        m = USERNAME_RE.search(message.text)
        if m:
            target = await get_user_by_username("@" + m.group(1))

    if not target:
        return await message.answer("Укажи пользователя ответом или через @username")

    try:
        await bot.restrict_chat_member(
            message.chat.id,
            target.id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        await message.answer(f"🔊 Размут: {target.full_name}")
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")

# ======================= БАН =======================

@dp.message(F.text.lower().startswith("бан"))
async def ban_user(message: Message):
    target = None

    if message.reply_to_message:
        target = message.reply_to_message.from_user
    else:
        m = USERNAME_RE.search(message.text)
        if m:
            target = await get_user_by_username("@" + m.group(1))

    if not target:
        return await message.answer("Укажи пользователя ответом или через @username")

    try:
        await bot.ban_chat_member(message.chat.id, target.id)
        await message.answer(f"⛔ Бан: {target.full_name}")
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")

# ======================= РАЗБАН =======================

@dp.message(F.text.lower().startswith("разбан"))
async def unban_user(message: Message):
    target = None

    if message.reply_to_message:
        target = message.reply_to_message.from_user
    else:
        m = USERNAME_RE.search(message.text)
        if m:
            target = await get_user_by_username("@" + m.group(1))

    if not target:
        return await message.answer("Укажи пользователя ответом или через @username")

    try:
        await bot.unban_chat_member(message.chat.id, target.id)
        await message.answer(f"♻️ Разбан: {target.full_name}")
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")

# ======================= ЗАПУСК =======================

async def main():
    await start_web()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
