import os
import asyncio
import logging
import nest_asyncio
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from aiohttp import web

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY_24SMS7 = os.getenv("API_KEY_24SMS7")
API_KEY_SMSBOWER = os.getenv("API_KEY_SMSBOWER")
API_KEY_TIGER = os.getenv("API_KEY_TIGER")
CHECKER_API_KEY = os.getenv("CHECKER_API_KEY")
SERVICE = "tg"

# Countries and their corresponding codes
COUNTRIES = {
    "24sms7": {
        "Iran": 57,
        "Ukraine": 1,
        "Kazakhstan": 2
        # Add other countries here
    },
    "smsbower": {
        "Kazakhstan": 2
        # Add more countries here
    },
    "tiger": {
        "Iran": 57,
        "Ukraine": 1,
        "Kazakhstan": 2
        # Add other countries here
    }
}

# Example operators
OPERATORS = {
    "Iran": ["MCI", "MTN", "Rightel"],
    "Ukraine": ["Kyivstar", "Vodafone", "Lifecell"],
    "Kazakhstan": ["Beeline", "Kcell"]
}

MAX_PARALLEL_REQUESTS = {
    "24sms7": 1,
    "smsbower": 5,
    "tiger": 1
}

user_sessions = {}
search_tasks = {}
cancel_flags = set()
valid_numbers = {}

async def fetch_url(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                return await response.text()
    except aiohttp.ClientError as e:
        logging.error(f"Error fetching URL {url}: {e}")
        return "ERROR"

async def get_number(site, code, operator):
    base_urls = {
        "24sms7": f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getNumber&service={SERVICE}&country={code}&operator={operator}",
        "smsbower": f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getNumber&service={SERVICE}&country={code}&operator={operator}",
        "tiger": f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getNumber&service={SERVICE}&country={code}&operator={operator}",
    }
    return await fetch_url(base_urls.get(site, ""))

async def check_valid(number):
    url = "http://checker.irbots.com:2021/check"
    params = {"key": CHECKER_API_KEY, "numbers": number.strip("+")}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("status") == "ok" and data["data"].get(f"+{number.strip('+')}", False) is True
    return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [[InlineKeyboardButton(site.capitalize(), callback_data=f"site_{site}")] for site in COUNTRIES.keys()]
    await update.message.reply_text("🌐 انتخاب سرویس:", reply_markup=InlineKeyboardMarkup(buttons))

def chunk_buttons(button_list, n):
    return [button_list[i:i + n] for i in range(0, len(button_list), n)]

async def site_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    site = query.data.split("_")[1]
    countries = COUNTRIES.get(site, {})
    
    country_buttons = [InlineKeyboardButton(name, callback_data=f"country_{site}_{id_}") for name, id_ in countries.items()]
    buttons = chunk_buttons(country_buttons, 3)
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")])
    await query.edit_message_text("🌍 انتخاب کشور:", reply_markup=InlineKeyboardMarkup(buttons))

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, context)

async def country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, site, code = query.data.split("_")
    selected_country = next((name for name, id_ in COUNTRIES[site].items() if str(id_) == code), None)
    
    if selected_country and selected_country in OPERATORS:
        operator_buttons = [InlineKeyboardButton(op, callback_data=f"operator_{site}_{code}_{op}") for op in OPERATORS[selected_country]]
        buttons = chunk_buttons(operator_buttons, 3)
        buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_sites")])
        await query.edit_message_text("🏢 انتخاب اپراتور:", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await query.message.reply_text(text="اپراتوری موجود نیست.")

async def back_to_sites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await site_selected(update, context)

# Define other functions like search_number, cancel_number, and relevant handlers.

async def main():
    await start_webserver()
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(site_selected, pattern="^site_"))
    application.add_handler(CallbackQueryHandler(back_to_sites, pattern="^back_to_sites$"))
    application.add_handler(CallbackQueryHandler(back_to_start, pattern="^back_to_start$"))
    application.add_handler(CallbackQueryHandler(country_selected, pattern="^country_"))
    # Add more handlers for operator selection and other operations
    await application.run_polling()

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())
