import asyncio
import os
import re
from datetime import timedelta, datetime
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, ChatJoinRequest
from aiogram.exceptions import TelegramBadRequest

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN not set")

bot = Bot(token=TOKEN)
dp = Dispatcher()

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


# ================== УТИЛИТЫ ==================
TIME_RE = re.compile(r"(\d+)\s*(мин|мину|минут|час|часа|часов|день|дня|дней|нед|недел)", re.IGNORECASE)

def parse_time(text):
    m = TIME_RE.search(text)
    if not m:
        return None
    value = int(m.group(1))
    unit = m.group(2).lower()

    if unit.startswith("мин"):
        return timedelta(minutes=value)
    if unit.startswith("час"):
        return timedelta(hours=value)
    if unit.startswith("ден"):
        return timedelta(days=value)
    if unit.startswith("нед"):
        return timedelta(days=value * 7)
    return None

async def is_admin(chat_id, user_id):
    admins = await bot.get_chat_administrators(chat_id)
    return any(a.user.id == user_id for a in admins)
# ============================================================


# ================== АВТОПРИНЯТИЕ ЗАЯВОК ==================
@dp.chat_join_request()
async def approve_request(join_request: ChatJoinRequest):
    try:
        await join_request.approve()
    except:
        pass
# ============================================================


# ================== /adm ДЛЯ ВСЕХ ==================
@dp.message(F.text.lower().startswith("/adm"))
async def call_admins(message: Message):
    admins = await bot.get_chat_administrators(message.chat.id)
    mentions = []
    for admin in admins:
        u = admin.user
        if not u.is_bot:
            mentions.append(f"<a href='tg://user?id={u.id}'>{u.first_name}</a>")
    if mentions:
        await message.answer("🚨 Администраторы:\n" + " ".join(mentions), parse_mode="HTML")
    else:
        await message.answer("Администраторы не найдены")
# ============================================================


# ================== МУТ ==================
@dp.message(F.text.lower().startswith("мут"))
async def mute_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return await message.answer("Ответь на сообщение пользователя.")

    delta = parse_time(message.text)
    until_date = None
    if delta:
        until_date = datetime.utcnow() + delta

    try:
        await bot.restrict_chat_member(
            message.chat.id,
            message.reply_to_message.from_user.id,
            permissions=None,
            until_date=until_date
        )
        await message.answer("🔇 Пользователь замучен.")
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")
# ============================================================


# ================== РАЗМУТ ==================
@dp.message(F.text.lower().startswith("размут"))
async def unmute_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return await message.answer("Ответь на сообщение пользователя.")

    try:
        await bot.restrict_chat_member(
            message.chat.id,
            message.reply_to_message.from_user.id,
            permissions=Message.ChatPermissions(can_send_messages=True)
        )
        await message.answer(f"Время мута у @{message.reply_to_message.from_user.username} закончилось")
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")
# ============================================================


# ================== БАН ==================
@dp.message(F.text.lower().startswith("бан"))
async def ban_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return await message.answer("Ответь на сообщение пользователя.")

    try:
        await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await message.answer("🚫 Пользователь забанен.")
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")
# ============================================================


# ================== РАЗБАН ==================
@dp.message(F.text.lower().startswith("разбан"))
async def unban_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return await message.answer("Ответь на сообщение пользователя.")

    try:
        await bot.unban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await message.answer("Пользователь разбанен.")
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")
# ============================================================


async def main():
    await start_web()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
