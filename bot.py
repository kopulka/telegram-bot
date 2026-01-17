import asyncio
import os
import re
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, ChatPermissions
from aiohttp import web

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN not set")

bot = Bot(TOKEN)
dp = Dispatcher()

# ---------------- WEB SERVER (для Render) ----------------

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

# ---------------- ВСПОМОГАТЕЛЬНОЕ ----------------

TIME_UNITS = {
    "минута": 1,
    "минуты": 1,
    "минут": 1,
    "час": 60,
    "часа": 60,
    "часов": 60,
    "день": 1440,
    "дня": 1440,
    "дней": 1440,
    "неделя": 10080,
    "недели": 10080,
    "недель": 10080,
}

time_regex = re.compile(r"(\d+)\s*(минута|минуты|минут|час|часа|часов|день|дня|дней|неделя|недели|недель)", re.I)

async def is_admin(chat_id, user_id):
    member = await bot.get_chat_member(chat_id, user_id)
    return member.status in ["administrator", "creator"]

async def get_user_from_message(message: Message):
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

def parse_time(text):
    match = time_regex.search(text.lower())
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2)
    minutes = value * TIME_UNITS[unit]
    return timedelta(minutes=minutes)

# ---------------- /ADM ----------------

@dp.message(F.text.lower().startswith("/adm"))
async def call_admins(message: Message):
    admins = await bot.get_chat_administrators(message.chat.id)
    mentions = []
    for admin in admins:
        if not admin.user.is_bot:
            mentions.append(f"<a href='tg://user?id={admin.user.id}'>{admin.user.first_name}</a>")

    if mentions:
        await message.answer("🚨 Администраторы:\n" + " ".join(mentions), parse_mode="HTML")
    else:
        await message.answer("Администраторы не найдены")

# ---------------- МУТ ----------------

@dp.message(F.text.lower().startswith("мут"))
async def mute_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    user = await get_user_from_message(message)
    if not user:
        await message.reply("Не удалось найти пользователя.")
        return

    duration = parse_time(message.text)
    if not duration:
        await message.reply("Укажи время: например `мут @user 3 часа`")
        return

    until = datetime.utcnow() + duration

    await bot.restrict_chat_member(
        message.chat.id,
        user.id,
        ChatPermissions(can_send_messages=False),
        until_date=until
    )

    await message.answer(f"🔇 @{user.username or user.first_name} замучен на {duration}")

    async def unmute_later():
        await asyncio.sleep(duration.total_seconds())
        try:
            await bot.restrict_chat_member(
                message.chat.id,
                user.id,
                ChatPermissions(can_send_messages=True)
            )
            await message.answer(f"🔊 Время мута у @{user.username or user.first_name} закончилось")
        except:
            pass

    asyncio.create_task(unmute_later())

# ---------------- РАЗМУТ ----------------

@dp.message(F.text.lower().startswith("размут"))
async def unmute_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    user = await get_user_from_message(message)
    if not user:
        await message.reply("Не удалось найти пользователя.")
        return

    await bot.restrict_chat_member(
        message.chat.id,
        user.id,
        ChatPermissions(can_send_messages=True)
    )

    await message.answer(f"🔊 @{user.username or user.first_name} размучен")

# ---------------- БАН ----------------

@dp.message(F.text.lower().startswith("бан"))
async def ban_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    user = await get_user_from_message(message)
    if not user:
        await message.reply("Не удалось найти пользователя.")
        return

    duration = parse_time(message.text)

    if duration:
        until = datetime.utcnow() + duration
        await bot.ban_chat_member(message.chat.id, user.id, until_date=until)
        await message.answer(f"⛔ @{user.username or user.first_name} забанен на {duration}")
    else:
        await bot.ban_chat_member(message.chat.id, user.id)
        await message.answer(f"⛔ @{user.username or user.first_name} забанен навсегда")

# ---------------- РАЗБАН ----------------

@dp.message(F.text.lower().startswith("разбан"))
async def unban_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    user = await get_user_from_message(message)
    if not user:
        await message.reply("Не удалось найти пользователя.")
        return

    await bot.unban_chat_member(message.chat.id, user.id)
    await message.answer(f"✅ @{user.username or user.first_name} разбанен")

# ---------------- ЗАПУСК ----------------

async def main():
    await start_web()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
