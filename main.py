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
CHECKER_API_KEY = os.getenv("CHECKER_API_KEY")
SERVICE = "tg"

COUNTRIES_24SMS7 = {
    "Iran": 57, "Russia": 0, "Ukraine": 1, "Mexico": 54,
    "Italy": 86, "Spain": 56, "Czech Republic": 63, "Kazakhstan": 2,
    "Paraguay": 87, "Hong Kong": 14,
    "Country Slot 1": 0, "Country Slot 2": 0, "Country Slot 3": 0,
    "Country Slot 4": 0, "Country Slot 5": 0, "Country Slot 6": 0,
    "Country Slot 7": 0, "Country Slot 8": 0, "Country Slot 9": 0,
    "Country Slot 10": 0,
}

COUNTRIES_SMSBOWER = {
    "Kazakhstan": 2, "Iran": 57, "Russia": 0, "Ukraine": 1, "Mexico": 54,
    "Italy": 86, "Spain": 56, "Czech Republic": 10, "Paraguay": 23, "Hong Kong": 14,
    "Country Slot 1": 0, "Country Slot 2": 0, "Country Slot 3": 0,
    "Country Slot 4": 0, "Country Slot 5": 0, "Country Slot 6": 0,
    "Country Slot 7": 0, "Country Slot 8": 0, "Country Slot 9": 0,
    "Country Slot 10": 0,
}

user_sessions = {}  # user_id: (activation_id, site)
search_tasks = {}   # user_id: asyncio.Task
cancel_flags = set()  # user_id هایی که لغو جستجو زده‌اند

async def get_number_24sms7(code):
    url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getNumber&service={SERVICE}&country={code}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()

async def get_number_smsbower(code):
    url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getNumber&service={SERVICE}&country={code}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()

async def get_code(site, id_):
    if site == "24sms7":
        url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getStatus&id={id_}"
    else:
        url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getStatus&id={id_}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()

async def cancel_number(site, id_):
    if site == "24sms7":
        url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=setStatus&status=8&id={id_}"
    else:
        url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=setStatus&status=8&id={id_}"
    async with aiohttp.ClientSession() as session:
        await session.get(url)

async def check_valid(number):
    url = "http://checker.irbots.com:2021/check"
    params = {"key": CHECKER_API_KEY, "numbers": number}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("data", {}).get(number, False)
    return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("24sms7", callback_data="site_24sms7")],
        [InlineKeyboardButton("SMSBower", callback_data="site_smsbower")],
    ]
    await update.message.reply_text("🌐 انتخاب سرویس:", reply_markup=InlineKeyboardMarkup(buttons))

async def site_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    site = query.data.split("_")[1]
    countries = COUNTRIES_24SMS7 if site == "24sms7" else COUNTRIES_SMSBOWER
    buttons = []
    for name, code in countries.items():
        if code != 0:
            buttons.append([InlineKeyboardButton(name, callback_data=f"country_{site}_{code}")])
    await query.edit_message_text("🌍 انتخاب کشور:", reply_markup=InlineKeyboardMarkup(buttons))

async def country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, site, code = query.data.split("_")
    user_id = query.from_user.id
    cancel_flags.discard(user_id)
    buttons = [[InlineKeyboardButton("❌ لغو جستجو", callback_data="cancel_search")]]
    msg = await query.edit_message_text("⏳ جستجو برای شماره سالم...", reply_markup=InlineKeyboardMarkup(buttons))
    task = asyncio.create_task(search_number(user_id, query.message.chat_id, msg.message_id, int(code), site, context))
    search_tasks[user_id] = task

async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("جستجو لغو شد.")
    user_id = query.from_user.id
    cancel_flags.add(user_id)
    if user_id in search_tasks:
        search_tasks[user_id].cancel()
        del search_tasks[user_id]
    await query.edit_message_text("🚫 جستجو توسط شما لغو شد.")

async def cancel_number_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id in user_sessions:
        id_, site = user_sessions.pop(user_id)
        await cancel_number(site, id_)
        buttons = [
            [InlineKeyboardButton("24sms7", callback_data="site_24sms7")],
            [InlineKeyboardButton("SMSBower", callback_data="site_smsbower")],
        ]
        await query.edit_message_text("✅ شماره لغو شد. انتخاب سرویس:", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await query.edit_message_text("❌ شماره‌ای برای لغو وجود ندارد.")

async def check_code_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if user_id not in user_sessions:
        await query.answer("❌ شماره فعال نیست.", show_alert=True)
        return
    id_, site = user_sessions[user_id]
    resp = await get_code(site, id_)
    if resp.startswith("STATUS_OK"):
        code = resp.split(":")[1]
        await query.answer(f"📩 کد: {code}", show_alert=True)
    elif resp.startswith("STATUS_WAIT_CODE") or resp.startswith("STATUS_WAIT_RETRY"):
        await query.answer("⏳ هنوز کدی دریافت نشده.", show_alert=True)
    else:
        await query.answer("❌ خطا در دریافت کد.", show_alert=True)

async def search_number(user_id, chat_id, msg_id, code, site, context):
    while True:
        if user_id in cancel_flags:
            cancel_flags.remove(user_id)
            await context.bot.edit_message_text("🚫 جستجو لغو شد.", chat_id=chat_id, message_id=msg_id)
            return

        if site == "24sms7":
            resp = await get_number_24sms7(code)
        else:
            resp = await get_number_smsbower(code)

        if not resp.startswith("ACCESS_NUMBER"):
            await context.bot.edit_message_text("⏳ شماره‌ای در دسترس نیست، در حال تلاش مجدد...", chat_id=chat_id, message_id=msg_id)
            await asyncio.sleep(0.5)
            continue

        parts = resp.split(":")
        if len(parts) < 3:
            await context.bot.edit_message_text("⚠️ پاسخ نامعتبر از سرور، تلاش مجدد...", chat_id=chat_id, message_id=msg_id)
            await asyncio.sleep(0.5)
            continue

        activation_id = parts[1]
        number = parts[2]

        valid = await check_valid(number)
        if not valid:
            # شماره سالم نیست، لغوش کن
            await cancel_number(site, activation_id)
            await context.bot.edit_message_text(f"❌ شماره {number} ناسالم بود، در حال تلاش مجدد...", chat_id=chat_id, message_id=msg_id)
            await asyncio.sleep(0.5)
            continue

        # شماره سالم پیدا شد
        user_sessions[user_id] = (activation_id, site)
        buttons = [
            [InlineKeyboardButton("📩 دریافت خودکار کد", callback_data="check_code")],
            [InlineKeyboardButton("❌ لغو شماره فعال شده", callback_data="cancel_number")],
        ]
        await context.bot.edit_message_text(
            f"✅ شماره سالم یافت شد:\n`{number}`\n\nکد فعالسازی را دریافت کنید یا شماره را لغو کنید.",
            chat_id=chat_id,
            message_id=msg_id,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

        # منتظر دریافت کد شو (تا 10 دقیقه، هر 7 ثانیه چک می‌کند)
        for _ in range(85):
            if user_id in cancel_flags:
                cancel_flags.remove(user_id)
                await context.bot.edit_message_text("🚫 دریافت کد لغو شد.", chat_id=chat_id, message_id=msg_id)
                return
            status = await get_code(site, activation_id)
            if status.startswith("STATUS_OK"):
                code = status.split(":")[1]
                await context.bot.edit_message_text(
                    f"✅ شماره: `{number}`\n📩 کد دریافت شد:\n`{code}`",
                    chat_id=chat_id,
                    message_id=msg_id,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
                return
            elif status.startswith("STATUS_CANCEL"):
                await context.bot.edit_message_text("❌ شماره لغو شده است.", chat_id=chat_id, message_id=msg_id)
                return
            else:
                await asyncio.sleep(7)

        await context.bot.edit_message_text("⏰ زمان دریافت کد به پایان رسید.", chat_id=chat_id, message_id=msg_id)
        return

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(site_selected, pattern="^site_"))
    application.add_handler(CallbackQueryHandler(country_selected, pattern="^country_"))
    application.add_handler(CallbackQueryHandler(cancel_search, pattern="^cancel_search$"))
    application.add_handler(CallbackQueryHandler(cancel_number_callback, pattern="^cancel_number$"))
    application.add_handler(CallbackQueryHandler(check_code_callback, pattern="^check_code$"))

    print("Bot started.")
    application.run_polling()

if __name__ == "__main__":
    main()
