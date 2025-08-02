import os
import asyncio
import logging
import nest_asyncio
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
)
from aiohttp import web

# === تنظیمات لاگ و API ها ===
logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY_24SMS7 = os.getenv("API_KEY_24SMS7")
API_KEY_SMSBOWER = os.getenv("API_KEY_SMSBOWER")
CHECKER_API_KEY = os.getenv("CHECKER_API_KEY")
SERVICE = "tg"

# === لیست کشورها ===
COUNTRIES_24SMS7 = {
    "Iran": 57, "Russia": 0, "Ukraine": 1, "Mexico": 54, "Italy": 86, "Spain": 56,
    "Czech Republic": 63, "Kazakhstan": 2, "Paraguay": 87, "Hong Kong": 14,
    "Country Slot 1": 0, "Country Slot 2": 0, "Country Slot 3": 0,
    "Country Slot 4": 0, "Country Slot 5": 0, "Country Slot 6": 0,
    "Country Slot 7": 0, "Country Slot 8": 0, "Country Slot 9": 0, "Country Slot 10": 0
}
COUNTRIES_SMSBOWER = {
    "Kazakhstan": 2, "Iran": 57, "Russia": 0, "Ukraine": 1, "Mexico": 54, "Italy": 86,
    "Spain": 56, "Czech Republic": 10, "Paraguay": 23, "Hong Kong": 14,
    "Country Slot 1": 0, "Country Slot 2": 0, "Country Slot 3": 0,
    "Country Slot 4": 0, "Country Slot 5": 0, "Country Slot 6": 0,
    "Country Slot 7": 0, "Country Slot 8": 0, "Country Slot 9": 0, "Country Slot 10": 0
}

# === حافظه موقت ===
user_sessions = {}
search_tasks = {}
cancel_flags = set()

# === گرفتن شماره ===
async def get_number_24sms7(code):
    url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getNumber&service={SERVICE}&country={code}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def get_number_smsbower(code):
    url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getNumber&service={SERVICE}&country={code}&maxPrice=58.67&providerIds=2195,2194,1000&exceptProviderIds=2196&phoneException=7700,7708"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

# === بررسی دریافت کد ===
async def get_code(site, id_):
    if site == "24sms7":
        url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getStatus&id={id_}"
    else:
        url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getStatus&id={id_}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def cancel_number(site, id_):
    if site == "24sms7":
        url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=setStatus&status=8&id={id_}"
    else:
        url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=setStatus&status=8&id={id_}"
    async with aiohttp.ClientSession() as s:
        await s.get(url)

# === چک کردن اعتبار شماره ===
async def check_valid(number):
    url = "http://checker.irbots.com:2021/check"
    params = {"key": CHECKER_API_KEY, "numbers": number}
    async with aiohttp.ClientSession() as s:
        async with s.get(url, params=params) as r:
            if r.status == 200:
                data = await r.json()
                return data.get("data", {}).get(number, False)
    return False

# === دستورات ربات ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("🌐 سرویس 24sms7", callback_data="site_24sms7")],
        [InlineKeyboardButton("🌐 سرویس SMSBower", callback_data="site_smsbower")]
    ]
    await update.message.reply_text("یک سرویس را انتخاب کن:", reply_markup=InlineKeyboardMarkup(buttons))

async def site_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    site = query.data.split("_")[1]
    countries = COUNTRIES_24SMS7 if site == "24sms7" else COUNTRIES_SMSBOWER
    buttons = [[InlineKeyboardButton(name, callback_data=f"country_{site}_{id_}")] for name, id_ in countries.items()]
    await query.edit_message_text("کشور مورد نظر را انتخاب کن:", reply_markup=InlineKeyboardMarkup(buttons))

async def country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, site, code = query.data.split("_")
    user_id = query.from_user.id
    cancel_flags.discard(user_id)
    msg = await query.edit_message_text("🔍 در حال جستجوی شماره سالم...")
    task = asyncio.create_task(search_number(user_id, query.message.chat_id, msg.message_id, code, site, context))
    search_tasks[user_id] = task

async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cancel_flags.add(query.from_user.id)
    await query.edit_message_text("❌ جستجو لغو شد.")

async def cancel_number_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id in user_sessions:
        id_, site = user_sessions.pop(user_id)
        await cancel_number(site, id_)
        await query.edit_message_text("❌ شماره لغو شد.")
    else:
        await query.edit_message_text("شماره‌ای برای لغو وجود ندارد.")

async def check_code_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if user_id not in user_sessions:
        await query.answer("شماره‌ای فعال نیست.", show_alert=True)
        return
    id_, site = user_sessions[user_id]
    resp = await get_code(site, id_)
    if resp.startswith("STATUS_OK"):
        code = resp.split(":")[1]
        await query.answer(f"📩 کد: {code}", show_alert=True)
    elif "WAIT" in resp:
        await query.answer("⏳ هنوز کدی دریافت نشده.", show_alert=True)
    else:
        await query.answer("❌ خطا در دریافت کد.", show_alert=True)

# === جستجو برای شماره سالم ===
async def search_number(user_id, chat_id, msg_id, code, site, context):
    while True:
        if user_id in cancel_flags:
            cancel_flags.remove(user_id)
            await context.bot.edit_message_text("❌ جستجو لغو شد.", chat_id=chat_id, message_id=msg_id)
            return

        resp = await (get_number_24sms7(code) if site == "24sms7" else get_number_smsbower(code))
        if "NO_NUMBER" in resp or "NO_NUMBERS" in resp:
            await context.bot.edit_message_text("⏳ شماره موجود نیست. تلاش مجدد...", chat_id=chat_id, message_id=msg_id)
            await asyncio.sleep(5)
            continue
        if not resp.startswith("ACCESS_NUMBER"):
            await asyncio.sleep(3)
            continue

        _, id_, number = resp.split(":")[:3]
        number = f"+{number}"
        valid = await check_valid(number)
        if valid:
            user_sessions[user_id] = (id_, site)
            buttons = [
                [InlineKeyboardButton("📩 دریافت کد", callback_data="checkcode")],
                [InlineKeyboardButton("❌ لغو شماره", callback_data="cancel_number")]
            ]
            await context.bot.edit_message_text(f"✅ شماره سالم پیدا شد:\n<code>{number}</code>", chat_id=chat_id, message_id=msg_id, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))
            return
        else:
            await cancel_number(site, id_)
            await context.bot.edit_message_text(f"❌ شماره ناسالم: <code>{number}</code>\n🔄 ادامه جستجو...", chat_id=chat_id, message_id=msg_id, parse_mode=ParseMode.HTML)
            await asyncio.sleep(2)

# === نگه‌داشتن بات آنلاین ===
async def web_handler(request):
    return web.Response(text="Bot is alive")

async def start_webserver():
    app = web.Application()
    app.add_routes([web.get('/', web_handler)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

# === اجرای ربات ===
async def main():
    await start_webserver()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(site_selected, pattern="^site_"))
    app.add_handler(CallbackQueryHandler(country_selected, pattern="^country_"))
    app.add_handler(CallbackQueryHandler(cancel_search, pattern="^cancel_search$"))
    app.add_handler(CallbackQueryHandler(cancel_number_callback, pattern="^cancel_number$"))
    app.add_handler(CallbackQueryHandler(check_code_callback, pattern="^checkcode$"))

    logging.info("🤖 Bot is running...")
    await app.run_polling()

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())
