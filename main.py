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

MAX_PARALLEL_REQUESTS = {
    "24sms7": 1,
    "smsbower": 5,
    "tiger": 1,
}

user_sessions = {}
search_tasks = {}
cancel_flags = set()
valid_numbers = {}

# --------------- 5SIM FUNCTIONS -----------------

async def get_number_5sim(country, operator, product):
    url = f"https://5sim.net/v1/user/buy/activation/{country}/{operator}/{product}"
    headers = {"Authorization": f"Bearer {API_KEY_5SIM}"}
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=headers) as r:
            return await r.json()

async def get_code_5sim(id_):
    url = f"https://5sim.net/v1/user/check/{id_}"
    headers = {"Authorization": f"Bearer {API_KEY_5SIM}"}
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=headers) as r:
            return await r.json()

async def cancel_number_5sim(id_):
    url = f"https://5sim.net/v1/user/cancel/{id_}"
    headers = {"Authorization": f"Bearer {API_KEY_5SIM}"}
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=headers) as r:
            return await r.json()

# --------------- OTHER FUNCTIONS -----------------

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
    API_KEY_TIGER = os.getenv("API_KEY_TIGER")
    url = f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&actoin=getNumber&service={SERVICE}&country={code}&ref=$ref&maxPrice=&providerIds=&exceptProviderIds="
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

# ------------------ HANDLERS ---------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("24sms7", callback_data="site_24sms7")],
        [InlineKeyboardButton("smsbower", callback_data="site_smsbower")],
        [InlineKeyboardButton("tiger", callback_data="site_tiger")],
        [InlineKeyboardButton("5sim", callback_data="site_5sim")],
    ]
    await update.message.reply_text(
        "لطفا یکی از سایت‌ها را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def site_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    site = query.data.split("_")[1]
    user_sessions[query.from_user.id] = {"site": site}
    countries = []
    if site == "24sms7":
        countries = list(COUNTRIES_24SMS7.keys())
    elif site == "smsbower":
        countries = list(COUNTRIES_SMSBOWER.keys())
    elif site == "tiger":
        countries = list(COUNTRIES_TIGER_SMS.keys())
    elif site == "5sim":
        # برای 5sim چون اطلاعات کشورها/اپراتورها رو نداری، فقط گزینه نمونه میذارم:
        countries = ["ru", "kz", "us", "uk", "de"]  # خودت پرشون کن
    buttons = [
        [InlineKeyboardButton(country, callback_data=f"country_{country}")]
        for country in countries
    ]
    await query.edit_message_text(
        "کشور را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

async def country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    country = query.data.split("_", 1)[1]
    user_sessions[query.from_user.id]["country"] = country
    site = user_sessions[query.from_user.id]["site"]
    # اگر سایت 5sim هست، باید اپراتور و محصول رو انتخاب کنیم یا فرض کنیم ثابتند
    if site == "5sim":
        # فرض می‌کنیم اپراتور و محصول پیش‌فرض:
        user_sessions[query.from_user.id]["operator"] = "any"
        user_sessions[query.from_user.id]["product"] = "any"
        await query.edit_message_text("در حال دریافت شماره از 5sim...")
        await get_and_send_number(update, context)
    else:
        await query.edit_message_text(f"در حال دریافت شماره از {site} برای کشور {country} ...")
        await get_and_send_number(update, context)

async def get_and_send_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    site = user_sessions[user_id]["site"]
    country = user_sessions[user_id].get("country")
    operator = user_sessions[user_id].get("operator", None)
    product = user_sessions[user_id].get("product", None)

    if site == "24sms7":
        code = COUNTRIES_24SMS7.get(country, 0)
        response = await get_number_24sms7(code)
        await context.bot.send_message(chat_id=user_id, text=f"شماره دریافت شد: {response}")
    elif site == "smsbower":
        code = COUNTRIES_SMSBOWER.get(country, 0)
        response = await get_number_smsbower(code)
        await context.bot.send_message(chat_id=user_id, text=f"شماره دریافت شد: {response}")
    elif site == "tiger":
        code = COUNTRIES_TIGER_SMS.get(country, 0)
        response = await get_number_tiger(code)
        await context.bot.send_message(chat_id=user_id, text=f"شماره دریافت شد: {response}")
    elif site == "5sim":
        response = await get_number_5sim(country, operator, product)
        await context.bot.send_message(chat_id=user_id, text=f"پاسخ 5sim: {response}")

async def check_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # این تابع فرضی برای چک کردن کد پیامکی است که احتمالا تو کد اصلی هست
    user_id = update.effective_user.id
    session = user_sessions.get(user_id)
    if not session:
        await update.message.reply_text("ابتدا باید سایت و کشور را انتخاب کنید.")
        return
    site = session["site"]
    id_ = session.get("id")
    if not id_:
        await update.message.reply_text("شماره ای فعال نشده است.")
        return

    if site == "5sim":
        result = await get_code_5sim(id_)
        await update.message.reply_text(f"نتیجه چک کد 5sim:\n{result}")
    else:
        code_result = await get_code(site, id_)
        await update.message.reply_text(f"نتیجه چک کد {site}:\n{code_result}")

async def cancel_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = user_sessions.get(user_id)
    if not session:
        await update.message.reply_text("ابتدا باید سایت و کشور را انتخاب کنید.")
        return
    site = session["site"]
    id_ = session.get("id")
    if not id_:
        await update.message.reply_text("شماره ای فعال نشده است.")
        return

    if site == "5sim":
        result = await cancel_number_5sim(id_)
        await update.message.reply_text(f"درخواست لغو 5sim: {result}")
    else:
        await cancel_number(site, id_)
        await update.message.reply_text(f"درخواست لغو {site} انجام شد.")

# ------------------- BOT SETUP ------------------

def main():
    nest_asyncio.apply()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(site_selected, pattern="^site_"))
    app.add_handler(CallbackQueryHandler(country_selected, pattern="^country_"))
    app.add_handler(CommandHandler("checkcode", check_code))
    app.add_handler(CommandHandler("cancel", cancel_request))

    app.run_polling()

if __name__ == "__main__":
    main()
