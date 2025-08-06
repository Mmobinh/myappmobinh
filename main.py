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

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY_24SMS7 = os.getenv("API_KEY_24SMS7")
API_KEY_SMSBOWER = os.getenv("API_KEY_SMSBOWER")
API_KEY_TIGER = os.getenv("API_KEY_TIGER")
CHECKER_API_KEY = os.getenv("CHECKER_API_KEY")
SERVICE = "tg"

# Countries and Operators
COUNTRIES_OPERATORS = {
    "24sms7": {
        "Iran": {"code": 57, "operators": [0, 1]},
        "Russia": {"code": 0, "operators": [3, 4]},
        # Define other countries and their operators
    },
    "smsbower": {
        "Kazakhstan": {"code": 2, "operators": [21, 22]},
        # Define other countries and their operators
    },
    "tiger": {
        "Iran": {"code": 57, "operators": [9, 10]},
        "Ukraine": {"code": 1, "operators": [6, 11]},
        # Define other countries and their operators
    }
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

async def fetch_url(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                return await response.text()
    except aiohttp.ClientError as e:
        logging.error(f"Error fetching URL {url}: {e}")
        return "ERROR"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [[InlineKeyboardButton(site.capitalize(), callback_data=f"site_{site}")] for site in COUNTRIES_OPERATORS.keys()]
    await update.message.reply_text("🌐 انتخاب سرویس:", reply_markup=InlineKeyboardMarkup(buttons))

async def site_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    site = query.data.split("_")[1]
    countries = COUNTRIES_OPERATORS.get(site, {})
    
    country_buttons = [InlineKeyboardButton(name, callback_data=f"country_{site}_{info['code']}") for name, info in countries.items()]
    buttons = chunk_buttons(country_buttons, 3)
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")])
    await query.edit_message_text("🌍 انتخاب کشور:", reply_markup=InlineKeyboardMarkup(buttons))

def chunk_buttons(button_list, n):
    return [button_list[i:i + n] for i in range(0, len(button_list), n)]

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, context)

async def country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    query_data = query.data.split("_")
    site = query_data[1]
    country_code = query_data[2]
    country_name = next((name for name, info in COUNTRIES_OPERATORS.get(site, {}).items() if str(info["code"]) == country_code), None)

    if country_name:
        operators = COUNTRIES_OPERATORS[site][country_name]["operators"]
        operator_buttons = [InlineKeyboardButton(f"اپراتور {op}", callback_data=f"operator_{site}_{country_code}_{op}") for op in operators]
        buttons = chunk_buttons(operator_buttons, 2)
        buttons.append([InlineKeyboardButton("🔙 بازگشت به کشورها", callback_data=f"back_to_sites_{site}")])
        await query.edit_message_text("📡 انتخاب اپراتور:", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await query.answer("کشور نامعتبر!", show_alert=True)

async def back_to_sites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    site = query.data.split("_")[2]
    countries = COUNTRIES_OPERATORS.get(site, {})
    
    country_buttons = [InlineKeyboardButton(name, callback_data=f"country_{site}_{info['code']}") for name, info in countries.items()]
    buttons = chunk_buttons(country_buttons, 3)
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")])
    await query.edit_message_text("🌍 انتخاب کشور:", reply_markup=InlineKeyboardMarkup(buttons))

# This is just an example function telling how to search numbers with operator
async def operator_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, site, country_code, operator_id = query.data.split("_")
    await query.answer("وظیفه انتخاب اپراتور از آنجا انجام می‌شود.")  # Add the specific logic

# Implement other handler functions here...

async def main():
    await start_webserver()
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(site_selected, pattern="^site_"))
    application.add_handler(CallbackQueryHandler(back_to_sites, pattern="^back_to_sites_"))
    application.add_handler(CallbackQueryHandler(back_to_start, pattern="^back_to_start$"))
    application.add_handler(CallbackQueryHandler(country_selected, pattern="^country_"))
    application.add_handler(CallbackQueryHandler(operator_selected, pattern="^operator_"))
    # Add other handlers here...
    await application.run_polling()

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())
