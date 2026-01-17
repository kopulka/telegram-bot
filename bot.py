import asyncio
import os
import re
from datetime import timedelta, datetime
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, ChatJoinRequest, ChatPermissions
from aiogram.exceptions import TelegramBadRequest

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN not set")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ================= WEB SERVER FOR RENDER =================
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
# =======================================================


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


# ================= AUTO APPROVE =================
@dp.chat_join_request()
async def approve_request(join_request: ChatJoinRequest):
    try:
        await join_request.approve()
    except:
        pass
# ==============================================


# ================= /adm =================
@dp.message(F.text.lower().startswith("/adm"))
async def call_admins(message: Message):
    admins = await bot.get_chat_administrators(message.chat.id)
    mentions = []
    for admin in admins:
        u = admin.user
        if not u.is_bot:
            mentions.append(f"<a href='tg://user?id={u.id}'>@{u.username or u.first_name}</a>")

    if mentions:
        await message.answer(
            f"<b>🚨 ВЫЗЫВ АДМИНИСТРАТОРОВ / ГАРАНТОВ</b>\n" + " ".join(mentions),
            parse_mode="HTML"
        )
# ======================================


# ================= MUTE =================
@dp.message(F.text.lower().startswith("мут"))
async def mute_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return await message.answer("<b>Ответь на сообщение пользователя.</b>", parse_mode="HTML")

    delta = parse_time(message.text)
    until_date = None
    end_time_text = "навсегда"

    if delta:
        until_date = datetime.utcnow() + delta
        end_time_text = until_date.strftime("%d.%m.%Y %H:%M")

    target = message.reply_to_message.from_user
    admin = message.from_user

    try:
        await bot.restrict_chat_member(
            message.chat.id,
            target.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )

        await message.answer(
            f"<b>‼️ Участник @{target.username or target.first_name} замучен до {end_time_text} администратором (@{admin.username or admin.first_name})</b>",
            parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        await message.answer(f"<b>Ошибка: {e}</b>", parse_mode="HTML")
# =======================================


# ================= UNMUTE =================
@dp.message(F.text.lower().startswith("размут"))
async def unmute_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return await message.answer("<b>Ответь на сообщение пользователя.</b>", parse_mode="HTML")

    target = message.reply_to_message.from_user
    admin = message.from_user

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
            f"<b>✅ Участник @{target.username or target.first_name} был размучен администратором (@{admin.username or admin.first_name})</b>",
            parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        await message.answer(f"<b>Ошибка: {e}</b>", parse_mode="HTML")
# =========================================


# ================= BAN =================
@dp.message(F.text.lower().startswith("бан"))
async def ban_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return await message.answer("<b>Ответь на сообщение пользователя.</b>", parse_mode="HTML")

    target = message.reply_to_message.from_user
    admin = message.from_user

    try:
        await bot.ban_chat_member(message.chat.id, target.id)

        await message.answer(
            f"<b>‼️ Участник @{target.username or target.first_name} забанен администратором (@{admin.username or admin.first_name})</b>",
            parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        await message.answer(f"<b>Ошибка: {e}</b>", parse_mode="HTML")
# ======================================


# ================= UNBAN =================
@dp.message(F.text.lower().startswith("разбан"))
async def unban_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return await message.answer("<b>Ответь на сообщение пользователя.</b>", parse_mode="HTML")

    target = message.reply_to_message.from_user

    try:
        await bot.unban_chat_member(message.chat.id, target.id)

        await message.answer(
            f"<b>✅ Участник @{target.username or target.first_name} разбанен</b>",
            parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        await message.answer(f"<b>Ошибка: {e}</b>", parse_mode="HTML")
# ========================================


async def main():
    await start_web()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
