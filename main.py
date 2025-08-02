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

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY_24SMS7 = os.getenv("API_KEY_24SMS7")
API_KEY_SMSBOWER = os.getenv("API_KEY_SMSBOWER")
CHECKER_API_KEY = os.getenv("CHECKER_API_KEY")
SERVICE = "tg"

COUNTRIES_24SMS7 = {
    "Iran": 57, "Russia": 0, "Ukraine": 1, "Mexico": 54, "Italy": 86, "Spain": 56,
    "Czech Republic": 63, "Kazakhstan": 2, "Paraguay": 87, "Hong Kong": 14,
    "Slot 1": 0, "Slot 2": 0, "Slot 3": 0, "Slot 4": 0, "Slot 5": 0,
    "Slot 6": 0, "Slot 7": 0, "Slot 8": 0, "Slot 9": 0, "Slot 10": 0,
}
COUNTRIES_SMSBOWER = {
    "Kazakhstan": 2, "Iran": 57, "Russia": 0, "Ukraine": 1, "Mexico": 54,
    "Italy": 86, "Spain": 56, "Czech Republic": 10, "Paraguay": 23, "Hong Kong": 14,
    "Slot 1": 0, "Slot 2": 0, "Slot 3": 0, "Slot 4": 0, "Slot 5": 0,
    "Slot 6": 0, "Slot 7": 0, "Slot 8": 0, "Slot 9": 0, "Slot 10": 0,
}

user_sessions = {}
search_tasks = {}
cancel_flags = set()

# === دریافت شماره ===
async def get_number(site, code):
    if site == "24sms7":
        url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getNumber&service={SERVICE}&country={code}"
    else:
        url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getNumber&service={SERVICE}&country={code}&maxPrice=58.67&providerIds=2195,2194,1000&exceptProviderIds=2196&phoneException=7700,7708"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def cancel_number(site, id_):
    url = f"https://{'24sms7.com' if site == '24sms7' else 'smsbower.online'}/stubs/handler_api.php?api_key={'API_KEY_24SMS7' if site == '24sms7' else 'API_KEY_SMSBOWER'}&action=setStatus&status=8&id={id_}"
    url = url.replace("API_KEY_24SMS7", API_KEY_24SMS7).replace("API_KEY_SMSBOWER", API_KEY_SMSBOWER)
    async with aiohttp.ClientSession() as s:
        await s.get(url)

async def get_code(site, id_):
    url = f"https://{'24sms7.com' if site == '24sms7' else 'smsbower.online'}/stubs/handler_api.php?api_key={'API_KEY_24SMS7' if site == '24sms7' else 'API_KEY_SMSBOWER'}&action=getStatus&id={id_}"
    url = url.replace("API_KEY_24SMS7", API_KEY_24SMS7).replace("API_KEY_SMSBOWER", API_KEY_SMSBOWER)
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def check_valid(number):
    try:
        url = "http://checker.irbots.com:2021/check"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, params={"key": CHECKER_API_KEY, "numbers": number}) as r:
                res = await r.json()
                return res.get("data", {}).get(number, False)
    except:
        return False

# === فرمان‌ها ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("📡 24sms7", callback_data="site_24sms7")],
        [InlineKeyboardButton("📡 SMSBower", callback_data="site_smsbower")]
    ]
    await update.message.reply_text("🌐 سرویس مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))

async def site_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    site = query.data.split("_")[1]
    countries = COUNTRIES_24SMS7 if site == "24sms7" else COUNTRIES_SMSBOWER
    buttons = [[InlineKeyboardButton(name, callback_data=f"country_{site}_{code}")] for name, code in countries.items()]
    await query.edit_message_text("🌍 انتخاب کشور:", reply_markup=InlineKeyboardMarkup(buttons))

async def country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, site, code = query.data.split("_")
    user_id = query.from_user.id
    cancel_flags.discard(user_id)
    msg = await query.edit_message_text("🔎 جستجو برای شماره سالم...")
    task = asyncio.create_task(search_number(user_id, query.message.chat_id, msg.message_id, code, site, context))
    search_tasks[user_id] = task

async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    cancel_flags.add(query.from_user.id)
    await query.answer("❌ جستجو لغو شد.")

async def cancel_number_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if user_id in user_sessions:
        id_, site = user_sessions.pop(user_id)
        await cancel_number(site, id_)
        await query.edit_message_text("✅ شماره لغو شد.")
    else:
        await query.answer("شماره‌ای برای لغو نیست.", show_alert=True)

async def check_code_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if user_id not in user_sessions:
        await query.answer("❌ شماره‌ای فعال نیست.", show_alert=True)
        return
    id_, site = user_sessions[user_id]
    resp = await get_code(site, id_)
    if resp.startswith("STATUS_OK"):
        code = resp.split(":")[-1]
        await query.answer(f"📩 کد: {code}", show_alert=True)
    elif "WAIT" in resp:
        await query.answer("⏳ هنوز کدی دریافت نشده.", show_alert=True)
    else:
        await query.answer("❌ خطا در دریافت کد.", show_alert=True)

# === جستجو برای شماره ===
async def search_number(user_id, chat_id, msg_id, code, site, context):
    while True:
        if user_id in cancel_flags:
            cancel_flags.remove(user_id)
            await context.bot.edit_message_text("❌ جستجو لغو شد.", chat_id=chat_id, message_id=msg_id)
            return
        resp = await get_number(site, code)
        if not resp.startswith("ACCESS_NUMBER"):
            await asyncio.sleep(2)
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
            await context.bot.edit_message_text(
                f"✅ شماره سالم پیدا شد:\n<code>{number}</code>",
                chat_id=chat_id, message_id=msg_id, parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            # دریافت خودکار کد
            for _ in range(60):
                await asyncio.sleep(3)
                code_resp = await get_code(site, id_)
                if code_resp.startswith("STATUS_OK"):
                    code = code_resp.split(":")[-1]
                    await context.bot.send_message(chat_id, f"📥 کد دریافت شد: <code>{code}</code>", parse_mode=ParseMode.HTML)
                    break
            return
        else:
            await cancel_number(site, id_)
            await context.bot.edit_message_text(
                f"❌ شماره ناسالم بود. ادامه جستجو...", chat_id=chat_id, message_id=msg_id)
        await asyncio.sleep(2)

# === سرور وب برای keep alive ===
async def web_handler(request): return web.Response(text="✅ Bot is Alive!")

async def start_webserver():
    app = web.Application()
    app.add_routes([web.get('/', web_handler)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

# === main ===
async def main():
    await start_webserver()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(site_selected, pattern="^site_"))
    app.add_handler(CallbackQueryHandler(country_selected, pattern="^country_"))
    app.add_handler(CallbackQueryHandler(cancel_search, pattern="^cancel_search$"))
    app.add_handler(CallbackQueryHandler(cancel_number_callback, pattern="^cancel_number$"))
    app.add_handler(CallbackQueryHandler(check_code_callback, pattern="^checkcode$"))
    print("✅ Bot is running...")
    await app.run_polling()

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())
