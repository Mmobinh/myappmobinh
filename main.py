import os
import asyncio
import logging
import nest_asyncio
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from aiohttp import web

# آماده‌سازی لاگ‌گیری
logging.basicConfig(level=logging.INFO)

# متغیرهای محیطی
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY_24SMS7 = os.getenv("API_KEY_24SMS7")
API_KEY_SMSBOWER = os.getenv("API_KEY_SMSBOWER")
API_KEY_TIGER = os.getenv("API_KEY_TIGER")
CHECKER_API_KEY = os.getenv("CHECKER_API_KEY")
SERVICE = "tg"

# کشورهای موجود برای هر سرویس
COUNTRIES = {
    "24sms7": {
        "Iran": 57, "Russia": 0, "Ukraine": 1, "Kazakhstan": 2, "Mexico": 54,
        "Italy": 86, "Spain": 56, "Czech Republic": 63
        # کشورهای بیشتر را اینجا اضافه کنید
    },
    "smsbower": {
        "Kazakhstan": 2,
        "cameron": 41,
    },
    "tiger": {
        "Iran": 57, "Russia": 0, "Ukraine": 1, "Kazakhstan": 2, "Paraguay": 87,
        "Hong Kong": 14, "Ireland": 23
        # کشورهای بیشتر را اینجا اضافه کنید
    }
}

MAX_PARALLEL_REQUESTS = {
    "24sms7": 1,
    "smsbower": 5,
    "tiger": 1,
}

# داده‌های برنامه
user_sessions = {}
search_tasks = {}
cancel_flags = set()
valid_numbers = {}

# تابعی برای درخواست به API با مدیریت خطا
async def fetch_url(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                return await response.text()
    except aiohttp.ClientError as e:
        logging.error(f"خطا در فراخوانی آدرس {url}: {e}")
        return "ERROR"

# تابعی برای گرفتن شماره تلفن
async def get_number(site, code):
    base_urls = {
        "24sms7": f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getNumber&service={SERVICE}&country={code}",
        "smsbower": f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getNumber&service={SERVICE}&country={code},&maxPrice=58.67&providerIds=1000,2196,2195,2194&exceptProviderIds=&phoneException=7700,7708"
        "tiger": f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getNumber&service={SERVICE}&country={code}",
    }
    return await fetch_url(base_urls.get(site, ""))

# تابع بررسی اعتبار شماره
async def check_valid(number):
    url = "http://checker.irbots.com:2021/check"
    params = {"key": CHECKER_API_KEY, "numbers": number.strip("+")}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            if response.status == 200:
                data = await response.json()
                return data.get("status") == "ok" and data["data"].get(f"+{number.strip('+')}", False) is True
    return False

# شروع کار
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [[InlineKeyboardButton(site.capitalize(), callback_data=f"site_{site}")] for site in COUNTRIES.keys()]
    await update.message.reply_text("🌐 انتخاب سرویس:", reply_markup=InlineKeyboardMarkup(buttons))

# انتخاب سایت
async def site_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    site = query.data.split("_")[1]
    countries = COUNTRIES.get(site, {})
    
    country_buttons = [InlineKeyboardButton(name, callback_data=f"country_{site}_{id_}") for name, id_ in countries.items()]
    buttons = chunk_buttons(country_buttons, 3)
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")])
    await query.edit_message_text("🌍 انتخاب کشور:", reply_markup=InlineKeyboardMarkup(buttons))

# Chunk کردن لیست دکمه‌ها
def chunk_buttons(button_list, n):
    return [button_list[i:i + n] for i in range(0, len(button_list), n)]

# بازگشت به مرحله انتخاب سایت‌ها
async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, context)

# انتخاب کشور
async def country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, site, code = query.data.split("_")
    user_id = query.from_user.id
    cancel_flags.discard(user_id)
    valid_numbers[user_id] = []
    msg = await query.edit_message_text("⏳ جستجو برای شماره سالم...", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ کنسل جستجو", callback_data="cancel_search")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")]
    ]))

    max_requests = MAX_PARALLEL_REQUESTS.get(site, 1)

    async def run_parallel_search(i):
        try:
            await search_number(user_id, query.message.chat_id, msg.message_id, code, site, context)
        except asyncio.CancelledError:
            pass

    tasks = [asyncio.create_task(run_parallel_search(i)) for i in range(max_requests)]
    search_tasks[user_id] = tasks

# کنسل کردن جستجو
async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    cancel_flags.add(user_id)
    valid_numbers[user_id] = []

    tasks = search_tasks.get(user_id, [])
    for task in tasks:
        task.cancel()
    search_tasks.pop(user_id, None)

    await query.answer("جستجو لغو شد")
    await query.edit_message_text("🚫 جستجو لغو شد.")

# تابع جستجوی شماره
async def search_number(user_id, chat_id, msg_id, code, site, context):
    while user_id not in cancel_flags:
        if (site in ["24sms7", "tiger"] and len(valid_numbers[user_id]) >= 1) or (site == "smsbower" and len(valid_numbers[user_id]) >= 5):
            break

        resp = await get_number(site, code)
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
            asyncio.create_task(cancel_number(site, id_))
        await asyncio.sleep(1)

    if user_id in cancel_flags:
        cancel_flags.discard(user_id)
        await context.bot.edit_message_text("🚫 جستجو لغو شد.", chat_id=chat_id, message_id=msg_id)

# تابع خودکار برای چک کردن کد
async def auto_check_code(user_id, chat_id, msg_id, id_, site, number, context):
    while True:
        await asyncio.sleep(1)
        resp = await get_code(site, id_)
        if resp.startswith("STATUS_OK:"):
            code = resp[len("STATUS_OK:"):].strip()
            await context.bot.edit_message_text(
                f"📩 کد برای شماره <code>{number}</code> دریافت شد:\n<code>{code}</code>",
                chat_id=chat_id, message_id=msg_id, parse_mode=ParseMode.HTML
            )
            return

# دریافت کد به صورت پویا
async def dynamic_check_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    id_ = query.data.split("_")[1]
    for rec in valid_numbers.get(user_id, []):
        if rec[0] == id_:
            _, site, number, msg_id = rec
            resp = await get_code(site, id_)
            if resp.startswith("STATUS_OK:"):
                code = resp[len("STATUS_OK:"):].strip()
                await context.bot.edit_message_text(
                    f"📩 کد برای شماره <code>{number}</code> دریافت شد:\n<code>{code}</code>",
                    chat_id=query.message.chat_id, message_id=msg_id, parse_mode=ParseMode.HTML
                )
            elif resp == "STATUS_WAIT_CODE":
                await query.answer("⏳ هنوز کدی دریافت نشده.", show_alert=True)
            else:
                await query.answer("❌ خطا در دریافت کد.", show_alert=True)
            break

# لغو شماره به صورت پویا
async def dynamic_cancel_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    id_ = query.data.split("_")[1]
    new_list = []
    for rec in valid_numbers.get(user_id, []):
        if rec[0] == id_:
            await cancel_number(rec[1], rec[0])
            await context.bot.edit_message_text(
                f"❌ شماره لغو شد: <code>{rec[2]}</code>",
                chat_id=query.message.chat_id, message_id=rec[3], parse_mode=ParseMode.HTML
            )
        else:
            new_list.append(rec)
    valid_numbers[user_id] = new_list

# راه‌اندازی وب‌سرور برای زنده نگه داشتن ربات
async def web_handler(request):
    return web.Response(text="✅ Bot is Alive!")

async def start_webserver():
    app = web.Application()
    app.add_routes([web.get('/', web_handler)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

# تابع اصلی برای اجرای ربات
async def main():
    await start_webserver()
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(site_selected, pattern="^site_"))
    application.add_handler(CallbackQueryHandler(back_to_start, pattern="^back_to_sites$")) 
    application.add_handler(CallbackQueryHandler(back_to_start, pattern="^back_to_start$"))
    application.add_handler(CallbackQueryHandler(country_selected, pattern="^country_"))
    application.add_handler(CallbackQueryHandler(cancel_search, pattern="^cancel_search$"))
    application.add_handler(CallbackQueryHandler(dynamic_check_code, pattern="^checkcode_"))
    application.add_handler(CallbackQueryHandler(dynamic_cancel_number, pattern="^cancel_"))
    await application.run_polling()

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())

