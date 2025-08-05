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
API_KEY_5SIM = os.getenv("API_KEY_5SIM")  # کلید API 5sim که اضافه شد
SERVICE = "tg"
product = "tg"
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

# اضافه کردن 5sim کشورها (مثلا یه نمونه که خودت باید کامل کنی)
COUNTRIES_5SIM = {
    "Iran": "ir",
    "Hongkong": "hongkong",
    "Ukraine": "ua",
    "USA": "us",
    # سایر کشورها رو به دلخواه اضافه کن
}

MAX_PARALLEL_REQUESTS = {
    "24sms7": 1,
    "smsbower": 5,
    "tiger": 1,
    "5sim": 1,  # حداکثر درخواست هم برای 5sim تعریف شد
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
    url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getNumber&service={SERVICE}&country={code}&maxPrice=58.67&providerIds=2195,2194,2196,1000&exceptProviderIds=&phoneException=7708"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def get_number_tiger(code):
    API_KEY_TIGER = os.getenv("API_KEY_TIGER")
    url = f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getNumber&service={SERVICE}&country={code}&ref=$ref&maxPrice=&providerIds=&exceptProviderIds="
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

# این تابع جدید برای 5sim اضافه شد
async def get_number_5sim(country, operator="any", product="tg"):
    url = f"https://5sim.net/v1/user/buy/activation/{hongkong}/{any}/{tg}"
    headers = {"Authorization": f"Bearer {API_KEY_5SIM}"}
    async with aiohttp.ClientSession(headers=headers) as s:
        async with s.get(url) as r:
            return await r.text()

async def get_code(site, id_):
    url = {
        "24sms7": f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getStatus&id={id_}",
        "smsbower": f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getStatus&id={id_}",
        "tiger": f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getStatus&id={id_}",
        "5sim": f"https://5sim.net/v1/user/check/{id_}",
    }[site]
    async with aiohttp.ClientSession(headers={"Authorization": f"Bearer {API_KEY_5SIM}"}) if site=="5sim" else aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def cancel_number(site, id_):
    url = {
        "24sms7": f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=setStatus&status=8&id={id_}",
        "smsbower": f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=setStatus&status=8&id={id_}",
        "tiger": f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=setStatus&status=8&id={id_}",
        "5sim": f"https://5sim.net/v1/user/cancel/{id_}",
    }[site]
    headers = {"Authorization": f"Bearer {API_KEY_5SIM}"} if site == "5sim" else {}
    async with aiohttp.ClientSession(headers=headers) as s:
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
        [InlineKeyboardButton("5sim", callback_data="site_5sim")],  # دکمه 5sim اضافه شد
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
        if site == "24sms7" or site == "tiger":
            if len(valid_numbers[user_id]) >= 1:
                break
        elif site == "smsbower":
            if len(valid_numbers[user_id]) >= 5:
                break
        elif site == "5sim":
            if len(valid_numbers[user_id]) >= 1:
                break
        if site == "24sms7":
            resp = await get_number_24sms7(code)
        elif site == "smsbower":
            resp = await get_number_smsbower(code)
        elif site == "tiger":
            resp = await get_number_tiger(code)
        elif site == "5sim":
            # توجه: اینجا به 5sim توکن نیاز است، country کد رو فرستادیم
            resp = await get_number_5sim(code)
        else:
            resp = ""
        if site != "5sim":
            if not resp.startswith("ACCESS_NUMBER"):
                await asyncio.sleep(1)
                continue
            _, id_, number = resp.split(":")[:3]
            number = f"+{number}"
        else:
            # پاسخ 5sim احتمالاً JSON است، پس پارسش می‌کنیم:
            import json
            try:
                data = json.loads(resp)
                id_ = str(data.get("id"))
                number = data.get("phone")
            except Exception:
                await asyncio.sleep(1)
                continue
        valid = await check_valid(number)
        if valid:
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"📱 شماره سالم: <code>{number}</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📩 دریافت کد", callback_data=f"checkcode_{id_}")],
                    [InlineKeyboardButton("❌ لغو شماره", callback_data=f"cancel_{id_}")],
                    [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_sites")]
                ])
            )
            valid_numbers[user_id].append((id_, site, number, msg.message_id))
            asyncio.create_task(auto_check_code(user_id, chat_id, msg.message_id, id_, site, number, context))
        else:
            await context.bot.edit_message_text(
                f"❌ شماره ناسالم: <code>{number}</code>\n🔄 در حال جستجو برای شماره سالم...",
                chat_id=chat_id, message_id=msg_id, parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ کنسل جستجو", callback_data="cancel_search")],
                    [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_sites")]
                ])
            )
            asyncio.create_task(delayed_cancel(id_, site))
        await asyncio.sleep(1)

async def dynamic_check_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data.startswith("checkcode_"):
        id_ = data.split("_", 1)[1]
        # پیداکردن سایت مربوط به id
        site = None
        for uid, sess_list in valid_numbers.items():
            for item in sess_list:
                if item[0] == id_:
                    site = item[1]
                    break
            if site:
                break
        if not site:
            await query.edit_message_text("❌ شماره پیدا نشد یا منقضی شده.")
            return

        resp = await get_code(site, id_)
        if site == "5sim":
            import json
            try:
                data = json.loads(resp)
                if data.get("sms"):
                    code = data["sms"][0].get("code") or data["sms"][0].get("text")
                    if code:
                        await query.edit_message_text(
                            f"📩 کد برای شماره دریافت شد:\n<code>{code}</code>",
                            parse_mode=ParseMode.HTML
                        )
                        return
            except Exception:
                await query.edit_message_text("❌ خطا در دریافت کد.")
        else:
            if resp.startswith("STATUS_OK:"):
                code = resp[len("STATUS_OK:"):].strip()
                await query.edit_message_text(
                    f"📩 کد برای شماره دریافت شد:\n<code>{code}</code>",
                    parse_mode=ParseMode.HTML
                )
            else:
                await query.edit_message_text("❌ کد هنوز دریافت نشده یا منقضی شده.")

    elif data.startswith("cancel_"):
        id_ = data.split("_", 1)[1]
        site = None
        for uid, sess_list in valid_numbers.items():
            for item in sess_list:
                if item[0] == id_:
                    site = item[1]
                    break
            if site:
                break
        if not site:
            await query.edit_message_text("❌ شماره پیدا نشد یا منقضی شده.")
            return

        await cancel_number(site, id_)
        await query.edit_message_text("🚫 شماره لغو شد.")

    elif data == "cancel_search":
        await cancel_search(update, context)

    elif data == "back_to_sites":
        await back_to_sites(update, context)

    elif data == "back_to_start":
        await back_to_start(update, context)

async def main():
    nest_asyncio.apply()
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(site_selected, pattern=r"^site_"))
    application.add_handler(CallbackQueryHandler(country_selected, pattern=r"^country_"))
    application.add_handler(CallbackQueryHandler(dynamic_check_code, pattern=r"^(checkcode_|cancel_|cancel_search|back_to_sites|back_to_start)"))

    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())


