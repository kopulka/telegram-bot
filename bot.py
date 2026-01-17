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

# ===== WEB SERVER (чтобы Render не убивал сервис) =====
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

# ====================================================

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
    
