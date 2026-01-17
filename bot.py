import asyncio
import os
import re
from datetime import datetime, timedelta
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, ChatPermissions, ChatJoinRequest
from aiogram.exceptions import TelegramBadRequest

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN not set")

bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher()

# ================== WEB SERVER FOR RENDER ==================
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

# ==========================================================

TIME_RE = re.compile(r"(\d+)\s*(мин|минута|минут|час|часа|часов|день|дня|дней|неделя|недель)", re.I)

def parse_time(text: str):
    m = TIME_RE.search(text)
    if not m:
        return None

    value = int(m.group(1))
    unit = m.group(2).lower()

    if "мин" in unit:
        return timedelta(minutes=value)
    if "час" in unit:
        return timedelta(hours=value)
    if "дн" in unit:
        return timedelta(days=value)
    if "нед" in unit:
        return timedelta(days=value * 7)

    return None

async def is_admin(chat_id, user_id):
    admins = await bot.get_chat_administrators(chat_id)
    return any(a.user.id == user_id for a in admins)

# ================== AUTO APPROVE ==================
@dp.chat_join_request()
async def approve_request(join_request: ChatJoinRequest):
    await join_request.approve()

# ================== /adm ==================
@dp.message(Command("adm"))
async def call_admins(message: Message):
    admins = await bot.get_chat_administrators(message.chat.id)
    mentions = []
    for admin in admins:
        u = admin.user
        if not u.is_bot:
            mentions.append(f"<a href='tg://user?id={u.id}'>{u.first_name}</a>")
    if mentions:
        await message.answer("🚨 <b>ВЫЗОВ АДМИНИСТРАТОРОВ:</b>\n" + ", ".join(mentions))
    else:
        await message.answer("Администраторы не найдены")

# ================== MUTE ==================
@dp.message(F.text.lower().startswith("мут"))
async def mute_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        await message.answer("Ответь на сообщение пользователя.")
        return

    delta = parse_time(message.text)
    if not delta:
        await message.answer("Укажи время: мут 10 минут / мут 2 часа / мут 3 дня")
        return

    until_date = datetime.utcnow() + delta
    target = message.reply_to_message.from_user

    try:
        await bot.restrict_chat_member(
            message.chat.id,
            target.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )

        await message.answer(
            f"‼️ <b>Участник @{target.username} замучен до {until_date.strftime('%d.%m.%Y %H:%M')}</b>\n"
            f"Админ: @{message.from_user.username}"
        )
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")

# ================== UNMUTE ==================
@dp.message(F.text.lower().startswith("размут"))
async def unmute_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        await message.answer("Ответь на сообщение пользователя.")
        return

    target = message.reply_to_message.from_user

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

        await message.answer(
            f"✅ <b>Участник @{target.username} был размучен</b>\n"
            f"Админ: @{message.from_user.username}"
        )
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")

# ================== BAN ==================
@dp.message(F.text.lower().startswith("бан"))
async def ban_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        await message.answer("Ответь на сообщение пользователя.")
        return

    target = message.reply_to_message.from_user

    try:
        await bot.ban_chat_member(message.chat.id, target.id)

        await message.answer(
            f"‼️ <b>Участник @{target.username} забанен</b>\n"
            f"Админ: @{message.from_user.username}"
        )
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")

# ================== UNBAN ==================
@dp.message(F.text.lower().startswith("разбан"))
async def unban_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        await message.answer("Ответь на сообщение пользователя.")
        return

    target = message.reply_to_message.from_user

    try:
        await bot.unban_chat_member(message.chat.id, target.id)

        await message.answer(
            f"✅ <b>Участник @{target.username} разбанен</b>\n"
            f"Админ: @{message.from_user.username}"
        )
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")

# ================== START ==================
async def main():
    await start_web()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
