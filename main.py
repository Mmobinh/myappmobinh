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
CHECKER_API_KEY = os.getenv("CHECKER_API_KEY")
SERVICE = "tg"

COUNTRIES = {
    "24sms7": {
        "Iran": 57, "Russia": 0, "Ukraine": 1, "Mexico": 54, "Italy": 86, "Spain": 56,
        # بقیه کشورها...
    },
    "smsbower": {
        "Kazakhstan": 2, "Iran": 57, "Russia": 0, "Ukraine": 1, # بقیه کشورها...
    },
    "tiger": {
        "Iran": 57, "Russia": 0, "Ukraine": 1, "Mexico": 54, # بقیه کشورها...
    }
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

async def fetch_url(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                return await response.text()
    except Exception as e:
        logging.error(f"Error fetching {url}: {e}")
        return "ERROR"

async def get_number(site, code):
    urls = {
        "24sms7": f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getNumber&service={SERVICE}&country={code}",
        "smsbower": f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getNumber&service={SERVICE}&country={code}",
        "tiger": f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getNumber&service={SERVICE}&country={code}",
    }
    return await fetch_url(urls.get(site, ""))

async def get_code(site, id_):
    urls = {
        "24sms7": f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getStatus&id={id_}",
        "smsbower": f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getStatus&id={id_}",
        "tiger": f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getStatus&id={id_}",
    }
    return await fetch_url(urls.get(site, ""))

async def cancel_number(site, id_):
    urls = {
        "24sms7": f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=setStatus&status=8&id={id_}",
        "smsbower": f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=setStatus&status=8&id={id_}",
        "tiger": f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=setStatus&status=8&id={id_}",
    }
    await fetch_url(urls.get(site, ""))

async def check_valid(number):
    url = "http://checker.irbots.com:2021/check"
    params = {"key": CHECKER_API_KEY, "numbers": number.strip("+")}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("status") == "ok" and data["data"].get(f"+{number.strip('+')}", False) is True
    return False

def chunk_buttons(buttons, n):
    return [buttons[i:i + n] for i in range(0, len(buttons), n)]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [[InlineKeyboardButton(site.capitalize(), callback_data=f"site_{site}")] for site in COUNTRIES.keys()]
    await update.message.reply_text("🌐 انتخاب سرویس:", reply_markup=InlineKeyboardMarkup(buttons))

async def site_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    site = query.data.split("_")[1]
    countries = COUNTRIES.get(site, {})
    country_buttons = [InlineKeyboardButton(name, callback_data=f"country_{site}_{code}") for name, code in countries.items()]
    buttons = chunk_buttons(country_buttons, 3)
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")])
    await query.edit_message_text("🌍 انتخاب کشور:", reply_markup=InlineKeyboardMarkup(buttons))

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    buttons = [[InlineKeyboardButton(site.capitalize(), callback_data=f"site_{site}")] for site in COUNTRIES.keys()]
    await query.edit_message_text("🌐 انتخاب سرویس:", reply_markup=InlineKeyboardMarkup(buttons))

async def back_to_sites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await back_to_start(update, context)

async def country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    cancel_flags.discard(user_id)
    valid_numbers[user_id] = []
    data_parts = query.data.split("_")
    if len(data_parts) < 3:
        await query.answer("خطا در دریافت اطلاعات کشور.", show_alert=True)
        return
    site, code = data_parts[1], data_parts[2]
    msg = await query.edit_message_text(
        "⏳ جستجو برای شماره سالم...",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ کنسل جستجو", callback_data="cancel_search")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_sites")]
        ])
    )
    max_req = MAX_PARALLEL_REQUESTS.get(site, 1)
    tasks = [asyncio.create_task(search_number(user_id, query.message.chat_id, msg.message_id, code, site, context)) for _ in range(max_req)]
    search_tasks[user_id] = tasks

async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer("جستجو لغو شد")
    cancel_flags.add(user_id)
    valid_numbers[user_id] = []
    tasks = search_tasks.pop(user_id, [])
    for task in tasks:
        task.cancel()
    await query.edit_message_text("🚫 جستجو لغو شد.")

async def search_number(user_id, chat_id, msg_id, code, site, context):
    while user_id not in cancel_flags:
        raw = await get_number(site, code)
        if raw in ("ERROR", "NO_NUMBERS", ""):
            await asyncio.sleep(3)
            continue
        if "ACCESS_NUMBER" in raw or "NO_NUMBERS" in raw:
            await asyncio.sleep(3)
            continue
        parts = raw.split(":")
        if len(parts) < 2:
            await asyncio.sleep(3)
            continue
        id_ = parts[1]
        number = parts[2] if len(parts) > 2 else ""
        if not number:
            await cancel_number(site, id_)
            continue
        valid = await check_valid(number)
        if valid:
            valid_numbers.setdefault(user_id, []).append((id_, number, site))
            text = f"✅ شماره سالم یافت شد:\n`{number}`"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📥 دریافت کد", callback_data=f"get_code_{site}_{id_}")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_sites")]
            ])
            try:
                await context.bot.edit_message_text(text, chat_id=chat_id, message_id=msg_id, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
            except:
                pass
            break
        else:
            await cancel_number(site, id_)
            await asyncio.sleep(2)

async def get_code_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    if len(data) < 4:
        await query.edit_message_text("خطا در دریافت کد.")
        return
    site, id_ = data[2], data[3]
    for _ in range(30):
        code = await get_code(site, id_)
        if code and code != "STATUS_WAIT_CODE" and code != "STATUS_CANCEL" and code != "ERROR":
            await query.edit_message_text(f"📩 کد دریافت شد:\n`{code}`", parse_mode=ParseMode.MARKDOWN)
            return
        await asyncio.sleep(3)
    await query.edit_message_text("⏳ کد دریافت نشد. دوباره تلاش کنید.")

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(site_selected, pattern="^site_"))
    app.add_handler(CallbackQueryHandler(country_selected, pattern="^country_"))
    app.add_handler(CallbackQueryHandler(cancel_search, pattern="^cancel_search$"))
    app.add_handler(CallbackQueryHandler(back_to_start, pattern="^back_to_start$"))
    app.add_handler(CallbackQueryHandler(back_to_sites, pattern="^back_to_sites$"))
    app.add_handler(CallbackQueryHandler(get_code_handler, pattern="^get_code_"))

    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
