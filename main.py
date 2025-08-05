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

# 5sim API token از environment بگیر
API_KEY_5SIM = os.getenv("API_KEY_5SIM")

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

# اضافه کردن 5sim به سایت ها
MAX_PARALLEL_REQUESTS = {
    "24sms7": 1,
    "smsbower": 5,
    "tiger": 1,
    "5sim": 3,  # مثلا 3 درخواست موازی برای 5sim
}

user_sessions = {}
search_tasks = {}
cancel_flags = set()
valid_numbers = {}

# --- توابع مربوط به سرویس 24sms7 ---
async def get_number_24sms7(code):
    url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getNumber&service={SERVICE}&country={code}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def get_code_24sms7(id_):
    url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getStatus&id={id_}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def cancel_number_24sms7(id_):
    url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=setStatus&status=8&id={id_}"
    async with aiohttp.ClientSession() as s:
        await s.get(url)

# --- توابع مربوط به سرویس SMSBower ---
async def get_number_smsbower(code):
    url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getNumber&service={SERVICE}&country={code}&maxPrice=58.67&providerIds=2195,2194,2196&exceptProviderIds=1000&phoneException=7700,7708"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def get_code_smsbower(id_):
    url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getStatus&id={id_}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def cancel_number_smsbower(id_):
    url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=setStatus&status=8&id={id_}"
    async with aiohttp.ClientSession() as s:
        await s.get(url)

# --- توابع مربوط به سرویس Tiger SMS ---
async def get_number_tiger(code):
    url = f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getNumber&service={SERVICE}&country={code}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def get_code_tiger(id_):
    url = f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getStatus&id={id_}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def cancel_number_tiger(id_):
    url = f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=setStatus&status=8&id={id_}"
    async with aiohttp.ClientSession() as s:
        await s.get(url)

# --- توابع جدید برای 5sim ---
async def get_products_5sim(country, operator):
    url = f"https://5sim.net/v1/guest/products/{country}/{operator}"
    headers = {
        "Accept": "application/json"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            return await resp.json()

async def buy_activation_5sim(country, operator, product):
    url = f"https://5sim.net/v1/user/buy/activation/{country}/{operator}/{product}"
    headers = {
        "Authorization": f"Bearer {API_KEY_5SIM}",
        "Accept": "application/json"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            return await resp.json()

async def check_order_5sim(order_id):
    url = f"https://5sim.net/v1/user/check/{order_id}"
    headers = {
        "Authorization": f"Bearer {API_KEY_5SIM}",
        "Accept": "application/json"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            return await resp.json()

async def cancel_order_5sim(order_id):
    url = f"https://5sim.net/v1/user/cancel/{order_id}"
    headers = {
        "Authorization": f"Bearer {API_KEY_5SIM}",
        "Accept": "application/json"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            return await resp.json()

# --- توابع اصلی get_number, get_code, cancel_number با پشتیبانی از 5sim ---

async def get_number(site, code, operator=None, product=None):
    if site == "24sms7":
        return await get_number_24sms7(code)
    elif site == "smsbower":
        return await get_number_smsbower(code)
    elif site == "tiger":
        return await get_number_tiger(code)
    elif site == "5sim":
        # برای 5sim باید operator و product مشخص باشد
        if not operator or not product:
            return None
        return await buy_activation_5sim(code, operator, product)
    else:
        return None

async def get_code(site, id_):
    if site == "24sms7":
        return await get_code_24sms7(id_)
    elif site == "smsbower":
        return await get_code_smsbower(id_)
    elif site == "tiger":
        return await get_code_tiger(id_)
    elif site == "5sim":
        return await check_order_5sim(id_)
    else:
        return None

async def cancel_number(site, id_):
    if site == "24sms7":
        await cancel_number_24sms7(id_)
    elif site == "smsbower":
        await cancel_number_smsbower(id_)
    elif site == "tiger":
        await cancel_number_tiger(id_)
    elif site == "5sim":
        await cancel_order_5sim(id_)

# تابع check_valid بدون تغییر می‌ماند

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

# باقی کد بدون تغییر باقی می‌ماند
# (توابع start، site_selected، country_selected و...)

# فقط باید در بخش انتخاب سایت دکمه 5sim اضافه کنی:

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("24sms7", callback_data="site_24sms7")],
        [InlineKeyboardButton("SMSBower", callback_data="site_smsbower")],
        [InlineKeyboardButton("Tiger SMS", callback_data="site_tiger")],
        [InlineKeyboardButton("5sim", callback_data="site_5sim")],  # اضافه شده
    ]
    await update.message.reply_text("🌐 انتخاب سرویس:", reply_markup=InlineKeyboardMarkup(buttons))

# و در site_selected هم اضافه کن:

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
    elif site == "5sim":
        # برای 5sim باید کشور و اپراتور رو از API بگیری (یا ثابت تعریف کنی)
        # اینجا برای نمونه یک دیکشنری ساده:
        countries = {
            "ru": "Russia",
            "us": "USA",
            "uk": "United Kingdom",
            # ... اگر نیاز داری کامل‌تر کن
        }
        # توجه: تو callback_data مقدار country و operator باید ذخیره بشه (کمی پیچیده‌تر)
    else:
        countries = {}

    # دکمه‌ها را مطابق countries بساز (برای 5sim باید اپراتور هم باشه، پس کمی تغییر نیاز داره)

    buttons = []
    if site != "5sim":
        buttons = [[InlineKeyboardButton(name, callback_data=f"country_{site}_{id_}")] for name, id_ in countries.items()]
    else:
        # نمونه دکمه برای 5sim (تنها کشور، اپراتور رو باید جدا انتخاب کنی یا ثابت بزاری)
        for country_code, country_name in countries.items():
            buttons.append([InlineKeyboardButton(country_name, callback_data=f"country_5sim_{country_code}_operator")])
        # operator را هم باید به همین شکل پیاده کنی

    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")])
    await query.edit_message_text("🌍 انتخاب کشور:", reply_markup=InlineKeyboardMarkup(buttons))

# --- اینجا کد خیلی مفصل می‌شود برای 5sim چون ساختار API کمی متفاوت است، ولی این کلیت اضافه کردن API است. ---

# ادامه کد main و handler ها بدون تغییر باقی می‌ماند

async def main():
    await start_webserver()
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(site_selected, pattern="^site_"))
    application.add_handler(CallbackQueryHandler(back_to_sites, pattern="^back_to_sites$"))
    application.add_handler(CallbackQueryHandler(back_to_start, pattern="^back_to_start$"))
    application.add_handler(CallbackQueryHandler(country_selected, pattern="^country_"))
    application.add_handler(CallbackQueryHandler(cancel_search, pattern="^cancel_search$"))
    application.add_handler(CallbackQueryHandler(dynamic_check_code, pattern="^checkcode_"))
    application.add_handler(CallbackQueryHandler(dynamic_cancel_number, pattern="^cancel_"))
    await application.run_polling()

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())
