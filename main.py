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
API_KEY_5SIM = os.getenv("API_KEY_5SIM")
CHECKER_API_KEY = os.getenv("CHECKER_API_KEY")

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
}

COUNTRIES_SMSBOWER = {
    "Kazakhstan": 2,
    # سایر کشورها اگر لازم بود اضافه شود
}

COUNTRIES_TIGER_SMS = {
    "Iran": 57,
    "Russia": 0,
    "Ukraine": 1,
    # سایر کشورها اگر لازم بود اضافه شود
}

MAX_PARALLEL_REQUESTS = {
    "24sms7": 1,
    "smsbower": 5,
    "tiger": 1,
    "5sim": 3,
}

# ذخیره وضعیت کاربرها، درخواست‌ها و شماره‌ها
user_sessions = {}
search_tasks = {}
cancel_flags = set()
valid_numbers = {}

# -------- توابع API مربوط به 24sms7 --------

async def get_number_24sms7(code):
    url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getNumber&service={SERVICE}&country={code}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()

async def get_code_24sms7(id_):
    url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getStatus&id={id_}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()

async def cancel_number_24sms7(id_):
    url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=setStatus&status=8&id={id_}"
    async with aiohttp.ClientSession() as session:
        await session.get(url)

# -------- توابع API مربوط به SMSBower --------

async def get_number_smsbower(code):
    url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getNumber&service={SERVICE}&country={code}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()

async def get_code_smsbower(id_):
    url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getStatus&id={id_}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()

async def cancel_number_smsbower(id_):
    url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=setStatus&status=8&id={id_}"
    async with aiohttp.ClientSession() as session:
        await session.get(url)

# -------- توابع API مربوط به Tiger SMS --------

async def get_number_tiger(code):
    url = f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getNumber&service={SERVICE}&country={code}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()

async def get_code_tiger(id_):
    url = f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getStatus&id={id_}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()

async def cancel_number_tiger(id_):
    url = f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=setStatus&status=8&id={id_}"
    async with aiohttp.ClientSession() as session:
        await session.get(url)

# -------- توابع API مربوط به 5sim --------

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
        await session.get(url, headers=headers)

# -------- توابع اصلی عمومی --------

async def get_number(site, code, operator=None, product=None):
    if site == "24sms7":
        return await get_number_24sms7(code)
    elif site == "smsbower":
        return await get_number_smsbower(code)
    elif site == "tiger":
        return await get_number_tiger(code)
    elif site == "5sim":
        if operator and product:
            return await buy_activation_5sim(code, operator, product)
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

async def check_valid(number):
    url = "http://checker.irbots.com:2021/check"
    params = {"key": CHECKER_API_KEY, "numbers": number.strip("+")}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get("status") == "ok":
                    result = data.get("data", {}).get(f"+{number.strip('+')}", False)
                    return result is True
    return False

# -------- توابع تلگرام --------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("24sms7", callback_data="site_24sms7")],
        [InlineKeyboardButton("SMSBower", callback_data="site_smsbower")],
        [InlineKeyboardButton("Tiger SMS", callback_data="site_tiger")],
        [InlineKeyboardButton("5sim", callback_data="site_5sim")],
    ]
    await update.message.reply_text("🌐 سرویس مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))

async def site_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    site = query.data.split("_")[1]
    user_sessions[query.from_user.id] = {"site": site}
    await query.edit_message_text(f"شما سرویس {site} را انتخاب کردید.\nلطفا کشور مورد نظر را انتخاب کنید.")
    # ساخت دکمه کشورها بر اساس سایت انتخاب شده
    if site == "24sms7":
        countries = COUNTRIES_24SMS7
    elif site == "smsbower":
        countries = COUNTRIES_SMSBOWER
    elif site == "tiger":
        countries = COUNTRIES_TIGER_SMS
    else:
        countries = {}
    buttons = []
    for country in countries:
        buttons.append([InlineKeyboardButton(country, callback_data=f"country_{country}")])
    buttons.append([InlineKeyboardButton("بازگشت", callback_data="back_to_sites")])
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(buttons))

async def country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    country = query.data.split("_", 1)[1]
    user_sessions[query.from_user.id]["country"] = country
    await query.edit_message_text(f"شما کشور {country} را انتخاب کردید.\nلطفا منتظر دریافت شماره باشید...")
    # شروع فرآیند گرفتن شماره
    site = user_sessions[query.from_user.id]["site"]
    if site == "24sms7":
        code = COUNTRIES_24SMS7.get(country)
    elif site == "smsbower":
        code = COUNTRIES_SMSBOWER.get(country)
    elif site == "tiger":
        code = COUNTRIES_TIGER_SMS.get(country)
    else:
        code = None
    if code is None:
        await query.edit_message_text("کد کشور برای این سرویس یافت نشد.")
        return

    number_response = await get_number(site, code)
    # فرض می‌کنیم جواب یک رشته ID است یا شماره، بر اساس API واقعی‌ات باید اصلاح کنی
    await query.edit_message_text(f"شماره دریافت شد:\n{number_response}")
    user_sessions[query.from_user.id]["number_id"] = number_response

async def back_to_sites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    buttons = [
        [InlineKeyboardButton("24sms7", callback_data="site_24sms7")],
        [InlineKeyboardButton("SMSBower", callback_data="site_smsbower")],
        [InlineKeyboardButton("Tiger SMS", callback_data="site_tiger")],
        [InlineKeyboardButton("5sim", callback_data="site_5sim")],
    ]
    await query.edit_message_text("🌐 سرویس مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(buttons))

async def cancel_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id in user_sessions:
        session = user_sessions[user_id]
        if "number_id" in session and "site" in session:
            await cancel_number(session["site"], session["number_id"])
            await query.edit_message_text("درخواست شما لغو شد.")
            user_sessions.pop(user_id, None)
        else:
            await query.edit_message_text("هیچ درخواست فعالی یافت نشد.")
    else:
        await query.edit_message_text("هیچ درخواست فعالی یافت نشد.")

async def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(site_selected, pattern="^site_"))
    application.add_handler(CallbackQueryHandler(country_selected, pattern="^country_"))
    application.add_handler(CallbackQueryHandler(back_to_sites, pattern="^back_to_sites$"))
    application.add_handler(CallbackQueryHandler(cancel_request, pattern="^cancel_request$"))

    await application.start()
    await application.updater.start_polling()
    await application.updater.idle()

if __name__ == "__main__":
    asyncio.run(main())
