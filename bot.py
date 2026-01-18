import asyncio
import os
import re
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, ChatJoinRequest, ChatPermissions
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest

import aiosqlite
from aiohttp import web

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN not set")

bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher()

# ================== DATABASE ==================

async def init_db():
    async with aiosqlite.connect("punishments.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS punishments (
                user_id INTEGER,
                chat_id INTEGER,
                type TEXT,
                until TEXT,
                reason TEXT,
                admin TEXT
            )
        """)
        await db.commit()

async def set_punishment(user_id, chat_id, p_type, until, reason, admin):
    async with aiosqlite.connect("punishments.db") as db:
        await db.execute("DELETE FROM punishments WHERE user_id=? AND chat_id=?", (user_id, chat_id))
        await db.execute(
            "INSERT INTO punishments VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, chat_id, p_type, until, reason, admin)
        )
        await db.commit()

async def clear_punishment(user_id, chat_id):
    async with aiosqlite.connect("punishments.db") as db:
        await db.execute("DELETE FROM punishments WHERE user_id=? AND chat_id=?", (user_id, chat_id))
        await db.commit()

async def get_punishment(user_id, chat_id):
    async with aiosqlite.connect("punishments.db") as db:
        async with db.execute(
            "SELECT type, until, reason, admin FROM punishments WHERE user_id=? AND chat_id=?",
            (user_id, chat_id)
        ) as cursor:
            return await cursor.fetchone()

# ================== UTILS ==================

TIME_RE = re.compile(r"(\d+)\s*(мин|минута|минут|час|часа|часов|дн|день|дня|дней)", re.I)

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
    if unit.startswith("д"):
        return timedelta(days=value)
    return None

async def is_admin(message: Message):
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]

async def get_target(message: Message):
    if message.reply_to_message:
        return message.reply_to_message.from_user

    if message.entities:
        for ent in message.entities:
            if ent.type == "text_mention":
                return ent.user

    parts = message.text.split()
    for p in parts:
        if p.startswith("@"):
            return None  # Telegram не даёт надёжно получить user по username
    return None

# ================== WEB (Render) ==================

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

# ================== HANDLERS ==================

@dp.chat_join_request()
async def approve_request(join_request: ChatJoinRequest):
    await join_request.approve()

@dp.message(Command("adm"))
async def call_admins(message: Message):
    admins = await bot.get_chat_administrators(message.chat.id)
    mentions = []
    for admin in admins:
        u = admin.user
        if not u.is_bot:
            mentions.append(f"@{u.username}" if u.username else u.full_name)
    await message.answer(f"<b>🚨 СОЗЫВ АДМИНОВ:</b>\n" + ", ".join(mentions))

# ================== MUTE ==================

@dp.message(F.text.lower().startswith("мут"))
async def mute_user(message: Message):
    if not await is_admin(message):
        return

    target = await get_target(message)
    if not target:
        return await message.answer("Используй ответ на сообщение.")

    delta = parse_time(message.text)
    if not delta:
        return await message.answer("Формат: мут 1 час причина")

    reason = message.text.split()[-1]
    until = datetime.utcnow() + delta

    try:
        await bot.restrict_chat_member(
            message.chat.id,
            target.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until
        )

        await set_punishment(
            target.id,
            message.chat.id,
            "mute",
            until.isoformat(),
            reason,
            message.from_user.username or message.from_user.full_name
        )

        await message.answer(
            f"‼️ <b>Участник @{target.username} замучен до {until.strftime('%d.%m.%Y %H:%M')}</b>\n"
            f"<b>Админ:</b> @{message.from_user.username}\n"
            f"<b>Причина:</b> {reason}"
        )
    except TelegramBadRequest as e:
        await message.answer(str(e))

# ================== UNMUTE ==================

@dp.message(F.text.lower().startswith("размут"))
async def unmute_user(message: Message):
    if not await is_admin(message):
        return

    target = await get_target(message)
    if not target:
        return await message.answer("Используй ответ на сообщение.")

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

        await clear_punishment(target.id, message.chat.id)

        await message.answer(
            f"✅ <b>Участник @{target.username} размучен</b>\n"
            f"<b>Админ:</b> @{message.from_user.username}"
        )

    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")

# ================== BAN ==================

@dp.message(F.text.lower().startswith("разбан"))
async def unban_user(message: Message):
    if not await is_admin(message):
        return

    target = await get_target(message)
    if not target:
        return await message.answer("Используй ответ на сообщение.")

    try:
        await bot.unban_chat_member(
            message.chat.id,
            target.id,
            only_if_banned=True
        )

        await clear_punishment(target.id, message.chat.id)

        await message.answer(
            f"✅ <b>Участник @{target.username} разбанен</b>\n"
            f"<b>Админ:</b> @{message.from_user.username}"
        )

    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")

# ================== UNBAN ==================

@dp.message(F.text.lower().startswith("разбан"))
async def unban_user(message: Message):
    if not await is_admin(message):
        return

    target = await get_target(message)
    if not target:
        return await message.answer("Используй ответ на сообщение.")

    try:
        await bot.unban_chat_member(message.chat.id, target.id)
        await clear_punishment(target.id, message.chat.id)

        await message.answer(
            f"✅ <b>Участник @{target.username} разбанен</b>\n"
            f"<b>Админ:</b> @{message.from_user.username}"
        )
    except TelegramBadRequest as e:
        await message.answer(str(e))

# ================== REASON ==================

@dp.message(F.text.lower().startswith("причина"))
async def reason_cmd(message: Message):
    if not await is_admin(message):
        return

    target = await get_target(message)
    if not target:
        return await message.answer("Используй ответ на сообщение.")

    data = await get_punishment(target.id, message.chat.id)
    if not data:
        return await message.answer("⭐️ Участник не находится в муте или бане")

    p_type, until, reason, admin = data

    if p_type == "mute":
        until_dt = datetime.fromisoformat(until)
        await message.answer(
            f"‼️ <b>Участник @{target.username} в муте до {until_dt.strftime('%d.%m.%Y %H:%M')}</b>\n"
            f"<b>Админ:</b> @{admin}\n"
            f"<b>Причина:</b> {reason}"
        )
    else:
        await message.answer(
            f"‼️ <b>Участник @{target.username} в бане</b>\n"
            f"<b>Админ:</b> @{admin}\n"
            f"<b>Причина:</b> {reason}"
        )

# ================== MAIN ==================

async def main():
    await init_db()
    await start_web()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
