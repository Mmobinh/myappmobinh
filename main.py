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
API_KEY_5SIM = os.getenv("API_KEY_5SIM")  # اضافه شد
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

# اضافه کردن کشورهای 5sim (از کد اول)
COUNTRIES_5SIM = {
    "US": "usa",
    "UK": "gb",
    "Germany": "de",
    "France": "fr",
    "Canada": "ca",
    "Italy": "it",
    "Russia": "ru",
    "Spain": "es",
    "Poland": "pl",
    "Mexico": "mx",
}

MAX_PARALLEL_REQUESTS = {
    "24sms7": 1,
    "smsbower": 5,
    "tiger": 1,
    "5sim": 1,  # اضافه شد
}

user_sessions = {}
search_tasks = {}
cancel_flags = set()
valid_numbers = {}

# توابع سایت 24sms7
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

# توابع سایت smsbower
async def get_number_smsbower(code):
    url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getNumber&service={SERVICE}&country={code}&maxPrice=58.67&providerIds=2195,2194,2196,1000&exceptProviderIds=&phoneException=7700,7708"
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

# توابع سایت tiger
async def get_number_tiger(code):
    url = f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getNumber&service={SERVICE}&country={code}&ref=$ref&maxPrice=&providerIds=&exceptProviderIds="
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

# توابع سایت 5sim (کاملاً کپی شده از کد اول، بدون تغییر)
async def get_number_5sim(country):
    url = f"https://5sim.net/v1/user/buy/activation/{country}/any/tg"
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
        async with s.post(url, headers=headers) as r:
            return await r.json()

# تابع عمومی گرفتن شماره با توجه به سایت
async def get_number(site, code):
    if site == "24sms7":
        return await get_number_24sms7(code)
    elif site == "smsbower":
        return await get_number_smsbower(code)
    elif site == "tiger":
        return await get_number_tiger(code)
    elif site == "5sim":
        return await get_number_5sim(code)
    else:
        return None

# تابع عمومی گرفتن کد با توجه به سایت
async def get_code(site, id_):
    if site == "24sms7":
        return await get_code_24sms7(id_)
    elif site == "smsbower":
        return await get_code_smsbower(id_)
    elif site == "tiger":
        return await get_code_tiger(id_)
    elif site == "5sim":
        return await get_code_5sim(id_)
    else:
        return None

# تابع عمومی لغو شماره با توجه به سایت
async def cancel_number(site, id_):
    if site == "24sms7":
        await cancel_number_24sms7(id_)
    elif site == "smsbower":
        await cancel_number_smsbower(id_)
    elif site == "tiger":
        await cancel_number_tiger(id_)
    elif site == "5sim":
        await cancel_number_5sim(id_)

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
        [InlineKeyboardButton("5sim", callback_data="site_5sim")],  # اضافه شد
    ]
    await update.message.reply_text("🌐 انتخاب سرویس:", reply_markup=InlineKeyboardMarkup(buttons))

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
        countries = COUNTRIES_5SIM
    else:
        countries = {}

    buttons = [[InlineKeyboardButton(name, callback_data=f"country_{site}_{id_}")] for name, id_ in countries.items()]
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")])
    await query.edit_message_text("🌍 انتخاب کشور:", reply_markup=InlineKeyboardMarkup(buttons))

async def back_to_sites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await site_selected(update, context)

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await start(update, context)

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
        await search_number(user_id, query.message.chat_id, msg.message_id, code, site, context)

    tasks = [asyncio.create_task(run_parallel_search(i)) for i in range(max_requests)]
    search_tasks[user_id] = tasks  # ذخیره همه تسک‌ها

async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    cancel_flags.add(user_id)
    valid_numbers[user_id] = []

    # لغو همه تسک‌های مربوط به این کاربر
    tasks = search_tasks.get(user_id, [])
    for task in tasks:
        task.cancel()
    search_tasks.pop(user_id, None)

    await query.answer("جستجو لغو شد")
    await query.edit_message_text("🚫 جستجو لغو شد.")

async def search_number(user_id, chat_id, msg_id, code, site, context):
    async def delayed_cancel(id_, site_):
        await asyncio.sleep(122)
        active_ids = [i[0] for i in valid_numbers.get(user_id, [])]
        if id_ not in active_ids:
            await cancel_number(site_, id_)

    while True:
        if user_id in cancel_flags:
            cancel_flags.discard(user_id)
            await context.bot.edit_message_text("🚫 جستجو لغو شد.", chat_id=chat_id, message_id=msg_id)
            return
        if site == "24sms7" or site == "tiger" or site == "5sim":
            if len(valid_numbers[user_id]) >= 1:
                break
        elif site == "smsbower":
            if len(valid_numbers[user_id]) >= 5:
                break

        if site == "24sms7":
            resp = await get_number_24sms7(code)
            if not resp.startswith("ACCESS_NUMBER"):
                await asyncio.sleep(1)
                continue
            _, id_, number = resp.split(":")[:3]
            number = f"+{number}"

        elif site == "smsbower":
            resp = await get_number_smsbower(code)
            if not resp.startswith("ACCESS_NUMBER"):
                await asyncio.sleep(1)
                continue
            _, id_, number = resp.split(":")[:3]
            number = f"+{number}"

        elif site == "tiger":
            resp = await get_number_tiger(code)
            if not resp.startswith("ACCESS_NUMBER"):
                await asyncio.sleep(1)
                continue
            _, id_, number = resp.split(":")[:3]
            number = f"+{number}"

        elif site == "5sim":
            data = await get_number_5sim(code)
            if not data or "error" in data:
                await asyncio.sleep(1)
                continue
            id_ = data.get("id")
            number = data.get("number")
            if number and not number.startswith("+"):
                number = "+" + number

        else:
            await asyncio.sleep(1)
            continue

        is_valid = await check_valid(number)
        if is_valid:
            valid_numbers[user_id].append((id_, number))
            await context.bot.send_message(chat_id=chat_id, text=f"✅ شماره سالم: {number}")
            asyncio.create_task(delayed_cancel(id_, site))
        else:
            await cancel_number(site, id_)
            await asyncio.sleep(1)

# تنظیم اپلیکیشن تلگرام و هندلرها

async def main():
    nest_asyncio.apply()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(site_selected, pattern="^site_"))
    app.add_handler(CallbackQueryHandler(country_selected, pattern="^country_"))
    app.add_handler(CallbackQueryHandler(cancel_search, pattern="^cancel_search$"))
    app.add_handler(CallbackQueryHandler(back_to_sites, pattern="^back_to_sites$"))
    app.add_handler(CallbackQueryHandler(back_to_start, pattern="^back_to_start$"))

    # به جای start و updater.start_polling و idle از run_polling استفاده کن
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())


