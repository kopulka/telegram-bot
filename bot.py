import asyncio
import os
import re
import aiosqlite
from datetime import datetime, timedelta
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ChatJoinRequest
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN not set")

bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher()

DB_PATH = "data.db"

TIME_RE = re.compile(r"(\d+)(м|ч|д|н)", re.IGNORECASE)

# ------------------ WEB SERVER (Render) ------------------

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

# ------------------ DATABASE ------------------

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sanctions (
                user_id INTEGER,
                chat_id INTEGER,
                type TEXT,
                until TEXT,
                reason TEXT,
                admin TEXT
            )
        """)
        await db.commit()

# ------------------ HELPERS ------------------

async def is_admin(chat_id, user_id):
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except:
        return False

def parse_time(text):
    match = TIME_RE.search(text)
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2).lower()
    if unit == "м":
        return timedelta(minutes=value)
    if unit == "ч":
        return timedelta(hours=value)
    if unit == "д":
        return timedelta(days=value)
    if unit == "н":
        return timedelta(days=value * 7)
    return None

def format_time(dt):
    return dt.strftime("%d.%m.%Y %H:%M")

# ------------------ AUTO APPROVE ------------------

@dp.chat_join_request()
async def approve_request(join_request: ChatJoinRequest):
    await join_request.approve()

# ------------------ ADM CALL ------------------

@dp.message(Command("adm"))
async def call_admins(message: Message):
    admins = await bot.get_chat_administrators(message.chat.id)
    mentions = []
    for admin in admins:
        u = admin.user
        if not u.is_bot:
            if u.username:
                mentions.append(f"@{u.username}")
            else:
                mentions.append(u.full_name)

    if mentions:
        await message.answer(f"<b>🚨 СОЗЫВ АДМИНИСТРАТОРОВ: {', '.join(mentions)}</b>")
    else:
        await message.answer("<b>Администраторы не найдены</b>")

# ------------------ SANCTIONS ------------------

async def save_sanction(user_id, chat_id, s_type, until, reason, admin):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM sanctions WHERE user_id=? AND chat_id=?", (user_id, chat_id))
        await db.execute(
            "INSERT INTO sanctions VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, chat_id, s_type, until, reason, admin)
        )
        await db.commit()

async def remove_sanction(user_id, chat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM sanctions WHERE user_id=? AND chat_id=?", (user_id, chat_id))
        await db.commit()

async def get_sanction(user_id, chat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT type, until, reason, admin FROM sanctions WHERE user_id=? AND chat_id=?",
            (user_id, chat_id)
        ) as cursor:
            return await cursor.fetchone()

# ------------------ MUTE ------------------

@dp.message(F.text.lower().startswith("мут"))
async def mute_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return await message.answer("<b>Ответь на сообщение пользователя.</b>")

    target = message.reply_to_message.from_user
    admin = message.from_user.username or message.from_user.full_name

    delta = parse_time(message.text)
    if not delta:
        return await message.answer("<b>Укажи время: 10м, 3ч, 2д, 1н</b>")

    until = datetime.utcnow() + delta
    reason = message.text.split(maxsplit=2)[-1]

    try:
        await bot.restrict_chat_member(message.chat.id, target.id, permissions=None, until_date=until)
        await save_sanction(target.id, message.chat.id, "mute", until.isoformat(), reason, admin)

        await message.answer(
            f"<b>‼️Участник @{target.username or target.full_name} замучен до {format_time(until)} админом (@{admin})\n\nПричина: {reason}</b>"
        )
    except TelegramBadRequest as e:
        await message.answer(str(e))

# ------------------ UNMUTE ------------------

@dp.message(F.text.lower().startswith("размут"))
async def unmute_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return await message.answer("<b>Ответь на сообщение пользователя.</b>")

    target = message.reply_to_message.from_user
    admin = message.from_user.username or message.from_user.full_name

    try:
        await bot.restrict_chat_member(message.chat.id, target.id, permissions=None)
        await remove_sanction(target.id, message.chat.id)

        await message.answer(
            f"<b>✅ Участник @{target.username or target.full_name} размучен администратором (@{admin})</b>"
        )
    except TelegramBadRequest as e:
        await message.answer(str(e))

# ------------------ BAN ------------------

@dp.message(F.text.lower().startswith("бан"))
async def ban_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return await message.answer("<b>Ответь на сообщение пользователя.</b>")

    target = message.reply_to_message.from_user
    admin = message.from_user.username or message.from_user.full_name
    reason = message.text.split(maxsplit=1)[-1]

    try:
        await bot.ban_chat_member(message.chat.id, target.id)
        await save_sanction(target.id, message.chat.id, "ban", None, reason, admin)

        await message.answer(
            f"<b>‼️Участник @{target.username or target.full_name} забанен админом (@{admin})\n\nПричина: {reason}</b>"
        )
    except TelegramBadRequest as e:
        await message.answer(str(e))

# ------------------ UNBAN ------------------

@dp.message(F.text.lower().startswith("разбан"))
async def unban_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return await message.answer("<b>Ответь на сообщение пользователя.</b>")

    target = message.reply_to_message.from_user
    admin = message.from_user.username or message.from_user.full_name

    try:
        await bot.unban_chat_member(message.chat.id, target.id)
        await remove_sanction(target.id, message.chat.id)

        await message.answer(
            f"<b>✅ Участник @{target.username or target.full_name} разбанен администратором (@{admin})</b>"
        )
    except TelegramBadRequest as e:
        await message.answer(str(e))

# ------------------ REASON ------------------

@dp.message(F.text.lower().startswith("причина"))
async def reason_cmd(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return await message.answer("<b>Ответь на сообщение пользователя.</b>")

    target = message.reply_to_message.from_user
    data = await get_sanction(target.id, message.chat.id)

    if not data:
        return await message.answer("<b>⭐️ Участник не находится в муте или бане</b>")

    s_type, until, reason, admin = data

    if s_type == "mute":
        until_dt = datetime.fromisoformat(until)
        await message.answer(
            f"<b>‼️Участник @{target.username or target.full_name} замучен до {format_time(until_dt)} администратором (@{admin})\n\nПричина: {reason}</b>"
        )
    else:
        await message.answer(
            f"<b>‼️Участник @{target.username or target.full_name} забанен администратором (@{admin})\n\nПричина: {reason}</b>"
        )

# ------------------ START ------------------

async def main():
    await init_db()
    await start_web()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
