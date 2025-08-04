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
API_KEY_TIGER_SMS = os.getenv("API_KEY_TIGER_SMS")  # اضافه شده

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

COUNTRIES_TIGER_SMS = {  # اضافه شده
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

MAX_PARALLEL_REQUESTS = {
    "24sms7": 1,
    "smsbower": 5,
    "tigersms": 3,  # اضافه شده
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
    url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getNumber&service={SERVICE}&country={code}&maxPrice=58.67&providerIds=2196,2195,2194,1000&exceptProviderIds=&phoneException=7700,7708"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def get_number_tigersms(code):  # اضافه شده
    url = f"https://tiger-sms.shop/api/getNumber?api_key={API_KEY_TIGER_SMS}&service={SERVICE}&country={code}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def get_code(site, id_):
    if site == "24sms7":
        url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getStatus&id={id_}"
    elif site == "smsbower":
        url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getStatus&id={id_}"
    elif site == "tigersms":
        url = f"https://tiger-sms.shop/api/getStatus?api_key={API_KEY_TIGER_SMS}&id={id_}"
    else:
        return ""
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def cancel_number(site, id_):
    if site == "24sms7":
        url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=setStatus&status=8&id={id_}"
    elif site == "smsbower":
        url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=setStatus&status=8&id={id_}"
    elif site == "tigersms":
        url = f"https://tiger-sms.shop/api/setStatus?api_key={API_KEY_TIGER_SMS}&status=8&id={id_}"
    else:
        return
    async with aiohttp.ClientSession() as s:
        await s.get(url)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("24sms7", callback_data="site_24sms7")],
        [InlineKeyboardButton("SMSBower", callback_data="site_smsbower")],
        [InlineKeyboardButton("TigerSMS", callback_data="site_tigersms")],  # اضافه شده
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
    elif site == "tigersms":
        countries = COUNTRIES_TIGER_SMS
    else:
        countries = {}
    buttons = [[InlineKeyboardButton(name, callback_data=f"country_{site}_{id_}")] for name, id_ in countries.items()]
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")])
    await query.edit_message_text("🌍 انتخاب کشور:", reply_markup=InlineKeyboardMarkup(buttons))

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
        if site == "24sms7":
            resp = await get_number_24sms7(code)
        elif site == "smsbower":
            resp = await get_number_smsbower(code)
        elif site == "tigersms":
            resp = await get_number_tigersms(code)
        else:
            resp = ""
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
        if user_id in cancel_flags:
            cancel_flags.remove(user_id)
            await cancel_number(site, id_)
            await context.bot.edit_message_text("🚫 لغو دریافت کد.", chat_id=chat_id, message_id=msg_id)
            return
        code = await get_code(site, id_)
        if "STATUS_OK" in code or "STATUS_CANCEL" in code:
            await context.bot.edit_message_text(
                f"📨 کد دریافتی برای شماره <code>{number}</code>:\n\n<code>{code}</code>",
                chat_id=chat_id, message_id=msg_id, parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ لغو شماره", callback_data=f"cancel_{id_}")],
                    [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_sites")]
                ])
            )
            return
        await asyncio.sleep(3)

async def check_valid(number):
    # تابع بررسی صحت شماره (نمونه)
    return True  # یا منطق خودت رو بزار

async def cancel_number_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    id_ = data.split("_")[1]
    site = None
    for val in valid_numbers.get(user_id, []):
        if val[0] == id_:
            site = val[1]
            break
    if site:
        await cancel_number(site, id_)
        await query.edit_message_text("شماره لغو شد.", reply_markup=None)

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    buttons = [
        [InlineKeyboardButton("24sms7", callback_data="site_24sms7")],
        [InlineKeyboardButton("SMSBower", callback_data="site_smsbower")],
        [InlineKeyboardButton("TigerSMS", callback_data="site_tigersms")],
    ]
    await query.edit_message_text("🌐 انتخاب سرویس:", reply_markup=InlineKeyboardMarkup(buttons))

async def back_to_sites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    site = None
    if query.data.startswith("back_to_sites"):
        # اگر نیاز بود میشه کشور رو دوباره نشان داد یا سرویس رو
        await back_to_start(update, context)

def main():
    nest_asyncio.apply()
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(site_selected, pattern="^site_"))
    application.add_handler(CallbackQueryHandler(country_selected, pattern="^country_"))
    application.add_handler(CallbackQueryHandler(cancel_search, pattern="^cancel_search$"))
    application.add_handler(CallbackQueryHandler(cancel_number_callback, pattern="^cancel_"))
    application.add_handler(CallbackQueryHandler(back_to_start, pattern="^back_to_start$"))
    application.add_handler(CallbackQueryHandler(back_to_sites, pattern="^back_to_sites$"))

    application.run_polling()

if __name__ == "__main__":
    main()
