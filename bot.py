import asyncio
import os
import re
from datetime import datetime, timedelta
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ChatJoinRequest
from aiogram.filters import Command
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN not set")

bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher()

active_mutes = {}

# ================= WEB SERVER (Render) =================
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
# =====================================================


def parse_duration(text: str):
    text = text.lower()
    match = re.search(r"(\d+)\s*(м|мин|минут|час|часа|часов|день|дня|дней|неделя|недель)", text)
    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)

    if "м" in unit:
        return timedelta(minutes=value)
    if "час" in unit:
        return timedelta(hours=value)
    if "д" in unit:
        return timedelta(days=value)
    if "нед" in unit:
        return timedelta(days=value * 7)

    return None


async def is_admin(chat_id, user_id):
    admins = await bot.get_chat_administrators(chat_id)
    for admin in admins:
        if admin.user.id == user_id:
            return True
    return False


@dp.chat_join_request()
async def approve_request(join_request: ChatJoinRequest):
    await join_request.approve()


@dp.message(Command("adm"))
async def call_admins(message: Message):
    admins = await bot.get_chat_administrators(message.chat.id)
    mentions = []
    for admin in admins:
        if not admin.user.is_bot:
            mentions.append(f"<b><a href='tg://user?id={admin.user.id}'>{admin.user.first_name}</a></b>")
    if mentions:
        await message.answer("🚨 <b>ВЫЗЫВ АДМИНИСТРАТОРОВ/ГАРАНТОВ</b>\n" + " ".join(mentions))
    else:
        await message.answer("<b>Администраторы не найдены</b>")


async def auto_unmute(chat_id, user_id, until, username):
    await asyncio.sleep((until - datetime.now()).total_seconds())
    try:
        await bot.restrict_chat_member(chat_id, user_id, permissions=None)
        await bot.send_message(chat_id, f"✅ <b>Срок молчания @{username} истёк</b>")
    except:
        pass


@dp.message(F.text.lower().startswith("мут"))
async def mute_handler(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return

    duration = parse_duration(message.text)
    if not duration:
        await message.reply("❌ <b>Укажи время: мут 1 час</b>")
        return

    reason = message.text.split("\n", 1)
    reason = reason[1] if len(reason) > 1 else "Не указана"

    user = message.reply_to_message.from_user
    until = datetime.now() + duration

    try:
        await bot.restrict_chat_member(
            message.chat.id,
            user.id,
            permissions=None,
            until_date=until
        )

        await message.answer(
            f"‼️ <b>Участник @{user.username} замучен до {until.strftime('%d.%m.%Y %H:%M')}</b>\n"
            f"<b>Администратор:</b> @{message.from_user.username}\n"
            f"<b>Причина:</b> {reason}"
        )

        asyncio.create_task(auto_unmute(message.chat.id, user.id, until, user.username))

    except TelegramBadRequest:
        await message.reply("❌ <b>Не удалось замутить</b>")


@dp.message(F.text.lower().startswith("размут"))
async def unmute_handler(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return

    user = message.reply_to_message.from_user

    try:
        await bot.restrict_chat_member(message.chat.id, user.id, permissions=None)
        await message.answer(
            f"✅ <b>Участник @{user.username} был размучен</b>\n"
            f"<b>Администратор:</b> @{message.from_user.username}"
        )
    except:
        await message.reply("❌ <b>Ошибка размута</b>")


@dp.message(F.text.lower().startswith("бан"))
async def ban_handler(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return

    reason = message.text.split("\n", 1)
    reason = reason[1] if len(reason) > 1 else "Не указана"

    user = message.reply_to_message.from_user

    try:
        await bot.ban_chat_member(message.chat.id, user.id)
        await message.answer(
            f"‼️ <b>Участник @{user.username} забанен</b>\n"
            f"<b>Администратор:</b> @{message.from_user.username}\n"
            f"<b>Причина:</b> {reason}"
        )
    except:
        await message.reply("❌ <b>Ошибка бана</b>")


@dp.message(F.text.lower().startswith("разбан"))
async def unban_handler(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return

    if not message.reply_to_message:
        return

    user = message.reply_to_message.from_user

    try:
        await bot.unban_chat_member(message.chat.id, user.id)
        await message.answer(
            f"✅ <b>Участник @{user.username} разбанен</b>\n"
            f"<b>Администратор:</b> @{message.from_user.username}"
        )
    except:
        await message.reply("❌ <b>Ошибка разбана</b>")


async def main():
    await start_web()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
