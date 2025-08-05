import os
import asyncio
import logging
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY_24SMS7 = os.getenv("API_KEY_24SMS7")
API_KEY_SMSBOWER = os.getenv("API_KEY_SMSBOWER")
API_KEY_TIGER = os.getenv("API_KEY_TIGER")
TOKEN_5SIM = os.getenv("TOKEN_5SIM")
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
}

COUNTRIES_TIGER_SMS = {
    "Iran": 57,
    "Russia": 0,
    "Ukraine": 1,
}

COUNTRIES_5SIM = {
    "Hong Kong": "hongkong",
}

valid_numbers = {}
cancel_flags = set()

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

# --- 24sms7 ---
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

# --- SMSBower ---
async def get_number_smsbower(code):
    url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getNumber&service={SERVICE}&country={code}"
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

# --- Tiger SMS ---
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

# --- 5sim ---
async def get_products_5sim(country, operator="any"):
    url = f"https://5sim.net/v1/guest/products/{country}/{operator}"
    headers = {"Accept": "application/json"}
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=headers) as r:
            return await r.json()

async def get_number_5sim(country, operator="any", product="any"):
    url = f"https://5sim.net/v1/user/buy/activation/{country}/{operator}/{product}"
    headers = {
        "Authorization": f"Bearer {TOKEN_5SIM}",
        "Accept": "application/json"
    }
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=headers) as r:
            return await r.json()

async def get_code_5sim(id_):
    url = f"https://5sim.net/v1/user/check/{id_}"
    headers = {
        "Authorization": f"Bearer {TOKEN_5SIM}",
        "Accept": "application/json"
    }
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=headers) as r:
            return await r.json()

async def cancel_number_5sim(id_):
    url = f"https://5sim.net/v1/user/cancel/{id_}"
    headers = {
        "Authorization": f"Bearer {TOKEN_5SIM}",
        "Accept": "application/json"
    }
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=headers) as r:
            return await r.json()

# --- Telegram Bot Handlers ---

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
    buttons = [[InlineKeyboardButton(name, callback_data=f"country_{site}_{code}")] for name, code in countries.items()]
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")])
    await query.edit_message_text("🌍 انتخاب کشور:", reply_markup=InlineKeyboardMarkup(buttons))

async def country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, site, code = query.data.split("_")
    msg = await query.edit_message_text(f"⏳ در حال جستجوی شماره از {site} برای کشور {code} ...")
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    msg_id = query.message.message_id
    asyncio.create_task(search_number(user_id, chat_id, msg_id, code, site, context))

async def search_number(user_id, chat_id, msg_id, code, site, context):
    while True:
        if user_id in cancel_flags:
            cancel_flags.remove(user_id)
            await context.bot.edit_message_text("🚫 جستجو لغو شد.", chat_id=chat_id, message_id=msg_id)
            return

        current_valid = valid_numbers.get(user_id, [])
        max_numbers = 1 if site in ["24sms7", "tiger", "5sim"] else 5
        if len(current_valid) >= max_numbers:
            break

        number = None
        id_ = None

        if site == "24sms7":
            resp = await get_number_24sms7(code)
            if resp.startswith("ACCESS_NUMBER"):
                _, id_, num = resp.split(":")[:3]
                number = f"+{num}"
        elif site == "smsbower":
            resp = await get_number_smsbower(code)
            if resp.startswith("ACCESS_NUMBER"):
                _, id_, num = resp.split(":")[:3]
                number = f"+{num}"
        elif site == "tiger":
            resp = await get_number_tiger(code)
            if resp.startswith("ACCESS_NUMBER"):
                _, id_, num = resp.split(":")[:3]
                number = f"+{num}"
        elif site == "5sim":
            resp = await get_number_5sim(code)
            if "error" not in resp:
                id_ = str(resp.get("id"))
                number = resp.get("phone")
        else:
            await asyncio.sleep(1)
            continue

        if not number:
            await asyncio.sleep(2)
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
                    [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")]
                ])
            )
            valid_numbers.setdefault(user_id, []).append((id_, site, number, msg.message_id))
            asyncio.create_task(auto_check_code(user_id, chat_id, msg.message_id, id_, site, number, context))
            break
        else:
            await context.bot.edit_message_text(
                f"❌ شماره ناسالم: <code>{number}</code>\n🔄 در حال جستجو برای شماره سالم...",
                chat_id=chat_id,
                message_id=msg_id,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ کنسل جستجو", callback_data="cancel_search")],
                    [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")]
                ])
            )
            await asyncio.sleep(3)

async def auto_check_code(user_id, chat_id, msg_id, id_, site, number, context):
    while True:
        await asyncio.sleep(5)
        if user_id in cancel_flags:
            cancel_flags.remove(user_id)
            return
        code = None
        if site == "5sim":
            resp = await get_code_5sim(id_)
            code = resp.get("sms")
        else:
            resp = await get_code(site, id_)
            if resp.startswith("STATUS_OK:"):
                code = resp[len("STATUS_OK:"):].strip()
        if code:
            await context.bot.edit_message_text(
                f"📩 کد برای شماره <code>{number}</code> دریافت شد:\n<code>{code}</code>",
                chat_id=chat_id,
                message_id=msg_id,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ حذف", callback_data=f"cancel_{id_}")],
                    [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")]
                ])
            )
            valid_numbers[user_id] = [v for v in valid_numbers.get(user_id, []) if v[0] != id_]
            break

async def get_code(site, id_):
    if site == "24sms7":
        return await get_code_24sms7(id_)
    elif site == "smsbower":
        return await get_code_smsbower(id_)
    elif site == "tiger":
        return await get_code_tiger(id_)
    return ""

async def cancel_number(site, id_):
    if site == "24sms7":
        await cancel_number_24sms7(id_)
    elif site == "smsbower":
        await cancel_number_smsbower(id_)
    elif site == "tiger":
        await cancel_number_tiger(id_)
    elif site == "5sim":
        await cancel_number_5sim(id_)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == "back_to_start":
        await start(update, context)
        return

    if data.startswith("site_"):
        await site_selected(update, context)
    elif data.startswith("country_"):
        await country_selected(update, context)
    elif data.startswith("checkcode_"):
        user_id = query.from_user.id
        id_ = data.split("_")[1]
        await query.answer()
        await context.bot.send_message(query.message.chat_id, f"در حال دریافت کد برای شماره {id_} ...")
    elif data.startswith("cancel_"):
        user_id = query.from_user.id
        id_ = data.split("_")[1]
        recs = valid_numbers.get(user_id, [])
        site = None
        for r in recs:
            if r[0] == id_:
                site = r[1]
                break
        if site:
            await cancel_number(site, id_)
            valid_numbers[user_id] = [r for r in recs if r[0] != id_]
            await query.edit_message_text("شماره لغو شد.")
    elif data == "cancel_search":
        user_id = query.from_user.id
        cancel_flags.add(user_id)
        await query.answer("جستجو لغو شد.")

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.run_polling()

if __name__ == "__main__":
    main()
