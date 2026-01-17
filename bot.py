import asyncio
import os
import re
from datetime import timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, ChatJoinRequest
from aiogram.exceptions import TelegramBadRequest

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN not set")

BAD_WORDS = ["мат1", "мат2", "мат3"]

TIME_RE = re.compile(r"на\s+(\d+)\s*(минут|минуты|минута|час|часа|часов|день|дня|дней)", re.IGNORECASE)
REASON_RE = re.compile(r"причина\s*:\s*(.+)", re.IGNORECASE)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ===== WEB SERVER FOR RENDER =====
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
# =================================

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
            mentions.append(f"<a href='tg://user?id={u.id}'>{u.first_name}</a>")
    if mentions:
        await message.answer("🚨 Вызов администраторов:\n" + " ".join(mentions), parse_mode="HTML")
    else:
        await message.answer("Администраторы не найдены")

def contains_bad_words(text: str) -> bool:
    t = text.lower()
    for w in BAD_WORDS:
        if re.search(rf"\b{re.escape(w)}\b", t):
            return True
    return False

@dp.message(F.text)
async def anti_swear(message: Message):
    if contains_bad_words(message.text):
        try:
            await message.delete()
        except TelegramBadRequest:
            pass
        await message.answer("Не ругайся")

def parse_reason(text: str) -> str:
    m = REASON_RE.search(text)
    return m.group(1).strip() if m else "Не указана"

def parse_time(text: str):
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
    return None

def format_timedelta(td: timedelta) -> str:
    seconds = int(td.total_seconds())
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} мин"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} час"
    days = hours // 24
    return f"{days} дн"

@dp.message(Command("бан"))
async def ban_user(message: Message):
    if not message.reply_to_message:
        return await message.answer("Ответь на сообщение пользователя.")

    target = message.reply_to_message.from_user
    reason = parse_reason(message.text)

    try:
        await bot.ban_chat_member(message.chat.id, target.id)
        await message.answer(
            f"🚫 Бан\nПользователь: {target.full_name}\nПричина: {reason}"
        )
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")

@dp.message(Command("мут"))
async def mute_user(message: Message):
    if not message.reply_to_message:
        return await message.answer("Ответь на сообщение пользователя.")

    target = message.reply_to_message.from_user
    reason = parse_reason(message.text)
    delta = parse_time(message.text)

    until_date = None
    time_text = "Навсегда"
    if delta:
        until_date = message.date + delta
        time_text = format_timedelta(delta)

    try:
        await bot.restrict_chat_member(
            message.chat.id,
            target.id,
            permissions=None,
            until_date=until_date
        )
        await message.answer(
            f"🔇 Мут\nПользователь: {target.full_name}\nСрок: {time_text}\nПричина: {reason}"
        )
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")

async def main():
    await start_web()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
