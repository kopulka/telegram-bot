import asyncio
import os
import re
from datetime import timedelta, datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ChatPermissions
from aiogram.exceptions import TelegramBadRequest

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN not set")

bot = Bot(token=TOKEN)
dp = Dispatcher()

USERNAME_RE = re.compile(r"@(\w+)", re.IGNORECASE)
TIME_RE = re.compile(r"(\d+)\s*(м|мин|ч|час|д|дн)", re.IGNORECASE)

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

async def is_admin(message: Message):
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in ["administrator", "creator"]
    except:
        return False

def parse_time(text):
    m = TIME_RE.search(text)
    if not m:
        return None

    value = int(m.group(1))
    unit = m.group(2).lower()

    if unit.startswith("м"):
        return timedelta(minutes=value)
    if unit.startswith("ч"):
        return timedelta(hours=value)
    if unit.startswith("д"):
        return timedelta(days=value)

    return None

async def get_target_user(message: Message):
    if message.reply_to_message:
        return message.reply_to_message.from_user

    m = USERNAME_RE.search(message.text)
    if m:
        try:
            return await bot.get_chat("@" + m.group(1))
        except:
            return None

    return None

# ======================= /adm (доступна всем) =======================

@dp.message(F.text == "/adm")
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

# ======================= МУТ =======================

@dp.message(F.text.lower().startswith("мут"))
async def mute_user(message: Message):
    if not await is_admin(message):
        return await message.answer("⛔ У тебя нет прав")

    target = await get_target_user(message)
    if not target:
        return await message.answer("Укажи пользователя ответом или через @username")

    delta = parse_time(message.text)

    until_date = None
    text_time = "навсегда"

    if delta:
        until_date = datetime.now() + delta
        text_time = f"на {delta}"

    try:
        await bot.restrict_chat_member(
            message.chat.id,
            target.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )
        await message.answer(f"🔇 Мут: {target.full_name} ({text_time})")
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")

# ======================= РАЗМУТ =======================

@dp.message(F.text.lower().startswith("размут"))
async def unmute_user(message: Message):
    if not await is_admin(message):
        return await message.answer("⛔ У тебя нет прав")

    target = await get_target_user(message)
    if not target:
        return await message.answer("Укажи пользователя ответом или через @username")

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
        await message.answer(f"🔊 Размут: {target.full_name}")
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")

# ======================= БАН =======================

@dp.message(F.text.lower().startswith("бан"))
async def ban_user(message: Message):
    if not await is_admin(message):
        return await message.answer("⛔ У тебя нет прав")

    target = await get_target_user(message)
    if not target:
        return await message.answer("Укажи пользователя ответом или через @username")

    try:
        await bot.ban_chat_member(message.chat.id, target.id)
        await message.answer(f"⛔ Бан: {target.full_name}")
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")

# ======================= РАЗБАН =======================

@dp.message(F.text.lower().startswith("разбан"))
async def unban_user(message: Message):
    if not await is_admin(message):
        return await message.answer("⛔ У тебя нет прав")

    target = await get_target_user(message)
    if not target:
        return await message.answer("Укажи пользователя ответом или через @username")

    try:
        await bot.unban_chat_member(message.chat.id, target.id)
        await message.answer(f"♻️ Разбан: {target.full_name}")
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")

# ======================= ЗАПУСК =======================

async def main():
    await start_web()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
