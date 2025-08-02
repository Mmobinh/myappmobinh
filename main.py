import os
import asyncio
import logging
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# --- لاگ ---
logging.basicConfig(level=logging.INFO)

# --- کلیدهای API ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY_24SMS7 = os.getenv("API_KEY_24SMS7")
API_KEY_SMSBOWER = os.getenv("API_KEY_SMSBOWER")
CHECKER_API_KEY = os.getenv("CHECKER_API_KEY")

# --- تنظیمات ---
SERVICE = "tg"

COUNTRIES_24SMS7 = {
    "Iran 🇮🇷": 57, "Russia 🇷🇺": 0, "Ukraine 🇺🇦": 1, "Mexico 🇲🇽": 54,
    "Italy 🇮🇹": 86, "Spain 🇪🇸": 56, "Czech 🇨🇿": 63, "Kazakhstan 🇰🇿": 2,
    "Paraguay 🇵🇾": 87, "Hong Kong 🇭🇰": 14,
}

COUNTRIES_SMSBOWER = {
    "Kazakhstan 🇰🇿": 2, "Iran 🇮🇷": 57, "Russia 🇷🇺": 0, "Ukraine 🇺🇦": 1,
    "Mexico 🇲🇽": 54, "Italy 🇮🇹": 86, "Spain 🇪🇸": 56, "Czech 🇨🇿": 10,
    "Paraguay 🇵🇾": 23, "Hong Kong 🇭🇰": 14,
}

# --- متغیرهای حافظه ---
user_sessions = {}
search_tasks = {}
cancel_flags = set()

# --- API Function ---
async def get_number(site, country_code):
    url = f"https://{site}.com/stubs/handler_api.php?api_key={'W9P5j2JQCG8OW1rvS6m1qw9iOW7m42pVeMxzqLdsT5F9703a' if site=='24sms7' else 'cKVlbCpzq2Souj6kHuTNQQDEt********'}&action=getNumber&service={SERVICE}&country={country_code}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()

async def get_status(site, activation_id):
    url = f"https://{site}.com/stubs/handler_api.php?api_key={'W9P5j2JQCG8OW1rvS6m1qw9iOW7m42pVeMxzqLdsT5F9703a' if site=='24sms7' else 'cKVlbCpzq2Souj6kHuTNQQDEt********'}&action=getStatus&id={activation_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()

async def cancel_activation(site, activation_id):
    url = f"https://{site}.com/stubs/handler_api.php?api_key={'W9P5j2JQCG8OW1rvS6m1qw9iOW7m42pVeMxzqLdsT5F9703a' if site=='24sms7' else 'cKVlbCpzq2Souj6kHuTNQQDEt********'}&action=setStatus&status=8&id={activation_id}"
    async with aiohttp.ClientSession() as session:
        await session.get(url)

async def check_valid_number(number):
    url = "http://checker.irbots.com:2021/check"
    params = {"key": CHECKER_API_KEY, "numbers": number}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status == 200:
                result = await resp.json()
                return result.get("data", {}).get(number, False)
    return False

# --- جستجوی شماره ---
async def search_number(user_id, chat_id, message_id, country_code, site, context):
    try:
        while True:
            if user_id in cancel_flags:
                cancel_flags.remove(user_id)
                await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="❌ جستجو لغو شد.")
                return

            response = await get_number(site, country_code)

            if not response.startswith("ACCESS_NUMBER"):
                await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                    text=f"⚠️ خطا از سرور: `{response}`", parse_mode="Markdown")
                return

            _, activation_id, number = response.split(":")
            is_valid = await check_valid_number(number)

            if is_valid:
                user_sessions[user_id] = (activation_id, site)
                await context.bot.edit_message_text(
                    chat_id=chat_id, message_id=message_id,
                    text=f"✅ شماره سالم پیدا شد:\n`{number}`\n\n🔄 منتظر دریافت کد باشید یا یکی از گزینه‌ها رو انتخاب کنید.",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📩 دریافت کد دستی", callback_data="get_code")],
                        [InlineKeyboardButton("❌ لغو شماره", callback_data="cancel_number")],
                        [InlineKeyboardButton("🛑 لغو جستجو", callback_data="cancel_search")],
                    ])
                )
                await wait_for_code(user_id, chat_id, message_id, context)
                return
            else:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                    text=f"⛔ شماره ناسالم پیدا شد: `{number}`\n🔄 تلاش برای شماره جدید...",
                    parse_mode="Markdown")
            await asyncio.sleep(0.5)

    except asyncio.CancelledError:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="🛑 جستجو متوقف شد.")
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ خطا: {str(e)}")

async def wait_for_code(user_id, chat_id, message_id, context):
    for _ in range(120):
        if user_id not in user_sessions:
            return
        activation_id, site = user_sessions[user_id]
        status = await get_status(site, activation_id)

        if status.startswith("STATUS_OK"):
            code = status.split(":")[1]
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                text=f"✅ کد دریافت شد:\n`{code}`", parse_mode="Markdown")
            user_sessions.pop(user_id, None)
            return
        elif status in ["STATUS_WAIT_CODE", "STATUS_WAIT_RETRY"]:
            await asyncio.sleep(5)
        else:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                text=f"⚠️ وضعیت غیرمنتظره: `{status}`", parse_mode="Markdown")
            user_sessions.pop(user_id, None)
            return

# --- هندلرهای تعامل با کاربر ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎯 لطفاً یک سرویس انتخاب کنید:", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 24SMS7", callback_data="site_24sms7")],
        [InlineKeyboardButton("🌐 SMSBower", callback_data="site_smsbower")],
    ]))

async def site_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    site = query.data.split("_")[1]
    countries = COUNTRIES_24SMS7 if site == "24sms7" else COUNTRIES_SMSBOWER
    keyboard = [[InlineKeyboardButton(k, callback_data=f"country_{site}_{v}")] for k, v in countries.items()]
    keyboard.append([InlineKeyboardButton("🛑 لغو جستجو", callback_data="cancel_search")])
    await query.edit_message_text("🌍 یک کشور انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

async def country_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, site, code = query.data.split("_")
    user_id = query.from_user.id

    if user_id in search_tasks:
        search_tasks[user_id].cancel()
    cancel_flags.discard(user_id)

    msg = await query.edit_message_text("🔍 در حال جستجوی شماره سالم...")
    task = asyncio.create_task(search_number(user_id, query.message.chat_id, msg.message_id, int(code), site, context))
    search_tasks[user_id] = task

async def cancel_search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    cancel_flags.add(user_id)
    if user_id in search_tasks:
        search_tasks[user_id].cancel()
        del search_tasks[user_id]
    await query.edit_message_text("🚫 جستجو لغو شد. برای شروع دوباره /start را بفرستید.")

async def cancel_number_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if user_id in user_sessions:
        activation_id, site = user_sessions.pop(user_id)
        await cancel_activation(site, activation_id)
        await query.edit_message_text("✅ شماره لغو شد. برای گرفتن شماره جدید /start را بفرستید.")
    else:
        await query.edit_message_text("ℹ️ شماره فعالی برای لغو وجود ندارد.")

async def get_code_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if user_id in user_sessions:
        activation_id, site = user_sessions[user_id]
        status = await get_status(site, activation_id)
        if status.startswith("STATUS_OK"):
            code = status.split(":")[1]
            await query.answer(f"✅ کد: {code}", show_alert=True)
        elif "WAIT" in status:
            await query.answer("⏳ هنوز کدی دریافت نشده.", show_alert=True)
        else:
            await query.answer(f"⚠️ وضعیت: {status}", show_alert=True)
    else:
        await query.answer("❌ شماره‌ای فعال نیست.", show_alert=True)

# --- اجرا ---
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(site_handler, pattern="site_"))
    app.add_handler(CallbackQueryHandler(country_handler, pattern="country_"))
    app.add_handler(CallbackQueryHandler(cancel_search_handler, pattern="cancel_search"))
    app.add_handler(CallbackQueryHandler(cancel_number_handler, pattern="cancel_number"))
    app.add_handler(CallbackQueryHandler(get_code_handler, pattern="get_code"))
    app.run_polling()

if __name__ == "__main__":
    main()
