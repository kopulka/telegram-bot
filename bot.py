import asyncio
import os
import re
import aiosqlite
from datetime import datetime, timedelta
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, ChatJoinRequest
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN not set")

bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

DB_NAME = "punishments.db"

# ---------- WEB SERVER FOR RENDER ----------
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
# ------------------------------------------

TIME_RE = re.compile(r"(\d+)\s*(мин|минут|минута|час|часа|часов|день|дня|дней|неделя|недели|недель)", re.I)

def parse_time(text):
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

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
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

# ---------- AUTO APPROVE ----------
@dp.chat_join_request()
async def approve_request(join_request: ChatJoinRequest):
    await join_request.approve()

# ---------- ADM CALL ----------
@dp.message(Command("adm"))
async def call_admins(message: Message):
    admins = await bot.get_chat_administrators(message.chat.id)
    mentions = []
    for admin in admins:
        u = admin.user
        if not u.is_bot:
            mentions.append(f"@{u.username}" if u.username else u.first_name)
    await message.answer(f"<b>🚨 СОЗЫВ АДМИНОВ:</b> {', '.join(mentions)}")

# ---------- BAN ----------
@dp.message(F.text.lower().startswith("бан"))
async def ban_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return await message.answer("Ответь на сообщение пользователя.")

    target = message.reply_to_message.from_user
    reason = message.text.replace("бан", "").strip() or "Не указана"

    try:
        await bot.ban_chat_member(message.chat.id, target.id)

        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "INSERT INTO punishments VALUES (?, ?, ?, ?, ?, ?)",
                (target.id, message.chat.id, "ban", "forever", reason, message.from_user.username)
            )
            await db.commit()

        await message.answer(
            f"<b>‼️ Участник @{target.username} забанен админом (@{message.from_user.username})</b>\n\n"
            f"<b>Причина:</b> {reason}"
        )
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")

# ---------- UNBAN ----------
@dp.message(F.text.lower().startswith("разбан"))
async def unban_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return await message.answer("Ответь на сообщение пользователя.")

    target = message.reply_to_message.from_user

    try:
        await bot.unban_chat_member(message.chat.id, target.id)

        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "DELETE FROM punishments WHERE user_id=? AND chat_id=? AND type='ban'",
                (target.id, message.chat.id)
            )
            await db.commit()

        await message.answer(
            f"<b>✅ Участник @{target.username} разбанен админом (@{message.from_user.username})</b>"
        )
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")

# ---------- MUTE ----------
@dp.message(F.text.lower().startswith("мут"))
async def mute_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return await message.answer("Ответь на сообщение пользователя.")

    target = message.reply_to_message.from_user
    delta = parse_time(message.text)
    if not delta:
        return await message.answer("Укажи время: например `мут 10 минут`")

    reason = message.text.split("\n", 1)[1] if "\n" in message.text else "Не указана"

    until = datetime.utcnow() + delta

    try:
        await bot.restrict_chat_member(
            message.chat.id,
            target.id,
            permissions=None,
            until_date=until
        )

        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "INSERT INTO punishments VALUES (?, ?, ?, ?, ?, ?)",
                (target.id, message.chat.id, "mute", until.isoformat(), reason, message.from_user.username)
            )
            await db.commit()

        await message.answer(
            f"<b>‼️ Участник @{target.username} замучен до {until.strftime('%d.%m.%Y %H:%M')}</b>\n"
            f"<b>Админ:</b> @{message.from_user.username}\n"
            f"<b>Причина:</b> {reason}"
        )
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")

# ---------- UNMUTE ----------
@dp.message(F.text.lower().startswith("размут"))
async def unmute_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return await message.answer("Ответь на сообщение пользователя.")

    target = message.reply_to_message.from_user

    try:
        await bot.restrict_chat_member(
            message.chat.id,
            target.id,
            permissions=None
        )

        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "DELETE FROM punishments WHERE user_id=? AND chat_id=? AND type='mute'",
                (target.id, message.chat.id)
            )
            await db.commit()

        await message.answer(
            f"<b>✅ Участник @{target.username} размучен админом (@{message.from_user.username})</b>"
        )
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")

# ---------- START ----------
async def main():
    await init_db()
    await start_web()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
