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
API_KEY_5SIM = os.getenv("API_KEY_5SIM")  # اضافه کردن کلید API 5sim

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
}

COUNTRIES_5SIM = {
    "hongkong": hongkong,
    "Ukraine": 1,
    "Kazakhstan": 2,
    # بقیه کشورها...
}

MAX_PARALLEL_REQUESTS = {
    "24sms7": 1,
    "smsbower": 5,
    "5sim": 5,
}

user_sessions = {}
search_tasks = {}
cancel_flags = set()
valid_numbers = {}

user_sessions_5sim = {}

# --- توابع 24sms7 و smsbower (بدون تغییر) ---

async def get_number_24sms7(code):
    url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getNumber&service={SERVICE}&country={code}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def get_number_smsbower(code):
    url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getNumber&service={SERVICE}&country={code}&maxPrice=58.67&providerIds=2195,2194,1000&exceptProviderIds=2196&phoneException=7700,7708"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def get_code(site, id_):
    url = {
        "24sms7": f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getStatus&id={id_}",
        "smsbower": f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getStatus&id={id_}",
        "5sim": f"https://5sim.net/v1/user/check/{id_}"
    }[site]
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            if site == "5sim":
                if r.status == 200:
                    return await r.json()
                return None
            else:
                return await r.text()

async def cancel_number(site, id_):
    url = {
        "24sms7": f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=setStatus&status=8&id={id_}",
        "smsbower": f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=setStatus&status=8&id={id_}",
        "5sim": f"https://5sim.net/v1/user/cancel/{id_}"
    }[site]
    async with aiohttp.ClientSession() as s:
        if site == "5sim":
            async with s.post(url) as resp:
                return resp.status == 200
        else:
            await s.get(url)
            return True

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

# --- توابع 5sim (اضافه شده) ---

async def get_number_5sim(country_code):
    url = f"https://5sim.net/v1/user/buy/activation/{country_code}/tg"
    headers = {"Authorization": f"Bearer {API_KEY_5SIM}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            return None

async def auto_check_code_5sim(chat_id, order_id, context):
    while True:
        await asyncio.sleep(0.1)
        code_resp = await get_code("5sim", order_id)
        if code_resp and code_resp.get("status") == "RECEIVED":
            code = code_resp.get("sms")
            await context.bot.send_message(chat_id=chat_id,
                                           text=f"📩 کد دریافت شده برای شماره:\n<code>{code}</code>",
                                           parse_mode=ParseMode.HTML)
            return

async def auto_check_code(user_id, chat_id, msg_id, id_, site, number, context):
    for _ in range(1220):  # حدود 2 دقیقه و 2 ثانیه
        await asyncio.sleep(0.1)
        if user_id in cancel_flags:
            cancel_flags.remove(user_id)
            await cancel_number(site, id_)
            await context.bot.edit_message_text("🚫 جستجو لغو شد.", chat_id=chat_id, message_id=msg_id)
            return
        code_resp = await get_code(site, id_)
        if code_resp and ("STATUS_OK" in code_resp or "STATUS_WAIT" in code_resp):
            if "STATUS_OK" in code_resp:
                code = code_resp.split(":")[-1]
                await context.bot.send_message(chat_id=chat_id,
                                               text=f"📩 کد دریافت شده برای شماره:\n<code>{code}</code>",
                                               parse_mode=ParseMode.HTML)
                return
    await cancel_number(site, id_)
    await context.bot.edit_message_text("⌛ زمان انتظار کد تمام شد.", chat_id=chat_id, message_id=msg_id)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("24sms7", callback_data="site_24sms7")],
        [InlineKeyboardButton("SMSBower", callback_data="site_smsbower")],
        [InlineKeyboardButton("5sim", callback_data="site_5sim")],  # اضافه کردن گزینه 5sim
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
    elif site == "5sim":
        countries = COUNTRIES_5SIM
    else:
        countries = {}

    buttons = [[InlineKeyboardButton(name, callback_data=f"country_{site}_{code}")] for name, code in countries.items()]
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")])
    await query.edit_message_text("🌍 انتخاب کشور:", reply_markup=InlineKeyboardMarkup(buttons))

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await start(update, context)

async def country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data_parts = query.data.split("_")
    # مثال data_parts: ["country", "5sim", "1"] یا ["country", "24sms7", "57"]
    _, site, code = data_parts
    user_id = query.from_user.id

    cancel_flags.discard(user_id)

    if site == "5sim":
        msg = await query.edit_message_text("⏳ در حال جستجو برای شماره سالم روی 5sim...")
        async def search_task():
            while user_id not in cancel_flags:
                result = await get_number_5sim(int(code))
                if not result or "error" in result:
                    await asyncio.sleep(0.5)
                    continue
                number = result.get("phone")
                order_id = result.get("id")
                if number and order_id:
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("📩 دریافت کد", callback_data=f"checkcode_{order_id}")],
                        [InlineKeyboardButton("❌ لغو شماره", callback_data=f"cancel_{order_id}")],
                        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")]
                    ])
                    await context.bot.send_message(chat_id=query.message.chat_id,
                                                   text=f"📱 شماره سالم 5sim: <code>{number}</code>",
                                                   parse_mode=ParseMode.HTML,
                                                   reply_markup=keyboard)
                    asyncio.create_task(auto_check_code_5sim(query.message.chat_id, order_id, context))
                    break
                await asyncio.sleep(0.1)

        user_sessions_5sim[user_id] = asyncio.create_task(search_task())

    else:
        # بقیه کد برای 24sms7 و smsbower (بدون تغییر)
        valid_numbers[user_id] = []
        msg = await query.edit_message_text("⏳ جستجو برای شماره سالم...", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ کنسل جستجو", callback_data="cancel_search")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_sites")]
        ]))

        max_requests = MAX_PARALLEL_REQUESTS.get(site, 1)

        async def run_parallel_search(i):
            await search_number(user_id, query.message.chat_id, msg.message_id, int(code), site, context)

        tasks = [asyncio.create_task(run_parallel_search(i)) for i in range(max_requests)]
        search_tasks[user_id] = tasks[0]

async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    cancel_flags.add(user_id)

async def search_number(user_id, chat_id, msg_id, code, site, context):
    async def delayed_cancel(id_, site_):
        await asyncio.sleep(122)
        active_ids = [i[0] for i in valid_numbers.get(user_id, [])]
        if id_ not in active_ids:
            await cancel_number(site_, id_)

    while len(valid_numbers[user_id]) < 5:
        if user_id in cancel_flags:
            cancel_flags.remove(user_id)
            await context.bot.edit_message_text("🚫 جستجو لغو شد.", chat_id=chat_id, message_id=msg_id)
            return
        resp = await (get_number_24sms7(code) if site == "24sms7" else get_number_smsbower(code))
        if not resp.startswith("ACCESS_NUMBER"):
            await asyncio.sleep(1)
            continue
        _, id_, number = resp.split(":")[:3]
        number = f"+{number}"
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
            await cancel_number(site, id_)

async def checkcode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    if len(data) != 2:
        return
    id_ = data[1]
    user_id = query.from_user.id
    for idnum, site, number, msg_id in valid_numbers.get(user_id, []):
        if idnum == id_:
            await context.bot.send_message(chat_id=query.message.chat_id, text=f"⏳ در حال دریافت کد برای شماره <code>{number}</code>...", parse_mode=ParseMode.HTML)
            return

async def cancel_number_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    if len(data) != 2:
        return
    id_ = data[1]
    user_id = query.from_user.id
    for idx, (idnum, site, number, msg_id) in enumerate(valid_numbers.get(user_id, [])):
        if idnum == id_:
            await cancel_number(site, id_)
            await context.bot.edit_message_text(f"❌ شماره <code>{number}</code> لغو شد.", chat_id=query.message.chat_id, message_id=msg_id, parse_mode=ParseMode.HTML)
            valid_numbers[user_id].pop(idx)
            return

def main():
    nest_asyncio.apply()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(site_selected, pattern=r"^site_"))
    app.add_handler(CallbackQueryHandler(country_selected, pattern=r"^country_"))
    app.add_handler(CallbackQueryHandler(back_to_start, pattern="back_to_start"))
    app.add_handler(CallbackQueryHandler(cancel_search, pattern="cancel_search"))
    app.add_handler(CallbackQueryHandler(checkcode, pattern=r"^checkcode_"))
    app.add_handler(CallbackQueryHandler(cancel_number_handler, pattern=r"^cancel_"))

    app.run_polling()

if __name__ == "__main__":
    main()

