import asyncio
import os
import re
from datetime import datetime, timedelta, timezone
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ChatJoinRequest
from aiogram.exceptions import TelegramBadRequest

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN not set")

bot = Bot(token=TOKEN)
dp = Dispatcher()

BAD_WORDS = ["мат1", "мат2", "мат3"]

TIME_RE = re.compile(r"на\s+(\d+)\s*(м|мин|минута|минуты|минут|ч|час|часа|часов|д|день|дня|дней|н|неделя|недели|недель)", re.IGNORECASE)
REASON_RE = re.compile(r"причина\s*:\s*(.+)", re.IGNORECASE)
USERNAME_RE = re.compile(r"@(\w+)")

# ========== WEB SERVER (для Render) ==========
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
# ============================================

async def is_admin(message: Message) -> bool:
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in ("administrator", "creator")
    except:
        return False

def parse_reason(text: str) -> str:
    m = REASON_RE.search(text)
    return m.group(1).strip() if m else "Не указана"

def parse_time(text: str):
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
    if unit.startswith("н"):
        return timedelta(weeks=value)
    return None

def contains_bad_words(text: str) -> bool:
    t = text.lower()
    for w in BAD_WORDS:
        if re.search(rf"\b{re.escape(w)}\b", t):
            return True
    return False

async def get_target_user(message: Message):
    if message.reply_to_message:
        return message.reply_to_message.from_user

    m = USERNAME_RE.search(message.text)
    if m:
        username = m.group(1)
        try:
            member = await bot.get_chat_member(message.chat.id, f"@{username}")
            return member.user
        except:
            return None

    return None

# ===== 1) Auto approve join requests =====
@dp.chat_join_request()
async def approve_request(join_request: ChatJoinRequest):
    await join_request.approve()

# ===== 2) /adm для всех, с текстом =====
@dp.message(F.text.lower().startswith("/adm"))
async def call_admins(message: Message):
    admins = await bot.get_chat_administrators(message.chat.id)
    mentions = []
    for admin in admins:
        u = admin.user
        if not u.is_bot:
            mentions.append(f"<a href='tg://user?id={u.id}'>{u.first_name}</a>")
    if mentions:
        await message.answer("🚨 Вызов администраторов:\n" + " ".join(mentions), parse_mode="HTML")

# ===== 3) Anti-swear =====
@dp.message(F.text)
async def anti_swear(message: Message):
    if contains_bad_words(message.text):
        try:
            await message.delete()
        except:
            pass
        await message.answer("Не ругайся")

# ===== BAN =====
@dp.message(F.text.lower().startswith("бан"))
async def ban_user(message: Message):
    if not await is_admin(message):
        return

    target = await get_target_user(message)
    if not target:
        return await message.answer("Не могу найти пользователя.")

    reason = parse_reason(message.text)
    delta = parse_time(message.text)

    until_date = None
    if delta:
        until_date = datetime.now(timezone.utc) + delta

    try:
        await bot.ban_chat_member(message.chat.id, target.id, until_date=until_date)
        await message.answer(
            f"🚫 Бан\nПользователь: @{target.username or target.first_name}\nПричина: {reason}"
        )
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")

# ===== UNBAN =====
@dp.message(F.text.lower().startswith("разбан"))
async def unban_user(message: Message):
    if not await is_admin(message):
        return

    target = await get_target_user(message)
    if not target:
        return await message.answer("Не могу найти пользователя.")

    try:
        await bot.unban_chat_member(message.chat.id, target.id)
        await message.answer(f"✅ Пользователь @{target.username or target.first_name} разбанен")
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")

# ===== MUTE =====
@dp.message(F.text.lower().startswith("мут"))
async def mute_user(message: Message):
    if not await is_admin(message):
        return

    target = await get_target_user(message)
    if not target:
        return await message.answer("Не могу найти пользователя.")

    reason = parse_reason(message.text)
    delta = parse_time(message.text)

    until_date = None
    time_text = "Навсегда"

    if delta:
        until_date = datetime.now(timezone.utc) + delta
        time_text = str(delta)

    try:
        await bot.restrict_chat_member(
            message.chat.id,
            target.id,
            permissions=None,
            until_date=until_date
        )
        await message.answer(
            f"🔇 Мут\nПользователь: @{target.username or target.first_name}\nСрок: {time_text}\nПричина: {reason}"
        )
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")

# ===== UNMUTE =====
@dp.message(F.text.lower().startswith("размут"))
async def unmute_user(message: Message):
    if not await is_admin(message):
        return

    target = await get_target_user(message)
    if not target:
        return await message.answer("Не могу найти пользователя.")

    try:
        await bot.restrict_chat_member(
            message.chat.id,
            target.id,
            permissions={
                "can_send_messages": True,
                "can_send_media_messages": True,
                "can_send_polls": True,
                "can_send_other_messages": True,
                "can_add_web_page_previews": True,
                "can_change_info": True,
                "can_invite_users": True,
                "can_pin_messages": True,
            }
        )
        await message.answer(f"🟢 Время мута у @{target.username or target.first_name} закончилось")
    except TelegramBadRequest as e:
        await message.answer(f"Ошибка: {e}")

# ===== RUN =====
async def main():
    await start_web()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
