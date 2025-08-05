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
API_KEY_5SIM = os.getenv("API_KEY_5SIM")  # جدا برای 5sim

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
}

COUNTRIES_TIGER_SMS = {
    "Iran": 57,
    "Russia": 0,
    "Ukraine": 1,
}

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

# --- API Call Functions ---

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
    url = f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getNumber&service={SERVICE}&country={code}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

# 5sim API
async def get_number_5sim(country, operator="any", product="any"):
    url = f"https://5sim.net/v1/user/buy/activation/{country}/{operator}/{product}"
    headers = {
        "Authorization": f"Bearer {API_KEY_5SIM}",
        "Accept": "application/json"
    }
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=headers) as r:
            return await r.json()

async def cancel_number_5sim(id_):
    url = f"https://5sim.net/v1/user/cancel/{id_}"
    headers = {
        "Authorization": f"Bearer {API_KEY_5SIM}",
        "Accept": "application/json"
    }
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=headers) as r:
            return await r.json()

async def get_code_5sim(id_):
    url = f"https://5sim.net/v1/user/check/{id_}"
    headers = {
        "Authorization": f"Bearer {API_KEY_5SIM}",
        "Accept": "application/json"
    }
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=headers) as r:
            return await r.json()

# --- Common API Functions ---

async def get_code(site, id_):
    url = {
        "24sms7": f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getStatus&id={id_}",
        "smsbower": f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getStatus&id={id_}",
        "tiger": f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getStatus&id={id_}",
        "5sim": None,  # جدا هندل میشه
    }[site]
    if site == "5sim":
        return await get_code_5sim(id_)
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def cancel_number(site, id_):
    if site == "5sim":
        return await cancel_number_5sim(id_)
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

# --- Telegram Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("24sms7", callback_data="site_24sms7")],
        [InlineKeyboardButton("SMSBower", callback_data="site_smsbower")],
        [InlineKeyboardButton("Tiger SMS", callback_data="site_tiger")],
        [InlineKeyboardButton("5SIM (Hong Kong)", callback_data="site_5sim")],
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

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, context)

async def country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    site = data[1]
    country_code = data[2]

    user_id = query.from_user.id
    chat_id = query.message.chat.id
    msg_id = query.message.message_id

    if user_id not in valid_numbers:
        valid_numbers[user_id] = []

    if user_id in cancel_flags:
        cancel_flags.discard(user_id)

    if user_id in search_tasks:
        search_tasks[user_id].cancel()

    search_tasks[user_id] = asyncio.create_task(search_number(user_id, chat_id, msg_id, country_code, site, context))

async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    cancel_flags.add(user_id)

async def dynamic_cancel_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    id_ = query.data.split("_")[1]

    new_list = []
    for rec in valid_numbers.get(user_id, []):
        if rec[0] == id_:
            await cancel_number(rec[1], id_)
        else:
            new_list.append(rec)
    valid_numbers[user_id] = new_list
    await query.edit_message_text("❌ شماره لغو شد.", chat_id=query.message.chat.id, message_id=query.message.message_id)

async def dynamic_check_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    id_ = query.data.split("_")[1]

    new_list = []
    for rec in valid_numbers.get(user_id, []):
        if rec[0] == id_:
            site, number, msg_id = rec[1], rec[2], rec[3]
            resp = await get_code(site, id_)
            if site == "5sim":
                # 5sim returns JSON
                if resp.get("sms"):
                    code = resp["sms"][0]["code"]
                    await context.bot.edit_message_text(
                        f"📩 کد برای شماره <code>{number}</code> دریافت شد:\n<code>{code}</code>",
                        chat_id=query.message.chat.id,
                        message_id=msg_id,
                        parse_mode=ParseMode.HTML
                    )
                else:
                    new_list.append(rec)
            else:
                if resp.startswith("STATUS_OK:"):
                    code = resp[len("STATUS_OK:"):].strip()
                    await context.bot.edit_message_text(
                        f"📩 کد برای شماره <code>{number}</code> دریافت شد:\n<code>{code}</code>",
                        chat_id=query.message.chat.id,
                        message_id=msg_id,
                        parse_mode=ParseMode.HTML
                    )
                else:
                    new_list.append(rec)
        else:
            new_list.append(rec)
    valid_numbers[user_id] = new_list

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

        # محدودیت تعداد شماره‌های فعال بر اساس سایت
        if site == "24sms7" or site == "tiger" or site == "5sim":
            if len(valid_numbers[user_id]) >= 1:
                break
        elif site == "smsbower":
            if len(valid_numbers[user_id]) >= 5:
                break

        # گرفتن شماره
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
            resp = await get_number_5sim(code)
            if "error" in resp:
                await asyncio.sleep(1)
                continue
            id_ = str(resp.get("id"))
            number = resp.get("phone")
        else:
            await asyncio.sleep(1)
            continue

        # چک سلامت شماره
        valid = await check_valid(number)
        if valid:
            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"📱 شماره سالم: <code>{number}</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📩 دریافت کد", callback_data=f"checkcode_{id_}")],
                    [InlineKeyboardButton("❌ لغو شماره", callback_data=f"cancel_{id_}")],
                    [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")]
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
                    [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")]
                ])
            )
            asyncio.create_task(delayed_cancel(id_, site))
        await asyncio.sleep(1)

async def auto_check_code(user_id, chat_id, msg_id, id_, site, number, context):
    # این تابع به صورت دوره‌ای وضعیت کد را چک می‌کند
    for _ in range(120):  # 120 بار چک کن (مثلا هر 5 ثانیه یکبار تا 10 دقیقه)
        await asyncio.sleep(5)
        if user_id in cancel_flags:
            break
        resp = await get_code(site, id_)
        if site == "5sim":
            if resp.get("sms"):
                code = resp["sms"][0]["code"]
                await context.bot.edit_message_text(
                    f"📩 کد برای شماره <code>{number}</code> دریافت شد:\n<code>{code}</code>",
                    chat_id=chat_id,
                    message_id=msg_id,
                    parse_mode=ParseMode.HTML
                )
                return
        else:
            if resp.startswith("STATUS_OK:"):
                code = resp[len("STATUS_OK:"):].strip()
                await context.bot.edit_message_text(
                    f"📩 کد برای شماره <code>{number}</code> دریافت شد:\n<code>{code}</code>",
                    chat_id=chat_id,
                    message_id=msg_id,
                    parse_mode=ParseMode.HTML
                )
                return

async def web_handler(request):
    return web.Response(text="✅ Bot is Alive!")

async def start_webserver():
    app = web.Application()
    app.add_routes([web.get('/', web_handler)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

async def main():
    await start_webserver()
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(site_selected, pattern="^site_"))
    application.add_handler(CallbackQueryHandler(back_to_start, pattern="^back_to_start$"))
    application.add_handler(CallbackQueryHandler(country_selected, pattern="^country_"))
    application.add_handler(CallbackQueryHandler(cancel_search, pattern="^cancel_search$"))
    application.add_handler(CallbackQueryHandler(dynamic_check_code, pattern="^checkcode_"))
    application.add_handler(CallbackQueryHandler(dynamic_cancel_number, pattern="^cancel_"))
    await application.run_polling()

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())
