import os
import asyncio
import logging
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY_24SMS7 = os.getenv("API_KEY_24SMS7")
API_KEY_SMSBOWER = os.getenv("API_KEY_SMSBOWER")
API_KEY_TIGER = os.getenv("API_KEY_TIGER")
CHECKER_API_KEY = os.getenv("CHECKER_API_KEY")
SERVICE = "tg"

if not all([BOT_TOKEN, API_KEY_24SMS7, API_KEY_SMSBOWER, API_KEY_TIGER, CHECKER_API_KEY]):
    raise ValueError("API keys and bot token must be provided.")

COUNTRIES_24SMS7 = {
    "Iran": 57, "Russia": 0, "Ukraine": 1, "Mexico": 54, "Italy": 86, "Spain": 56,
}

COUNTRIES_SMSBOWER = {
    "Kazakhstan": 2, "Iran": 57, "Russia": 0, "Ukraine": 1, "Mexico": 54, "Italy": 86, "Spain": 56, "Cameron": 41,
}

COUNTRIES_TIGER_SMS = {
    "Iran": 57, "Russia": 0, "Ukraine": 1,
}

OPERATORS = {
    "smsbower": {"All": "", "2195": "2195", "2194": "2194", "1000": "1000", "2887": "2887", "3134": "3134"},
    "tiger": {"All": "", "Provider 55": "55", "188": "188", "234": "234"},
}

MAX_PARALLEL_REQUESTS = {"24sms7": 1, "smsbower": 5, "tiger": 1}

cancel_flags = set()
valid_numbers = {}
tasks = {}

async def safe_request(url, params=None):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                response.raise_for_status()
                return await response.text()
    except aiohttp.ClientError as e:
        logging.error(f"HTTP error occurred: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
    return None

async def get_number_24sms7(code):
    url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getNumber&service={SERVICE}&country={code}"
    return await safe_request(url)

async def get_number_smsbower(code, operator=""):
    url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getNumber&service={SERVICE}&country={code}&providerIds={operator}"
    return await safe_request(url)

async def get_number_tiger(code, operator=""):
    url = f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getNumber&service={SERVICE}&country={code}&providerIds={operator}"
    return await safe_request(url)

async def check_valid(number):
    url = "http://checker.irbots.com:2021/check"
    params = {"key": CHECKER_API_KEY, "numbers": number.strip("+")}
    response = await safe_request(url, params)
    if response:
        data = await aiohttp.ClientResponse.json(response)
        if data.get("status") == "ok":
            return data.get("data", {}).get(number.strip("+"), False)
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
    if site in OPERATORS:
        operator_buttons = [InlineKeyboardButton(name, callback_data=f"operator_{site}_{id_}") for name, id_ in OPERATORS[site].items()]
        buttons = chunk_buttons(operator_buttons, 2)
        buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")])
        await query.edit_message_text("📡 انتخاب اپراتور:", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await show_countries(query, site, context)

async def show_countries(query, site, context, operator=""):
    countries = {
        "24sms7": COUNTRIES_24SMS7,
        "smsbower": COUNTRIES_SMSBOWER,
        "tiger": COUNTRIES_TIGER_SMS,
    }.get(site, {})
    country_buttons = [InlineKeyboardButton(name, callback_data=f"country_{site}_{operator}_{id_}") for name, id_ in countries.items()]
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
    _, site, operator, code = query.data.split("_")
    user_id = query.from_user.id
    cancel_flags.discard(user_id)
    valid_numbers[user_id] = []
    msg = await query.edit_message_text(
        "⏳ جستجو برای شماره سالم...",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("❌ کنسل جستجو", callback_data="cancel_search")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")],
            ]
        ),
    )
    max_requests = MAX_PARALLEL_REQUESTS.get(site, 1)

    async def search_loop():
        tries = 0
        while user_id not in cancel_flags and tries < 100:
            tries += 1
            if site == "24sms7":
                number_response = await get_number_24sms7(code)
            elif site == "smsbower":
                number_response = await get_number_smsbower(code, operator)
            else:
                number_response = await get_number_tiger(code, operator)

            if number_response and number_response.startswith("ACCESS_NUMBER"):
                number = number_response.split(":")[-1].strip()
                is_valid = await check_valid(number)
                if is_valid:
                    valid_numbers[user_id].append(number)
                    await context.bot.send_message(user_id, f"✅ شماره سالم پیدا شد: `{number}`", parse_mode="Markdown")
                    break
            if tries % 10 == 0:
                await context.bot.send_message(user_id, f"🔄 تلاش {tries}: هنوز در حال جستجو...")
            await asyncio.sleep(5)
        
        if tries >= 100:
            await context.bot.send_message(user_id, "🔍 جستجو به پایان رسید بدون یافتن شماره معتبر.")

    tasks[user_id] = asyncio.create_task(search_loop())

async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id in tasks:
        tasks[user_id].cancel()
    cancel_flags.add(user_id)
    await query.edit_message_text("❌ جستجو لغو شد.")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    if data.startswith("site_"):
        await site_selected(update, context)
    elif data.startswith("operator_"):
        _, site, operator = data.split("_")
        await show_countries(update.callback_query, site, context, operator)
    elif data.startswith("country_"):
        await country_selected(update, context)
    elif data == "cancel_search":
        await cancel_search(update, context)
    elif data == "back_to_start":
        await back_to_start(update, context)

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.run_polling()

if __name__ == "__main__":
    main()


