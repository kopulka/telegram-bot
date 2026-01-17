import asyncio
import os
import re
import aiosqlite
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ChatPermissions, ChatJoinRequest
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties

from aiohttp import web

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN not set")

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

DB_PATH = "punishments.db"


# ================== WEB SERVER (Render) ==================
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


# ================== DATABASE ==================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS punishments (
            user_id INTEGER,
            username TEXT,
            admin_id INTEGER,
            admin_username TEXT,
            type TEXT,
            reason TEXT,
            until TEXT
        )
        """)
        await db.commit()


# ================== HELPERS ==================
async def is_admin(chat_id: int, user_id: int):
    admins = await bot.get_chat_administrators(chat_id)
    return any(a.user.id == user_id for a in admins)


def parse_time(text: str):
    match = re.search(r"(\d+)\s*(мин|минута|минут|час|часа|часов|день|дня|дней|неделя|недели|недель)", text.lower())
    if not match:
        return None

    num = int(match.group(1))
    unit = match.group(2)

    if "мин" in unit:
        return timedelta(minutes=num)
    if "час" in unit:
        return timedelta(hours=num)
    if "день" in unit:
        return timedelta(days=num)
    if "нед" in unit:
        return timedelta(weeks=num)

    return None


async def get_user_from_text(message: Message):
    if message.reply_to_message:
        return message.reply_to_message.from_user

    match = re.search(r"@(\w+)", message.text)
    if match:
        username = match.group(1)
        try:
            user = await bot.get_chat_member(message.chat.id, username)
            return user.user
        except:
            return None

    return None


# ================== JOIN AUTO APPROVE ==================
@dp.chat_join_request()
async def approve_request(join_request: ChatJoinRequest):
    await join_request.approve()


# ================== ADM CALL ==================
@dp.message(F.text.lower().startswith("/adm"))
async def call_admins(message: Message):
    admins = await bot.get_chat_administrators(message.chat.id)
    mentions = []
    for admin in admins:
        if not admin.user.is_bot:
            mentions.append(f"@{admin.user.username}" if admin.user.username else admin.user.full_name)

    if mentions:
        await message.answer(f"<b>🚨 СОЗЫВ АДМИНИСТРАЦИИ:</b>\n" + ", ".join(mentions))
    else:
        await message.answer("<b>Администраторы не найдены</b>")


# ================== MUTE ==================
@dp.message(F.text.lower().startswith("мут"))
async def mute_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    user = await get_user_from_text(message)
    if not user:
        return await message.answer("<b>Не удалось найти пользователя</b>")

    delta = parse_time(message.text)
    if not delta:
        return await message.answer("<b>Укажи время: мут 1 час</b>")

    reason_match = re.split(r"\n", message.text, 1)
    reason = reason_match[1] if len(reason_match) > 1 else "Не указана"

    until = datetime.now(timezone.utc) + delta

    await bot.restrict_chat_member(
        message.chat.id,
        user.id,
        ChatPermissions(can_send_messages=False),
        until_date=until
    )

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM punishments WHERE user_id=?", (user.id,))
        await db.execute("""
        INSERT INTO punishments VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user.id, user.username, message.from_user.id, message.from_user.username, "mute", reason, until.isoformat()))
        await db.commit()

    await message.answer(
        f"<b>‼️Участник @{user.username} замучен до {until.strftime('%d.%m.%Y %H:%M')}</b>\n"
        f"<b>Админ:</b> @{message.from_user.username}\n"
        f"<b>Причина:</b> {reason}"
    )


# ================== BAN ==================
@dp.message(F.text.lower().startswith("бан"))
async def ban_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    user = await get_user_from_text(message)
    if not user:
        return await message.answer("<b>Не удалось найти пользователя</b>")

    reason_match = re.split(r"\n", message.text, 1)
    reason = reason_match[1] if len(reason_match) > 1 else "Не указана"

    await bot.ban_chat_member(message.chat.id, user.id)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM punishments WHERE user_id=?", (user.id,))
        await db.execute("""
        INSERT INTO punishments VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user.id, user.username, message.from_user.id, message.from_user.username, "ban", reason, None))
        await db.commit()

    await message.answer(
        f"<b>‼️Участник @{user.username} забанен</b>\n"
        f"<b>Админ:</b> @{message.from_user.username}\n"
        f"<b>Причина:</b> {reason}"
    )


# ================== REASON ==================
@dp.message(F.text.lower().startswith("причина"))
async def reason_cmd(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    user = await get_user_from_text(message)
    if not user:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM punishments WHERE user_id=?", (user.id,)) as cursor:
            row = await cursor.fetchone()

    if not row:
        return await message.answer(f"<b>⭐️Участник @{user.username} не находится в муте или бане</b>")

    _, _, _, admin_username, ptype, reason, until = row

    if ptype == "mute":
        until_dt = datetime.fromisoformat(until)
        text = f"<b>МУТ до {until_dt.strftime('%d.%m.%Y %H:%M')}</b>"
    else:
        text = "<b>БАН</b>"

    await message.answer(
        f"<b>‼️Участник @{user.username}</b>\n"
        f"{text}\n"
        f"<b>Админ:</b> @{admin_username}\n"
        f"<b>Причина:</b> {reason}"
    )


# ================== START ==================
async def main():
    await init_db()
    await start_web()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
