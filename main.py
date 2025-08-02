# main.py
import os
import asyncio
import logging
import aiohttp
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# Environment variables
API_KEY_24SMS7 = os.getenv("API_KEY_24SMS7")
API_KEY_SMSBOWER = os.getenv("API_KEY_SMSBOWER")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHECKER_API_KEY = os.getenv("CHECKER_API_KEY")
SERVICE = "tg"

COUNTRIES_24SMS7 = {
    "Iran": 57,
    "Russia": 3,
    "Ukraine": 4,
    "Mexico": 20,
    "Italy": 15,
    "Spain": 12,
    "Czech Republic": 10,
    "Kazakhstan": 2,
    "Paraguay": 23,
    "Hong Kong": 14,
}

COUNTRIES_SMSBOWER = {
    "Kazakhstan": 2,
}

user_sessions = {}
search_tasks = {}
cancel_flags = set()
invalid_number_messages = {}

# ------------------ API HANDLERS ------------------

async def get_number_24sms7(country_code):
    url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getNumber&service={SERVICE}&country={country_code}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()

async def get_number_smsbower(country_code):
    url = (
        f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}"
        f"&action=getNumber&service={SERVICE}&country={country_code}"
        f"&maxPrice=58.67&providerIds=2195,2194,1000&exceptProviderIds=2196&phoneException=7700,7708"
    )
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()

async def cancel_number_24sms7(id_):
    url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=setStatus&status=8&id={id_}"
    async with aiohttp.ClientSession() as session:
        await session.get(url)

async def cancel_number_smsbower(id_):
    url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=setStatus&status=8&id={id_}"
    async with aiohttp.ClientSession() as session:
        await session.get(url)

async def get_code(site, id_):
    if site == "24sms7":
        url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getStatus&id={id_}"
    else:
        url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getStatus&id={id_}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()

async def check_number_validity(number: str) -> bool:
    url = "http://checker.irbots.com:2021/check"
    params = {"key": CHECKER_API_KEY, "numbers": number}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("data", {}).get(number, False) is True
            return False

# ------------------ TELEGRAM COMMANDS ------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("24sms7", callback_data="site_24sms7")],
        [InlineKeyboardButton("SMSBower", callback_data="site_smsbower")],
    ]
    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("🌐 لطفاً سایت مورد نظر را انتخاب کنید:", reply_markup=markup)

async def site_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    site = query.data.split("_")[1]
    countries = COUNTRIES_24SMS7 if site == "24sms7" else COUNTRIES_SMSBOWER

    buttons = [
        [InlineKeyboardButton(name, callback_data=f"country_{site}_{id_}")]
        for name, id_ in countries.items()
    ]
    markup = InlineKeyboardMarkup(buttons)
    await query.edit_message_text("🌍 لطفاً کشور مورد نظر را انتخاب کنید:", reply_markup=markup)

async def country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, site, country_code = query.data.split("_")
    user_id = query.from_user.id
    cancel_flags.discard(user_id)

    msg = await query.edit_message_text("⏳ شروع جستجو...")
    task = asyncio.create_task(number_search_task(user_id, query.message.chat_id, msg.message_id, country_code, site, context))
    search_tasks[user_id] = task

async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("❌ جستجو لغو شد.")
    cancel_flags.add(query.from_user.id)

async def cancel_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer("❌ شماره لغو شد.")

    if user_id in user_sessions:
        id_, site = user_sessions.pop(user_id)
        await (cancel_number_24sms7(id_) if site == "24sms7" else cancel_number_smsbower(id_))

    # بازگشت به منوی انتخاب سایت
    buttons = [
        [InlineKeyboardButton("24sms7", callback_data="site_24sms7")],
        [InlineKeyboardButton("SMSBower", callback_data="site_smsbower")],
    ]
    markup = InlineKeyboardMarkup(buttons)
    await query.edit_message_text("🌐 لطفاً سایت جدیدی را انتخاب کنید:", reply_markup=markup)

async def check_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if user_id not in user_sessions:
        await query.answer("❌ شماره‌ای برای دریافت کد وجود ندارد.", show_alert=True)
        return

    id_, site = user_sessions[user_id]
    resp = await get_code(site, id_)

    if resp.startswith("STATUS_OK"):
        code = resp.split(":")[2]
        await query.answer(f"📩 کد: {code}", show_alert=True)
    elif resp == "STATUS_WAIT_CODE":
        await query.answer("⏳ هنوز کدی دریافت نشده", show_alert=True)
    else:
        await query.answer("❌ خطا در دریافت کد", show_alert=True)

# ------------------ SEARCH TASK ------------------

async def number_search_task(user_id, chat_id, message_id, country_code, site, context):
    while True:
        if user_id in cancel_flags:
            cancel_flags.remove(user_id)
            await context.bot.edit_message_text("🚫 جستجو لغو شد.", chat_id=chat_id, message_id=message_id)
            return

        resp = await (get_number_24sms7(country_code) if site == "24sms7" else get_number_smsbower(country_code))
        if not resp.startswith("ACCESS_NUMBER"):
            await asyncio.sleep(2)
            continue

        _, id_, number = resp.split(":")[:3]
        full_number = f"+{number}"
        valid = await check_number_validity(full_number)

        if valid:
            user_sessions[user_id] = (id_, site)
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("📩 دریافت کد دستی", callback_data="checkcode")],
                [InlineKeyboardButton("❌ لغو شماره", callback_data="cancel_number")],
            ])
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"✅ شماره سالم:\n<code>{full_number}</code>\n\n🔄 منتظر دریافت کد...",
                parse_mode=ParseMode.HTML,
                reply_markup=markup
            )
            return
        else:
            await (cancel_number_24sms7(id_) if site == "24sms7" else cancel_number_smsbower(id_))
        await asyncio.sleep(2)

# ------------------ WEB SERVER FOR UPTIMEROBOT ------------------

async def handle(request):
    return web.Response(text="Bot is alive!")

async def start_webserver():
    app = web.Application()
    app.add_routes([web.get('/', handle)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()

# ------------------ MAIN ------------------

async def main():
    await start_webserver()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(site_selected, pattern=r"^site_"))
    app.add_handler(CallbackQueryHandler(country_selected, pattern=r"^country_"))
    app.add_handler(CallbackQueryHandler(cancel_search, pattern="^cancel_search$"))
    app.add_handler(CallbackQueryHandler(check_code, pattern="^checkcode$"))
    app.add_handler(CallbackQueryHandler(cancel_number, pattern="^cancel_number$"))

    print("✅ Bot started...")
    await app.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
