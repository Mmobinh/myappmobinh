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
    "cameron": 41,
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
        operator_buttons = [
            InlineKeyboardButton(name, callback_data=f"operator_{site}_{id_}")
            for name, id_ in OPERATORS[site].items()
        ]
        buttons = chunk_buttons(operator_buttons, 2)
        buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")])
        await query.edit_message_text("📡 انتخاب اپراتور:", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await show_countries(query, site, context)

async def operator_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    site = parts[1]
    operator = parts[2]
    await show_countries(query, site, context, operator)

async def show_countries(query, site, context, operator=""):
    if site == "24sms7":
        countries = COUNTRIES_24SMS7
    elif site == "smsbower":
        countries = COUNTRIES_SMSBOWER
    elif site == "tiger":
        countries = COUNTRIES_TIGER_SMS
    else:
        countries = {}

    country_buttons = [
        InlineKeyboardButton(name, callback_data=f"country_{site}_{operator}_{id_}")
        for name, id_ in countries.items()
    ]
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
    data = query.data.split("_")
    site = data[1]
    operator = data[2]
    country_code = data[3]

    await query.edit_message_text("⏳ در حال دریافت شماره...")

    try:
        if site == "24sms7":
            response = await get_number_24sms7(country_code)
        elif site == "smsbower":
            response = await get_number_smsbower(country_code, operator)
        elif site == "tiger":
            response = await get_number_tiger(country_code, operator)
        else:
            response = None

        if response is None or response == "NO_NUMBERS":
            await query.edit_message_text("❌ شماره‌ای موجود نیست، لطفا کشور دیگری انتخاب کنید.")
            return

        number_id = response.split(":")[1]
        number = response.split(":")[0]

        # ذخیره در سشن کاربر
        user_sessions[query.from_user.id] = {
            "site": site,
            "id": number_id,
            "number": number,
            "operator": operator,
            "country": country_code,
        }

        await query.edit_message_text(
            f"✅ شماره دریافت شد:\n`{number}`\nبرای دریافت کد روی دکمه زیر بزنید.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("دریافت کد", callback_data="get_code")],
                 [InlineKeyboardButton("لغو", callback_data="cancel_number")]]
            ),
        )
    except Exception as e:
        await query.edit_message_text(f"❌ خطا در دریافت شماره: {e}")

async def get_code_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    session = user_sessions.get(query.from_user.id)
    if not session:
        await query.edit_message_text("❌ شماره‌ای برای دریافت کد موجود نیست.")
        return

    site = session["site"]
    number_id = session["id"]

    await query.edit_message_text("⏳ در حال دریافت کد...")

    for _ in range(30):  # 30 بار چک کن، هر بار 5 ثانیه فاصله
        code_response = await get_code(site, number_id)
        if "STATUS_OK" in code_response:
            code = code_response.split(":")[1]
            await query.edit_message_text(f"✅ کد دریافت شد:\n`{code}`", parse_mode=ParseMode.MARKDOWN)
            valid_numbers[query.from_user.id] = session["number"]
            return
        elif "STATUS_CANCEL" in code_response:
            await query.edit_message_text("❌ شماره لغو شده است.")
            return
        await asyncio.sleep(5)

    await query.edit_message_text("⏰ زمان دریافت کد تمام شد.")

async def cancel_number_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    session = user_sessions.get(query.from_user.id)
    if not session:
        await query.edit_message_text("❌ شماره‌ای برای لغو موجود نیست.")
        return

    site = session["site"]
    number_id = session["id"]

    await cancel_number(site, number_id)
    await query.edit_message_text("✅ شماره لغو شد.")
    user_sessions.pop(query.from_user.id, None)

async def check_valid_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    number = valid_numbers.get(query.from_user.id)
    if not number:
        await query.edit_message_text("❌ شماره‌ای برای بررسی وجود ندارد.")
        return

    valid = await check_valid(number)
    if valid:
        await query.edit_message_text(f"✅ شماره `{number}` معتبر است.", parse_mode=ParseMode.MARKDOWN)
    else:
        await query.edit_message_text(f"❌ شماره `{number}` معتبر نیست.", parse_mode=ParseMode.MARKDOWN)

def main():
    nest_asyncio.apply()
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(site_selected, pattern=r"^site_"))
    application.add_handler(CallbackQueryHandler(operator_selected, pattern=r"^operator_"))
    application.add_handler(CallbackQueryHandler(country_selected, pattern=r"^country_"))
    application.add_handler(CallbackQueryHandler(back_to_start, pattern="back_to_start"))
    application.add_handler(CallbackQueryHandler(get_code_callback, pattern="get_code"))
    application.add_handler(CallbackQueryHandler(cancel_number_callback, pattern="cancel_number"))
    application.add_handler(CallbackQueryHandler(check_valid_callback, pattern="check_valid"))

    # aiohttp server for webhook or healthcheck if needed
    # runner = web.AppRunner(app) ...

    application.run_polling()

if __name__ == "__main__":
    main()
