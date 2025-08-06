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
}

COUNTRIES_SMSBOWER = {
    "Kazakhstan": 2,
    # ... (بقیه کشورها اگر لازم بود اضافه کنید)
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
}

OPERATORS = {
    "smsbower": {
        "All": "",
        "2195": "2195",
        "2194": "2194",
        "2196": "2196",
        "1000": "1000",
        "3134": "3134",
        "2887": "2887",
    },
    "tiger": {
        "All": "",
        "Provider 55": "55",
        "Provider 188": "188",
        "Provider 234": "234",
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

async def get_number_24sms7(code):
    url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getNumber&service={SERVICE}&country={code}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def get_number_smsbower(code, operator=""):
    url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getNumber&service={SERVICE}&country={code}&maxPrice=58.67&providerIds={operator}&exceptProviderIds=&phoneException=7700,7708"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def get_number_tiger(code, operator=""):
    url = f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getNumber&service={SERVICE}&country={code}&maxPrice=60&providerIds={operator}"
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

    if site in OPERATORS:
        operator_buttons = [InlineKeyboardButton(name, callback_data=f"operator_{site}_{id_}") for name, id_ in OPERATORS[site].items()]
        buttons = chunk_buttons(operator_buttons, 2)
        buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")])
        await query.edit_message_text("📡 انتخاب اپراتور:", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await show_countries(query, site, context)

async def show_countries(query, site, context, operator=""):
    if site == "24sms7":
        countries = COUNTRIES_24SMS7
    elif site == "smsbower":
        countries = COUNTRIES_SMSBOWER
    elif site == "tiger":
        countries = COUNTRIES_TIGER_SMS
    else:
        countries = {}

    country_buttons = [InlineKeyboardButton(name, callback_data=f"country_{site}_{operator}_{id_}") for name, id_ in countries.items()]
    buttons = chunk_buttons(country_buttons, 3)
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")])
    await query.edit_message_text("🌍 انتخاب کشور:", reply_markup=InlineKeyboardMarkup(buttons))

async def back_to_sites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await site_selected(update, context)

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
    msg = await query.edit_message_text("⏳ جستجو برای شماره سالم...", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ کنسل جستجو", callback_data="cancel_search")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_sites")]
    ]))

    max_requests = MAX_PARALLEL_REQUESTS.get(site, 1)

    async def run_parallel_search(i):
        try:
            await search_number(user_id, query.message.chat_id, msg.message_id, code, site, context, operator)
        except asyncio.CancelledError:
            pass

    tasks = [asyncio.create_task(run_parallel_search(i)) for i in range(max_requests)]
    search_tasks[user_id] = tasks

async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    cancel_flags.add(user_id)
    valid_numbers[user_id] = []

    tasks = search_tasks.get(user_id, [])
    for task in tasks:
        task.cancel()
    search_tasks.pop(user_id, None)

    await query.answer("جستجو لغو شد.")
    await query.edit_message_text("جستجو لغو شد. برای شروع دوباره /start را ارسال کنید.")

async def search_number(user_id, chat_id, msg_id, country_code, site, context, operator=""):
    while user_id not in cancel_flags:
        if site == "24sms7":
            number_response = await get_number_24sms7(country_code)
        elif site == "smsbower":
            number_response = await get_number_smsbower(country_code, operator)
        elif site == "tiger":
            number_response = await get_number_tiger(country_code, operator)
        else:
            return

        if number_response.startswith("ACCESS_NUMBER"):
            parts = number_response.split(":")
            id_ = parts[1].strip()
            number = parts[2].strip()

            is_valid = await check_valid(number)
            if is_valid:
                valid_numbers.setdefault(user_id, []).append(number)
                text = f"✅ شماره سالم یافت شد:\n`{number}`\n\n🆔 شماره ID: `{id_}`"
                await context.bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, parse_mode=ParseMode.MARKDOWN,
                                                    reply_markup=InlineKeyboardMarkup([
                                                        [InlineKeyboardButton("لغو شماره", callback_data=f"cancel_{site}_{id_}")]
                                                    ]))
                return
            else:
                # شماره نامعتبر را لغو کن
                await cancel_number(site, id_)
        elif number_response == "NO_NUMBERS":
            await context.bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                                text="⚠️ شماره‌ای برای کشور و اپراتور انتخاب شده موجود نیست. لطفا کشور یا اپراتور دیگری را انتخاب کنید.",
                                                reply_markup=InlineKeyboardMarkup([
                                                    [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_sites")]
                                                ]))
            return
        else:
            await asyncio.sleep(1)

async def dynamic_cancel_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    _, site, id_ = data.split("_")
    user_id = query.from_user.id
    # اجازه لغو شماره‌های سالم رو میده
    await cancel_number(site, id_)
    if user_id in valid_numbers and valid_numbers[user_id]:
        try:
            valid_numbers[user_id].remove(id_)
        except ValueError:
            pass
    await query.edit_message_text("شماره لغو شد. جستجوی شماره ادامه دارد...")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == "back_to_start":
        await back_to_start(update, context)
    elif data == "back_to_sites":
        await back_to_sites(update, context)
    elif data == "cancel_search":
        await cancel_search(update, context)
    elif data.startswith("site_"):
        await site_selected(update, context)
    elif data.startswith("operator_"):
        parts = data.split("_")
        site = parts[1]
        operator = parts[2]
        await show_countries(update.callback_query, site, context, operator)
    elif data.startswith("country_"):
        await country_selected(update, context)
    elif data.startswith("cancel_"):
        await dynamic_cancel_number(update, context)

async def main():
    nest_asyncio.apply()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
