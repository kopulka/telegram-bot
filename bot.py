import asyncio
import os
import re
from datetime import timedelta, datetime
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ChatJoinRequest
from aiogram.exceptions import TelegramBadRequest

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN not set")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# =================== НАСТРОЙКИ ===================

BAD_WORDS = ["мат1", "мат2", "мат3"]

TIME_RE = re.compile(r"(\d+)\s*(минут|минуты|минута|час|часа|часов|день|дня|дней|неделя|недели|недель)", re.IGNORECASE)

# Хранилище причин и сроков (в памяти)
mutes = {}  # user_id: {"until": datetime|None, "reason": str, "admin": str}
bans = {}   # user_id: {"reason": str, "admin": str}

# =================== WEB (для Render) ===================

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

# =================== ВСПОМОГАТЕЛЬНЫЕ ===================

def contains_bad_words(text: str) -> bool:
    t = text.lower()
    for w in BAD_WORDS:
        if re.search(rf"\b{re.escape(w)}\b", t):
            return True
    return False

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
    if unit.startswith("дн"):
        return timedelta(days=value)
    if unit.startswith("нед"):
        return timedelta(days=value * 7)
    return None

async def is_admin(chat_id, user_id):
    admins = await bot.get_chat_administrators(chat_id)
    return any(a.user.id == user_id for a in admins)

async def get_user_by_username(chat_id, username: str):
    # Telegram API не даёт прямой поиск по username в чате,
    # поэтому тут мы полагаемся на reply или упоминание.
    # Если нужно — сделаю через кеш/БД.
    return None

def fmt_dt(dt: datetime):
    return dt.strftime("%d.%m.%Y %H:%M")

# =================== АВТОАПРУВ ===================

@dp.chat_join_request()
async def approve_request(join_request: ChatJoinRequest):
    await join_request.approve()

# =================== /adm (работает с текстом) ===================

@dp.message(F.text.lower().startswith("/adm"))
async def call_admins(message: Message):
    admins = await bot.get_chat_administrators(message.chat.id)
    mentions = []
    for admin in admins:
        u = admin.user
        if not u.is_bot:
            if u.username:
                mentions.append(f"@{u.username}")
            else:
                mentions.append(f"<a href='tg://user?id={u.id}'>{u.first_name}</a>")
    if mentions:
        text = "<b>🚨 СОЗЫВ АДМИНИСТРАЦИИ:</b> " + ", ".join(mentions)
        await message.answer(text, parse_mode="HTML")
    else:
        await message.answer("<b>Администраторы не найдены</b>", parse_mode="HTML")

# =================== АНТИМАТ ===================

@dp.message(F.text)
async def anti_swear(message: Message):
    if contains_bad_words(message.text):
        try:
            await message.delete()
        except:
            pass
        await message.answer("<b>Не ругайся</b>", parse_mode="HTML")

# =================== МУТ ===================

@dp.message(F.text.lower().startswith("мут"))
async def mute_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    target = None
    if message.reply_to_message:
        target = message.reply_to_message.from_user

    if not target:
        return await message.answer("<b>Ответь на сообщение пользователя.</b>", parse_mode="HTML")

    delta = parse_time(message.text)
    reason = message.text.replace("мут", "").strip() or "Не указана"

    until_date = None
    time_text = "Навсегда"
    if delta:
        until_date = datetime.utcnow() + delta
        time_text = fmt_dt(until_date)

    try:
        await bot.restrict_chat_member(
            message.chat.id,
            target.id,
            permissions=None,
            until_date=until_date
        )

        mutes[target.id] = {
            "until": until_date,
            "reason": reason,
            "admin": message.from_user.username or message.from_user.first_name
        }

        text = (
            f"<b>‼️Участник @{target.username or target.first_name} замучен до {time_text}</b> "
            f"админом (@{message.from_user.username})\n\n"
            f"<b>Причина:</b> {reason}"
        )
        await message.answer(text, parse_mode="HTML")

        if until_date:
            asyncio.create_task(auto_unmute(message.chat.id, target.id, until_date))

    except TelegramBadRequest as e:
        await message.answer(str(e))

async def auto_unmute(chat_id, user_id, until_date: datetime):
    await asyncio.sleep(max(0, (until_date - datetime.utcnow()).total_seconds()))
    try:
        await bot.restrict_chat_member(chat_id, user_id, permissions=None)
        info = mutes.pop(user_id, None)
        if info:
            text = f"<b>✅Срок молчания @{user_id} истёк</b>"
            await bot.send_message(chat_id, text, parse_mode="HTML")
    except:
        pass

# =================== РАЗМУТ ===================

@dp.message(F.text.lower().startswith("размут"))
async def unmute_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return await message.answer("<b>Ответь на сообщение пользователя.</b>", parse_mode="HTML")

    target = message.reply_to_message.from_user

    try:
        await bot.restrict_chat_member(message.chat.id, target.id, permissions=None)
        mutes.pop(target.id, None)

        text = (
            f"<b>✅Участник @{target.username or target.first_name} был размучен</b> "
            f"админом (@{message.from_user.username})"
        )
        await message.answer(text, parse_mode="HTML")
    except TelegramBadRequest as e:
        await message.answer(str(e))

# =================== БАН ===================

@dp.message(F.text.lower().startswith("бан"))
async def ban_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return await message.answer("<b>Ответь на сообщение пользователя.</b>", parse_mode="HTML")

    target = message.reply_to_message.from_user
    reason = message.text.replace("бан", "").strip() or "Не указана"

    try:
        await bot.ban_chat_member(message.chat.id, target.id)

        bans[target.id] = {
            "reason": reason,
            "admin": message.from_user.username or message.from_user.first_name
        }

        text = (
            f"<b>‼️Участник @{target.username or target.first_name} забанен</b> "
            f"админом (@{message.from_user.username})\n\n"
            f"<b>Причина:</b> {reason}"
        )
        await message.answer(text, parse_mode="HTML")

    except TelegramBadRequest as e:
        await message.answer(str(e))

# =================== РАЗБАН ===================

@dp.message(F.text.lower().startswith("разбан"))
async def unban_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return await message.answer("<b>Ответь на сообщение пользователя.</b>", parse_mode="HTML")

    target = message.reply_to_message.from_user

    try:
        await bot.unban_chat_member(message.chat.id, target.id)
        bans.pop(target.id, None)

        text = (
            f"<b>✅Участник @{target.username or target.first_name} был разбанен</b> "
            f"админом (@{message.from_user.username})"
        )
        await message.answer(text, parse_mode="HTML")
    except TelegramBadRequest as e:
        await message.answer(str(e))

# =================== ПРИЧИНА ===================

@dp.message(F.text.lower().startswith("причина"))
async def reason_user(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return await message.answer("<b>Ответь на сообщение пользователя.</b>", parse_mode="HTML")

    target = message.reply_to_message.from_user

    if target.id in mutes:
        info = mutes[target.id]
        until = info["until"]
        time_text = fmt_dt(until) if until else "Навсегда"
        text = (
            f"<b>‼️Участник @{target.username or target.first_name} замучен до {time_text}</b>\n\n"
            f"<b>Причина:</b> {info['reason']}"
        )
        return await message.answer(text, parse_mode="HTML")

    if target.id in bans:
        info = bans[target.id]
        text = (
            f"<b>‼️Участник @{target.username or target.first_name} забанен</b>\n\n"
            f"<b>Причина:</b> {info['reason']}"
        )
        return await message.answer(text, parse_mode="HTML")

    await message.answer(
        f"<b>⭐️Участник @{target.username or target.first_name} не находится в бане или муте</b>",
        parse_mode="HTML"
    )

# =================== ЗАПУСК ===================

async def main():
    await start_web()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
