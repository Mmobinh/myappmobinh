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
API_KEY_TIGER = os.getenv("API_KEY_TIGER")
API_KEY_5SIM = os.getenv("API_KEY_5SIM")
SERVICE = "tg"

COUNTRIES_24SMS7 = {
    "Iran": 57,
    "Russia": 0,
    "Ukraine": 1,
    "Mexico": 54,
    "Italy": 86,
    "Spain": 56,
    "Czech Republic": 63,
    "Kazakhstan": 2,
    "Paraguay": 87,
    "Hong Kong": 14,
    "Country Slot 1": 0,
    "Country Slot 2": 0,
    "Country Slot 3": 0,
    "Country Slot 4": 0,
    "Country Slot 5": 0,
}

COUNTRIES_SMSBOWER = {
    "Kazakhstan": 2,
    "Country Slot 1": 0,
    "Country Slot 2": 0,
    "Country Slot 3": 0,
    "Country Slot 4": 0,
    "Country Slot 5": 0,
    "Country Slot 6": 0,
    "Country Slot 7": 0,
    "Country Slot 8": 0,
    "Country Slot 9": 0,
    "Country Slot 10": 0,
}

COUNTRIES_TIGER_SMS = {
    "Iran": 57,
    "Russia": 0,
    "Ukraine": 1,
    "Country Slot 1": 0,
    "Country Slot 2": 0,
    "Country Slot 3": 0,
    "Country Slot 4": 0,
    "Country Slot 5": 0,
    "Country Slot 6": 0,
    "Country Slot 7": 0,
    "Country Slot 8": 0,
    "Country Slot 9": 0,
    "Country Slot 10": 0,
}

COUNTRIES_5SIM = {
    "Russia": "russia",
    "USA": "usa",
    "Ukraine": "ukraine",
    "UK": "england",
    "Germany": "germany",
    "India": "india",
}

MAX_PARALLEL_REQUESTS = {
    "24sms7": 1,
    "smsbower": 5,
    "tiger": 1,
    "5sim": 1,
}

user_sessions = {}
search_tasks = {}
cancel_flags = set()
valid_numbers = {}

async def get_number_5sim(code):
    url = f"https://5sim.net/v1/user/buy/activation/any/{code}/{SERVICE}"
    headers = {"Authorization": f"Bearer {API_KEY_5SIM}"}
    async with aiohttp.ClientSession(headers=headers) as s:
        async with s.get(url) as r:
            if r.status == 200:
                data = await r.json()
                return f"ACCESS_NUMBER:{data['id']}:{data['phone']}"
            return "NO_NUMBER"

async def get_number_24sms7(code):
    url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getNumber&service={SERVICE}&country={code}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def get_number_smsbower(code):
    url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getNumber&service={SERVICE}&country={code}&maxPrice=58.67&providerIds=2195,2194,2196&exceptProviderIds=1000&phoneException=7700,7708"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def get_number_tiger(code):
    url = f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getNumber&service={SERVICE}&country={code}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def get_code(site, id_):
    if site == "5sim":
        url = f"https://5sim.net/v1/user/check/{id_}"
        headers = {"Authorization": f"Bearer {API_KEY_5SIM}"}
        async with aiohttp.ClientSession(headers=headers) as s:
            async with s.get(url) as r:
                if r.status == 200:
                    data = await r.json()
                    if data["sms"]:
                        return f"STATUS_OK:{data['sms'][0]['code']}"
                    return "STATUS_WAIT_CODE"
                return "ERROR"
    url = {
        "24sms7": f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getStatus&id={id_}",
        "smsbower": f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getStatus&id={id_}",
        "tiger": f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getStatus&id={id_}",
    }[site]
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def cancel_number(site, id_):
    if site == "5sim":
        url = f"https://5sim.net/v1/user/cancel/{id_}"
        headers = {"Authorization": f"Bearer {API_KEY_5SIM}"}
        async with aiohttp.ClientSession(headers=headers) as s:
            await s.get(url)
        return
    url = {
        "24sms7": f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=setStatus&status=8&id={id_}",
        "smsbower": f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=setStatus&status=8&id={id_}",
        "tiger": f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=setStatus&status=8&id={id_}",
    }[site]
    async with aiohttp.ClientSession() as s:
        await s.get(url)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("24sms7", callback_data="site_24sms7")],
        [InlineKeyboardButton("SMSBower", callback_data="site_smsbower")],
        [InlineKeyboardButton("Tiger SMS", callback_data="site_tiger")],
        [InlineKeyboardButton("5sim", callback_data="site_5sim")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "لطفاً یک سایت انتخاب کنید:", reply_markup=reply_markup
    )

async def site_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    site = query.data.split("_")[1]
    user_sessions[query.from_user.id] = {"site": site}
    # بر اساس سایت، کشورها را تنظیم کن
    if site == "24sms7":
        countries = COUNTRIES_24SMS7
    elif site == "smsbower":
        countries = COUNTRIES_SMSBOWER
    elif site == "tiger":
        countries = COUNTRIES_TIGER_SMS
    elif site == "5sim":
        countries = COUNTRIES_5SIM
    else:
        countries = {}

    keyboard = [
        [InlineKeyboardButton(country, callback_data=f"country_{code}")]
        for country, code in countries.items()
    ]
    keyboard.append([InlineKeyboardButton("بازگشت", callback_data="back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "لطفاً کشور را انتخاب کنید:", reply_markup=reply_markup
    )

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_sessions.pop(query.from_user.id, None)
    await query.edit_message_text("دوباره یک سایت انتخاب کنید:")
    await start(update, context)

async def country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    site = user_sessions[user_id]["site"]

    # کشور انتخابی
    data = query.data
    country_code = data.split("_")[1]

    user_sessions[user_id]["country_code"] = country_code

    # شروع گرفتن شماره
    await query.edit_message_text("در حال دریافت شماره...")

    if site == "24sms7":
        get_number_func = get_number_24sms7
    elif site == "smsbower":
        get_number_func = get_number_smsbower
    elif site == "tiger":
        get_number_func = get_number_tiger
    elif site == "5sim":
        get_number_func = get_number_5sim
    else:
        get_number_func = None

    if not get_number_func:
        await query.edit_message_text("سایت انتخاب شده پشتیبانی نمی‌شود.")
        return

    async def search_number():
        while True:
            if user_id in cancel_flags:
                cancel_flags.remove(user_id)
                await query.edit_message_text("جستجو لغو شد.")
                return

            number_info = await get_number_func(country_code)

            if "NO_NUMBER" not in number_info and "ACCESS_NUMBER" in number_info:
                parts = number_info.split(":")
                id_ = parts[1]
                phone = parts[2]
                valid_numbers[user_id] = {"id": id_, "phone": phone, "site": site}
                await query.edit_message_text(f"شماره دریافت شد: {phone}\nدر حال انتظار پیام...")
                await auto_check_code(update, context, id_, site)
                return
            await asyncio.sleep(5)

            if user_id in search_tasks:
    search_tasks[user_id].cancel()
    del search_tasks[user_id]

task = asyncio.create_task(search_number())
search_tasks[user_id] = task

async def auto_check_code(update: Update, context: ContextTypes.DEFAULT_TYPE, id_: str, site: str): for _ in range(60): result = await get_code(site, id_) if "STATUS_OK" in result: code = result.split(":")[1] await update.callback_query.message.reply_text(f"کد دریافت شد: {code}", parse_mode=ParseMode.MARKDOWN) return await asyncio.sleep(2) await update.callback_query.message.reply_text("زمان دریافت کد به پایان رسید. شماره لغو شد.") await cancel_number(site, id_)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE): user_id = update.effective_user.id cancel_flags.add(user_id) await update.message.reply_text("درخواست لغو ارسال شد.")

async def main(): application = ApplicationBuilder().token(BOT_TOKEN).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("cancel", cancel))
application.add_handler(CallbackQueryHandler(back_to_start, pattern="^back$"))
application.add_handler(CallbackQueryHandler(site_selected, pattern="^site_"))
application.add_handler(CallbackQueryHandler(country_selected, pattern="^country_"))

await application.run_polling()

if name == "main": nest_asyncio.apply() asyncio.get_event_loop().run_until_complete(main())



