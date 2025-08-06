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
    "macao": 20,
    "irland": 23,
    "serbia": 29,
    "romani": 32,
    "estonia": 34,
    "germany": 43,
    "auustria": 50,
    "belarus": 51,
    "tiwan": 55,
    "newziland": 67,
    "belgium": 82,
    "moldova": 85,
    "armenia": 148,
    "maldiv": 159,
    "guadlouap": 160,
    "denmark": 172,
    "norway": 174,
    "switzerland": 173,
    "giblarator": 201,
    "Country Slot 8": 0,
    "Country Slot 9": 0,
    "Country Slot 10": 0,
}

COUNTRIES_SMSBOWER = {
    "Kazakhstan": 2,
    "Country Slot 1": 0,
    "Country Slot 2": 0,
    "try Slot 3": 0,
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
    "armanei": 148,
    "Mexico": 54,
    "Italy": 86,
    "Spain": 56,
    "Czech Republic": 63,
    "Kazakhstan": 2,
    "Paraguay": 87,
    "Hong Kong": 14,
    "macao": 20,
    "irland": 23,
    "serbia": 29,
    "romani": 32,
    "estonia": 34,
    "germany": 43,
    "auustria": 50,
    "belarus": 51,
    "tiwan": 55,
    "newziland": 67,
    "belgium": 82,
    "moldova": 85,
    "armenia": 148,
    "maldiv": 159,
    "guadlouap": 160,
    "denmark": 172,
    "norway": 174,
    "switzerland": 173,
    "giblarator": 201,
    "peru": 65,
    "Country Slot 2": 0,
    "try Slot 3": 0,
    "england": 16,
    "uzbekistan": 40,
    "zimbabwe": 96,
    "zambie": 147,
    "bolivi": 92,
    "Country Slot 9": 0,
    "Country Slot 10": 0,
}

MAX_PARALLEL_REQUESTS = {
    "24sms7": 1,
    "smsbower": 5,
    "tiger": 1,
}

user_sessions = {}
search_tasks = {}
cancel_flags = set()
valid_numbers = {}

async def get_number_24sms7(code):
    url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getNumber&service={SERVICE}&country={code}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def get_number_smsbower(code):
    url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getNumber&service={SERVICE}&country={code}&maxPrice=58.67&providerIds=2195,2194,2196,1000&exceptProviderIds=&phoneException=7700,7708"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def get_number_tiger(code):
    url = f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getNumber&service={SERVICE}&country={code}&maxPrice=60&providerIds=55,188,234"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def get_code(site, id_):
    url = {
        "24sms7": f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getStatus&id={id_}",
        "smsbower": f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getStatus&id={id_}",
        "tiger": f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getStatus&id={id_}",
    }[site]
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def cancel_number(site, id_):
    url = {
        "24sms7": f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=setStatus&status=8&id={id_}",
        "smsbower": f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=setStatus&status=8&id={id_}",
        "tiger": f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=setStatus&status=8&id={id_}",
    }[site]
    async with aiohttp.ClientSession() as s:
        await s.get(url)

async def check_valid(number):
    url = "http://checker.irbots.com:2021/check"
    params = {"key": CHECKER_API_KEY, "numbers": number.strip("+")}
    async with aiohttp.ClientSession() as s:
        async with s.get(url, params=params) as r:
            if r.status == 200:
                data = await r.json()
                status = data.get("status")
                if status == "ok":
                    result = data.get("data", {}).get(f"+{number.strip('+')}", False)
                    return result is True
    return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("24sms7", callback_data="site_24sms7")],
        [InlineKeyboardButton("SMSBower", callback_data="site_smsbower")],
        [InlineKeyboardButton("Tiger SMS", callback_data="site_tiger")],
    ]
    await update.message.reply_text("🌐 انتخاب سرویس:", reply_markup=InlineKeyboardMarkup(buttons))

def chunk_buttons(button_list, n):
    return [button_list[i:i + n] for i in range(0, len(button_list), n)]

async def site_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    site = query.data.split("_")[1]
    if site == "24sms7":
        countries = COUNTRIES_24SMS7
    elif site == "smsbower":
        countries = COUNTRIES_SMSBOWER
    elif site == "tiger":
        countries = COUNTRIES_TIGER_SMS
    else:
        countries = {}

    country_buttons = [InlineKeyboardButton(name, callback_data=f"country_{site}_{id_}") for name, id_ in countries.items()]
    buttons = chunk_buttons(country_buttons, 3)
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")])
    
    await query.edit_message_text("🌍 انتخاب کشور:", reply_markup=InlineKeyboardMarkup(buttons))

async def back_to_sites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    buttons = [
        [InlineKeyboardButton("24sms7", callback_data="site_24sms7")],
        [InlineKeyboardButton("SMSBower", callback_data="site_smsbower")],
        [InlineKeyboardButton("Tiger SMS", callback_data="site_tiger")],
    ]
    await query.edit_message_text("🌐 انتخاب سرویس:", reply_markup=InlineKeyboardMarkup(buttons))

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    buttons = [
        [InlineKeyboardButton("24sms7", callback_data="site_24sms7")],
        [InlineKeyboardButton("SMSBower", callback_data="site_smsbower")],
        [InlineKeyboardButton("Tiger SMS", callback_data="site_tiger")],
    ]
    await query.edit_message_text("🌐 انتخاب سرویس:", reply_markup=InlineKeyboardMarkup(buttons))

async def country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, site, code = query.data.split("_")
    user_id = query.from_user.id
    cancel_flags.discard(user_id)
    valid_numbers[user_id] = []
    msg = await query.edit_message_text("⏳ جستجو برای شماره سالم...", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ کنسل جستجو", callback_data="cancel_search")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_sites")]
    ]))

    max_requests = MAX_PARALLEL_REQUESTS.get(site, 1)

    async def run_parallel_search(i):
        try:
            await search_number(user_id, query.message.chat_id, msg.message_id, code, site, context)
        except asyncio.CancelledError:
            pass

    tasks = [asyncio.create_task(run_parallel_search(i)) for i in range(max_requests)]
    search_tasks[user_id] = tasks

async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    cancel_flags.add(user_id)
    if user_id in search_tasks:
        for task in search_tasks[user_id]:
            task.cancel()
        search_tasks.pop(user_id, None)
    await query.edit_message_text("❌ جستجو کنسل شد.", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")]
    ]))

async def search_number(user_id, chat_id, message_id, country_code, site, context):
    if site == "24sms7":
        get_number = get_number_24sms7
    elif site == "smsbower":
        get_number = get_number_smsbower
    elif site == "tiger":
        get_number = get_number_tiger
    else:
        return

    while True:
        if user_id in cancel_flags:
            cancel_flags.discard(user_id)
            break

        response = await get_number(country_code)
        if "ACCESS_NUMBER" in response:
            parts = response.split(":")
            if len(parts) >= 3:
                id_ = parts[1]
                number = parts[2]
                is_valid = await check_valid(number)
                if is_valid:
                    valid_numbers[user_id].append(number)
                    text = f"✅ شماره سالم یافت شد:\n`{number}`"
                    buttons = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🆗 پایان", callback_data="stop_search")],
                        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")],
                    ])
                    await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, reply_markup=buttons, parse_mode=ParseMode.MARKDOWN)
                    break
                else:
                    await cancel_number(site, id_)
            else:
                await asyncio.sleep(3)
        else:
            await asyncio.sleep(3)

async def stop_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id in search_tasks:
        for task in search_tasks[user_id]:
            task.cancel()
        search_tasks.pop(user_id, None)
    await query.edit_message_text("🔴 عملیات متوقف شد.", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")]
    ]))

def main():
    nest_asyncio.apply()
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(site_selected, pattern=r"^site_"))
    application.add_handler(CallbackQueryHandler(country_selected, pattern=r"^country_"))
    application.add_handler(CallbackQueryHandler(cancel_search, pattern=r"^cancel_search$"))
    application.add_handler(CallbackQueryHandler(back_to_sites, pattern=r"^back_to_sites$"))
    application.add_handler(CallbackQueryHandler(back_to_start, pattern=r"^back_to_start$"))
    application.add_handler(CallbackQueryHandler(stop_search, pattern=r"^stop_search$"))

    application.run_polling()

if __name__ == "__main__":
    main()
