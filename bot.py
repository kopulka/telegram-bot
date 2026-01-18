import asyncio
import re
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command
import aiosqlite

TOKEN = "ВСТАВЬ_ТОКЕН"

ADMINS = {123456789}  # <-- ВСТАВЬ ID АДМИНОВ

bot = Bot(TOKEN, parse_mode="HTML")
dp = Dispatcher()

DB = "punishments.db"


def parse_time(text: str):
    match = re.search(r"(\d+)\s*(минута|минут|минуты|час|часа|часов|день|дня|дней|неделя|недели|недель)", text)
    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)

    if "мин" in unit:
        return timedelta(minutes=value)
    if "час" in unit:
        return timedelta(hours=value)
    if "день" in unit:
        return timedelta(days=value)
    if "недел" in unit:
        return timedelta(weeks=value)

    return None


async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS punishments (
            username TEXT PRIMARY KEY,
            type TEXT,
            until TEXT,
            admin TEXT,
            reason TEXT
        )
        """)
        await db.commit()


def is_admin(user_id):
    return user_id in ADMINS


@dp.message(Command("start"))
async def start(m: Message):
    await m.answer("Бот запущен.")


@dp.message(F.text.lower().startswith("мут"))
async def mute_cmd(m: Message):
    if not is_admin(m.from_user.id):
        return

    if not m.reply_to_message:
        return

    target = m.reply_to_message.from_user
    username = f"@{target.username}" if target.username else target.full_name

    delta = parse_time(m.text.lower())
    if not delta:
        await m.answer("Не могу распознать время.")
        return

    reason = m.text.split("\n", 1)[1] if "\n" in m.text else "Не указана"

    until = datetime.utcnow() + delta
    until_str = until.strftime("%d.%m.%Y %H:%M")

    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "REPLACE INTO punishments VALUES (?, ?, ?, ?, ?)",
            (username.lower(), "mute", until_str, f"@{m.from_user.username}", reason)
        )
        await db.commit()

    await m.answer(
        f"‼️ <b>Участник {username} замучен до {until_str} админом (@{m.from_user.username})</b>\n\n"
        f"причина: <b>{reason}</b>"
    )


@dp.message(F.text.lower().startswith("бан"))
async def ban_cmd(m: Message):
    if not is_admin(m.from_user.id):
        return

    if not m.reply_to_message:
        return

    target = m.reply_to_message.from_user
    username = f"@{target.username}" if target.username else target.full_name

    reason = m.text.split("\n", 1)[1] if "\n" in m.text else "Не указана"

    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "REPLACE INTO punishments VALUES (?, ?, ?, ?, ?)",
            (username.lower(), "ban", "-", f"@{m.from_user.username}", reason)
        )
        await db.commit()

    await m.answer(
        f"‼️ <b>Участник {username} забанен админом (@{m.from_user.username})</b>\n\n"
        f"Причина: <b>{reason}</b>"
    )


@dp.message(F.text.lower().startswith("размут"))
async def unmute_cmd(m: Message):
    if not is_admin(m.from_user.id):
        return

    parts = m.text.split()
    if len(parts) < 2:
        return

    username = parts[1].lower()

    async with aiosqlite.connect(DB) as db:
        await db.execute("DELETE FROM punishments WHERE username = ? AND type = 'mute'", (username,))
        await db.commit()

    await m.answer(f"✅ <b>Участник {username} был размучен</b>")


@dp.message(F.text.lower().startswith("разбан"))
async def unban_cmd(m: Message):
    if not is_admin(m.from_user.id):
        return

    parts = m.text.split()
    if len(parts) < 2:
        return

    username = parts[1].lower()

    async with aiosqlite.connect(DB) as db:
        await db.execute("DELETE FROM punishments WHERE username = ? AND type = 'ban'", (username,))
        await db.commit()

    await m.answer(f"✅ <b>Участник {username} был разбанен</b>")


@dp.message(F.text.lower().startswith("причина"))
async def reason_cmd(m: Message):
    if not is_admin(m.from_user.id):
        return

    parts = m.text.split()
    if len(parts) < 2:
        return

    username = parts[1].lower()

    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT type, until, admin, reason FROM punishments WHERE username = ?", (username,)) as cur:
            row = await cur.fetchone()

    if not row:
        await m.answer("⭐️ <b>Участник не находится в бане или муте</b>")
        return

    p_type, until, admin, reason = row

    if p_type == "mute":
        await m.answer(
            f"‼️ <b>Участник {username} замучен до {until} админом ({admin})</b>\n\n"
            f"причина: <b>{reason}</b>"
        )
    else:
        await m.answer(
            f"‼️ <b>Участник {username} забанен админом ({admin})</b>\n\n"
            f"Причина: <b>{reason}</b>"
        )


async def main():
    await init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
