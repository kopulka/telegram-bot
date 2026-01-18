import asyncio
import logging
import re
import aiosqlite
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ChatPermissions
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.utils.markdown import bold

TOKEN = "ВСТАВЬ_СЮДА_ТОКЕН"

logging.basicConfig(level=logging.INFO)

bot = Bot(TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

DB_PATH = "data.db"

# -------------------- DATABASE --------------------

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS punishments (
            user_id INTEGER,
            username TEXT,
            type TEXT,
            until TEXT,
            reason TEXT,
            admin TEXT
        )
        """)
        await db.commit()

# -------------------- HELPERS --------------------

async def is_admin(chat_id, user_id):
    member = await bot.get_chat_member(chat_id, user_id)
    return member.status in ["administrator", "creator"]

def parse_time(text):
    match = re.search(r"(\d+)\s*(мин|м|час|ч|день|д|нед|н)", text.lower())
    if not match:
        return None

    num = int(match.group(1))
    unit = match.group(2)

    if unit in ["мин", "м"]:
        return timedelta(minutes=num)
    if unit in ["час", "ч"]:
        return timedelta(hours=num)
    if unit in ["день", "д"]:
        return timedelta(days=num)
    if unit in ["нед", "н"]:
        return timedelta(weeks=num)

    return None

def extract_username(text):
    match = re.search(r"@(\w+)", text)
    return match.group(1) if match else None

# -------------------- START --------------------

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer("Бот работает.")

# -------------------- ADM CALL --------------------

@dp.message(F.text.lower().startswith("созыв"))
async def call_admins(message: Message):
    await message.answer("🚨 <b>ВЫЗОВ АДМИНИСТРАТОРОВ</b>")

# -------------------- MUTE --------------------

@dp.message(F.text.lower().startswith("мут"))
async def mute_handler(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    duration = parse_time(message.text)
    if not duration:
        await message.answer("Формат: мут 1 час причина")
        return

    reason = message.text.split(maxsplit=2)[-1]

    target = None

    if message.reply_to_message:
        target = message.reply_to_message.from_user
    else:
        username = extract_username(message.text)
        if not username:
            await message.answer("Нужно reply или @username")
            return
        members = await bot.get_chat_administrators(message.chat.id)
        for m in members:
            if m.user.username == username:
                target = m.user

    if not target:
        await message.answer("Пользователь не найден")
        return

    until = datetime.utcnow() + duration

    await bot.restrict_chat_member(
        message.chat.id,
        target.id,
        ChatPermissions(can_send_messages=False),
        until_date=until
    )

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO punishments VALUES (?, ?, ?, ?, ?, ?)",
            (target.id, target.username, "mute", until.isoformat(), reason, message.from_user.username)
        )
        await db.commit()

    await message.answer(
        f"‼️ Участник @{target.username} замучен до {until.strftime('%d.%m.%Y %H:%M')} админом (@{message.from_user.username})\n\nПричина: {reason}"
    )

# -------------------- UNMUTE --------------------

@dp.message(F.text.lower().startswith("размут"))
async def unmute_handler(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    target = None

    if message.reply_to_message:
        target = message.reply_to_message.from_user
    else:
        username = extract_username(message.text)
        if not username:
            await message.answer("Нужно reply или @username")
            return

    if not target:
        return

    await bot.restrict_chat_member(
        message.chat.id,
        target.id,
        ChatPermissions(can_send_messages=True)
    )

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM punishments WHERE user_id=? AND type='mute'", (target.id,))
        await db.commit()

    await message.answer(f"✅ Участник @{target.username} размучен")

# -------------------- BAN --------------------

@dp.message(F.text.lower().startswith("бан"))
async def ban_handler(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    reason = message.text.split(maxsplit=1)[-1]

    if not message.reply_to_message:
        await message.answer("Ответь на сообщение")
        return

    target = message.reply_to_message.from_user

    await bot.ban_chat_member(message.chat.id, target.id)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO punishments VALUES (?, ?, ?, ?, ?, ?)",
            (target.id, target.username, "ban", None, reason, message.from_user.username)
        )
        await db.commit()

    await message.answer(
        f"‼️ Участник @{target.username} забанен админом (@{message.from_user.username})\n\nПричина: {reason}"
    )

# -------------------- UNBAN --------------------

@dp.message(F.text.lower().startswith("разбан"))
async def unban_handler(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        await message.answer("Ответь на сообщение")
        return

    target = message.reply_to_message.from_user

    await bot.unban_chat_member(message.chat.id, target.id)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM punishments WHERE user_id=? AND type='ban'", (target.id,))
        await db.commit()

    await message.answer(f"✅ Участник @{target.username} разбанен")

# -------------------- REASON --------------------

@dp.message(F.text.lower().startswith("причина"))
async def reason_handler(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    username = extract_username(message.text)
    if not username:
        await message.answer("Формат: причина @username")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM punishments WHERE username=?", (username,)) as cur:
            row = await cur.fetchone()

    if not row:
        await message.answer("⭐️ Участник не находится в муте или бане")
        return

    _, username, ptype, until, reason, admin = row

    if ptype == "mute":
        await message.answer(
            f"‼️ Участник @{username} замучен до {until}\n\nПричина: {reason}"
        )
    else:
        await message.answer(
            f"‼️ Участник @{username} забанен\n\nПричина: {reason}"
        )

# -------------------- MAIN --------------------

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
