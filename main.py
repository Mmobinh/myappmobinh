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
API_KEY_5SIM = os.getenv("API_KEY_5SIM")  # توکن 5sim اینجا باید تعریف بشه
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

# اضافه کردن کشور هنگ کنگ برای 5sim
COUNTRIES_5SIM = {
    "Hong Kong": "hongkong",
}

MAX_PARALLEL_REQUESTS = {
    "24sms7": 1,
    "smsbower": 5,
    "tiger": 1,
    "5sim": 1,
}

user_sessions = {}
search_tasks = {}
cancel_flags = set()
valid_numbers = {}

# --- توابع اصلی شماره گرفتن برای سرویس‌ها ---
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
    url = f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getNumber&service={SERVICE}&country={code}&ref=$ref&maxPrice=&providerIds=&exceptProviderIds="
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

# تابع جدید برای گرفتن شماره از 5sim
async def get_number_5sim(country):
    url = f"https://5sim.net/v1/user/buy/activation/{country}/any/any"
    headers = {
        "Authorization": f"Bearer {API_KEY_5SIM}",
        "Accept": "application/json"
    }
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=headers) as r:
            if r.status == 200:
                data = await r.json()
                # داده‌های لازم از پاسخ رو اینجا استخراج کن
                # id و number و ...
                return data
            else:
                return None

async def get_code(site, id_):
    url = {
        "24sms7": f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getStatus&id={id_}",
        "smsbower": f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getStatus&id={id_}",
        "tiger": f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getStatus&id={id_}",
        "5sim": f"https://5sim.net/v1/user/check/{id_}"
    }[site]
    headers = {}
    if site == "5sim":
        headers["Authorization"] = f"Bearer {API_KEY_5SIM}"
        headers["Accept"] = "application/json"
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=headers) as r:
            if site == "5sim":
                if r.status == 200:
                    return await r.json()
                else:
                    return None
            else:
                return await r.text()

async def cancel_number(site, id_):
    url = {
        "24sms7": f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=setStatus&status=8&id={id_}",
        "smsbower": f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=setStatus&status=8&id={id_}",
        "tiger": f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=setStatus&status=8&id={id_}",
        "5sim": f"https://5sim.net/v1/user/cancel/{id_}"
    }[site]
    headers = {}
    if site == "5sim":
        headers["Authorization"] = f"Bearer {API_KEY_5SIM}"
        headers["Accept"] = "application/json"
    async with aiohttp.ClientSession() as s:
        await s.get(url, headers=headers)

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

# --- هندلرها ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("24sms7", callback_data="site_24sms7")],
        [InlineKeyboardButton("SMSBower", callback_data="site_smsbower")],
        [InlineKeyboardButton("Tiger SMS", callback_data="site_tiger")],
        [InlineKeyboardButton("5sim", callback_data="site_5sim")]
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
            resp = await get_number_5sim(code)
        else:
            resp = None

        if site != "5sim":
            if not resp or not resp.startswith("ACCESS_NUMBER"):
                await asyncio.sleep(1)
                continue
            _, id_, number = resp.split(":")[:3]
            number = f"+{number}"
        else:
            if not resp:
                await asyncio.sleep(1)
                continue
            id_ = resp.get("id")
            number = resp.get("number")
            if number and not number.startswith("+"):
                number = "+" + number

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

async def auto_check_code(user_id, chat_id, msg_id, id_, site, number, context):
    while True:
        async def auto_check_code(user_id, chat_id, msg_id, id_, site, number, context):
    for _ in range(120):  # بررسی کد به مدت تقریبا 2 دقیقه (120 بار هر 1 ثانیه)
        if user_id in cancel_flags:
            return
        code_data = await get_code(site, id_)
        if not code_data:
            await asyncio.sleep(1)
            continue

        # بررسی وضعیت کد در سرویس‌های مختلف
        if site == "5sim":
            messages = code_data.get("sms", [])
            if messages:
                code_text = messages[0].get("code", "")
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=f"✅ کد دریافتی برای شماره <code>{number}</code>:\n\n<code>{code_text}</code>",
                    parse_mode=ParseMode.HTML
                )
                return
        else:
            if "STATUS_OK" in code_data or "STATUS_CANCEL" in code_data:
                code = code_data.split(":")[-1].strip()
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=f"✅ کد دریافتی برای شماره <code>{number}</code>:\n\n<code>{code}</code>",
                    parse_mode=ParseMode.HTML
                )
                return
        await asyncio.sleep(1)

    # اگر کد نیامد بعد از زمان مشخص
    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=msg_id,
        text=f"❌ کدی دریافت نشد برای شماره <code>{number}</code>",
        parse_mode=ParseMode.HTML
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    await query.answer()

    if data == "cancel_search":
        cancel_flags.add(user_id)
        tasks = search_tasks.get(user_id, [])
        for t in tasks:
            t.cancel()
        search_tasks.pop(user_id, None)
        valid_numbers[user_id] = []
        await query.edit_message_text("🚫 جستجو لغو شد.")
        return

    if data == "back_to_sites":
        await back_to_sites(update, context)
        return

    if data == "back_to_start":
        await back_to_start(update, context)
        return

    if data.startswith("site_"):
        await site_selected(update, context)
        return

    if data.startswith("country_"):
        await country_selected(update, context)
        return

    if data.startswith("checkcode_"):
        id_ = data.split("_")[1]
        # پیدا کردن شماره و سرویس مربوط به این id از valid_numbers
        items = valid_numbers.get(user_id, [])
        for entry in items:
            if entry[0] == id_:
                site = entry[1]
                number = entry[2]
                msg_id = entry[3]
                await auto_check_code(user_id, query.message.chat_id, msg_id, id_, site, number, context)
                break
        return

    if data.startswith("cancel_"):
        id_ = data.split("_")[1]
        # پیدا کردن سرویس مربوط به این id
        items = valid_numbers.get(user_id, [])
        for entry in items:
            if entry[0] == id_:
                site = entry[1]
                await cancel_number(site, id_)
                items.remove(entry)
                await query.edit_message_text("❌ شماره لغو شد.")
                break
        return

async def main():
    nest_asyncio.apply()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    runner = web.AppRunner(app)
    await runner.setup()

    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
