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
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("24sms7", callback_data="site_24sms7")],
        [InlineKeyboardButton("SMSBower", callback_data="site_smsbower")],
        [InlineKeyboardButton("Tiger SMS", callback_data="site_tiger")],
    ]
    await update.message.reply_text("🌐 انتخاب سرویس:", reply_markup=InlineKeyboardMarkup(buttons))
    async def handle_site_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    site = query.data.split("_")[1]
    user_id = query.from_user.id
    user_sessions[user_id] = {"site": site}
    countries = {
        "24sms7": COUNTRIES_24SMS7,
        "smsbower": COUNTRIES_SMSBOWER,
        "tiger": COUNTRIES_TIGER_SMS,
    }[site]
    buttons = [[InlineKeyboardButton(name, callback_data=f"country_{code}")]
               for name, code in countries.items()]
    await query.edit_message_text("🌍 انتخاب کشور:", reply_markup=InlineKeyboardMarkup(buttons))

async def handle_country_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id not in user_sessions:
        await query.edit_message_text("❌ ابتدا یک سرویس انتخاب کنید.")
        return
    code = int(query.data.split("_")[1])
    user_sessions[user_id]["country"] = code
    site = user_sessions[user_id]["site"]

    if user_id in search_tasks:
        search_tasks[user_id].cancel()
        cancel_flags.discard(user_id)

    async def search_number():
        sem = asyncio.Semaphore(MAX_PARALLEL_REQUESTS[site])
        while user_id not in cancel_flags:
            async with sem:
                result = await {
                    "24sms7": get_number_24sms7,
                    "smsbower": get_number_smsbower,
                    "tiger": get_number_tiger,
                }[site](code)
                if "ACCESS_NUMBER" in result:
                    parts = result.strip().split(":")
                    id_ = parts[1]
                    number = parts[2]
                    is_valid = await check_valid(number)
                    if is_valid:
                        await query.edit_message_text(
                            f"✅ شماره سالم یافت شد:\n\n📱 Number: `{number}`\n🆔 ID: `{id_}`\n🌐 Site: {site}",
                            parse_mode=ParseMode.MARKDOWN
                        )
                        valid_numbers[user_id] = (site, id_)
                        cancel_flags.add(user_id)
                        return
                    else:
                        await cancel_number(site, id_)
                await asyncio.sleep(2)

    task = asyncio.create_task(search_number())
    search_tasks[user_id] = task
    await query.edit_message_text("🔍 در حال جستجو برای شماره سالم...")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cancel_flags.add(user_id)
    await update.message.reply_text("❌ جستجو لغو شد.")

async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in valid_numbers:
        site, id_ = valid_numbers[user_id]
        url = {
            "24sms7": f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=setStatus&status=6&id={id_}",
            "smsbower": f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=setStatus&status=6&id={id_}",
            "tiger": f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=setStatus&status=6&id={id_}",
        }[site]
        async with aiohttp.ClientSession() as s:
            await s.get(url)
        await update.message.reply_text("✅ شماره تایید شد.")
    else:
        await update.message.reply_text("❌ شماره‌ای برای تایید یافت نشد.")

async def webhook_handler(request):
    data = await request.json()
    await app.update_queue.put(Update.de_json(data, app.bot))
    return web.Response()

async def main():
    global app
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_site_selection, pattern="^site_"))
    app.add_handler(CallbackQueryHandler(handle_country_selection, pattern="^country_"))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("confirm", confirm))

    runner = web.AppRunner(web.Application().add_routes([web.post("/", webhook_handler)]))
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 8080)))
    await site.start()
    logging.info("Bot is running...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await app.updater.idle()

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())

