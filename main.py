import os
import asyncio
import logging
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

# توکن و کلیدهای API خودت رو اینجا بزار
BOT_TOKEN = os.getenv("BOT_TOKEN")  # توکن ربات تلگرام
API_KEY_24SMS7 = os.getenv("API_KEY_24SMS7")  # کلید 24sms7
API_KEY_SMSBOWER = os.getenv("API_KEY_SMSBOWER")  # کلید smsbower
CHECKER_API_KEY = os.getenv("CHECKER_API_KEY")  # کلید چکر شماره

SERVICE = "tg"  # نام سرویس برای API

# لیست کشورها با کدهای مربوط به هر سرویس
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
    "Country Slot 6": 0,
    "Country Slot 7": 0,
    "Country Slot 8": 0,
    "Country Slot 9": 0,
    "Country Slot 10": 0,
}

COUNTRIES_SMSBOWER = {
    "Kazakhstan": 2,
    "Iran": 57,
    "Russia": 0,
    "Ukraine": 1,
    "Mexico": 54,
    "Italy": 86,
    "Spain": 56,
    "Czech Republic": 10,
    "Paraguay": 23,
    "Hong Kong": 14,
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

# ذخیره‌سازی session کاربران و تسک‌ها
user_sessions = {}  # user_id: (activation_id, site)
search_tasks = {}  # user_id: asyncio.Task
cancel_flags = set()  # user_id هایی که لغو کردن

# --- توابع ارتباط با API ها ---

async def get_number(site: str, country_code: int) -> str:
    if site == "24sms7":
        url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getNumber&service={SERVICE}&country={country_code}"
    else:
        url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getNumber&service={SERVICE}&country={country_code}&maxPrice=58.67&providerIds=2195,2194,1000&exceptProviderIds=2196&phoneException=7700,7708"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()

async def get_status(site: str, activation_id: str) -> str:
    if site == "24sms7":
        url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getStatus&id={activation_id}"
    else:
        url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getStatus&id={activation_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()

async def cancel_activation(site: str, activation_id: str):
    if site == "24sms7":
        url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=setStatus&status=8&id={activation_id}"
    else:
        url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=setStatus&status=8&id={activation_id}"
    async with aiohttp.ClientSession() as session:
        await session.get(url)

async def check_valid_number(number: str) -> bool:
    # API چکر شماره (مثال)
    url = "http://checker.irbots.com:2021/check"
    params = {"key": CHECKER_API_KEY, "numbers": number}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("data", {}).get(number, False)
    return False

# --- منطق جستجو و دریافت شماره ---

async def search_number(user_id, chat_id, message_id, country_code, site, context):
    try:
        while True:
            if user_id in cancel_flags:
                cancel_flags.remove(user_id)
                await context.bot.edit_message_text(
                    chat_id=chat_id, message_id=message_id,
                    text="🚫 جستجو لغو شد."
                )
                return

            response = await get_number(site, country_code)
            # پاسخ API قالب: OK:id:شماره یا خطا
            if not response.startswith("ACCESS_NUMBER"):
                # اگر پاسخ خطا بود به کاربر اطلاع بده و قطع کن
                await context.bot.edit_message_text(
                    chat_id=chat_id, message_id=message_id,
                    text=f"❌ خطا در دریافت شماره:\n{response}\nلطفا دوباره تلاش کنید."
                )
                return

            parts = response.split(":")
            if len(parts) < 3:
                await context.bot.edit_message_text(
                    chat_id=chat_id, message_id=message_id,
                    text=f"❌ پاسخ نامعتبر از سرور:\n{response}"
                )
                return

            activation_id = parts[1]
            number = parts[2]
            # چک کردن سالم بودن شماره
            is_valid = await check_valid_number(number)
            if is_valid:
                # ذخیره session کاربر
                user_sessions[user_id] = (activation_id, site)
                text = (f"✅ شماره سالم پیدا شد:\n"
                        f"`{number}`\n\n"
                        f"🔄 منتظر دریافت کد بمانید یا از دکمه‌ها استفاده کنید.")
                buttons = [
                    [InlineKeyboardButton("⏳ دریافت کد دستی", callback_data="get_code")],
                    [InlineKeyboardButton("❌ لغو شماره", callback_data="cancel_number")],
                    [InlineKeyboardButton("❌ لغو جستجو", callback_data="cancel_search")],
                ]
                await context.bot.edit_message_text(
                    chat_id=chat_id, message_id=message_id,
                    text=text, parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(buttons)
                )
                # شروع دریافت خودکار کد
                await wait_for_code(user_id, chat_id, message_id, context)
                return
            else:
                # شماره ناسالم است، پیام به روزرسانی شود
                await context.bot.edit_message_text(
                    chat_id=chat_id, message_id=message_id,
                    text=f"⚠️ شماره ناسالم یافت شد: `{number}`\nدر حال جستجوی شماره سالم..."
                    , parse_mode="Markdown"
                )
            await asyncio.sleep(0.5)  # نیم ثانیه تاخیر برای سرعت مناسب

    except asyncio.CancelledError:
        # اگر تسک لغو شد
        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="🚫 جستجو لغو شد.")
        return
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ خطا: {e}")

# --- دریافت کد به صورت خودکار ---

async def wait_for_code(user_id, chat_id, message_id, context):
    for _ in range(120):  # حداکثر 120 بار چک کن (مثلا 2 دقیقه)
        if user_id not in user_sessions:
            # اگر session حذف شده (لغو شده)
            return
        activation_id, site = user_sessions[user_id]
        status = await get_status(site, activation_id)

        if status.startswith("STATUS_OK"):
            code = status.split(":")[1]
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=message_id,
                text=f"✅ کد دریافت شد:\n`{code}`",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ لغو شماره", callback_data="cancel_number")]
                ])
            )
            # حذف session بعد از دریافت کد
            user_sessions.pop(user_id, None)
            return

        elif status in ["STATUS_WAIT_CODE"] or status.startswith("STATUS_WAIT_RETRY"):
            # منتظر کد است
            await asyncio.sleep(5)
        else:
            # خطا یا لغو شده
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=message_id,
                text=f"❌ وضعیت نامعتبر: {status}"
            )
            user_sessions.pop(user_id, None)
            return
    # زمان تمام شد
    await context.bot.edit_message_text(
        chat_id=chat_id, message_id=message_id,
        text="❌ کد دریافت نشد. جستجو را دوباره شروع کنید."
    )
    user_sessions.pop(user_id, None)

# --- هندلرها ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("24sms7", callback_data="site_24sms7")],
        [InlineKeyboardButton("SMSBower", callback_data="site_smsbower")],
    ]
    await update.message.reply_text("🌐 انتخاب سرویس:", reply_markup=InlineKeyboardMarkup(buttons))

async def site_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    site = query.data.split("_")[1]
    countries = COUNTRIES_24SMS7 if site == "24sms7" else COUNTRIES_SMSBOWER
    buttons = []
    for name, code in countries.items():
        if code == 0:
            continue  # جایگاه‌های اضافی که صفر هستن رو رد کن
        buttons.append([InlineKeyboardButton(name, callback_data=f"country_{site}_{code}")])
    buttons.append([InlineKeyboardButton("❌ لغو جستجو", callback_data="cancel_search")])
    await query.edit_message_text("🌍 انتخاب کشور:", reply_markup=InlineKeyboardMarkup(buttons))

async def country_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, site, code = query.data.split("_")
    user_id = query.from_user.id

    # لغو جستجوی قبلی اگر هست
    if user_id in search_tasks:
        search_tasks[user_id].cancel()

    cancel_flags.discard(user_id)

    msg = await query.edit_message_text("⏳ جستجو برای شماره سالم...")

    task = asyncio.create_task(search_number(user_id, query.message.chat_id, msg.message_id, int(code), site, context))
    search_tasks[user_id] = task

async def cancel_search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("لغو جستجو شد.")
    user_id = query.from_user.id
    cancel_flags.add(user_id)
    if user_id in search_tasks:
        search_tasks[user_id].cancel()
        del search_tasks[user_id]
    await query.edit_message_text("🚫 جستجو لغو شد. /start برای شروع دوباره.")

async def cancel_number_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id in user_sessions:
        activation_id, site = user_sessions.pop(user_id)
        await cancel_activation(site, activation_id)
        buttons = [
            [InlineKeyboardButton("24sms7", callback_data="site_24sms7")],
            [InlineKeyboardButton("SMSBower", callback_data="site_smsbower")],
        ]
        await query.edit_message_text("✅ شماره لغو شد. انتخاب سرویس:", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await query.edit_message_text("❌ شماره فعالی موجود نیست.")

async def get_code_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if user_id not in user_sessions:
        await query.answer("❌ شماره فعالی وجود ندارد.", show_alert=True)
        return
    activation_id, site = user_sessions[user_id]
    status = await get_status(site, activation_id)
    if status.startswith("STATUS_OK"):
        code = status.split(":")[1]
        await query.answer(f"📩 کد: {code}", show_alert=True)
    elif status == "STATUS_WAIT_CODE" or status.startswith("STATUS_WAIT_RETRY"):
        await query.answer("⏳ هنوز کد دریافت نشده است.", show_alert=True)
    else:
        await query.answer(f"❌ وضعیت نامعتبر: {status}", show_alert=True)

# --- اصلی ---

def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(site_handler, pattern=r"^site_"))
    application.add_handler(CallbackQueryHandler(country_handler, pattern=r"^country_"))
    application.add_handler(CallbackQueryHandler(cancel_search_handler, pattern="cancel_search"))
    application.add_handler(CallbackQueryHandler(cancel_number_handler, pattern="cancel_number"))
    application.add_handler(CallbackQueryHandler(get_code_handler, pattern="get_code"))

    print("Bot started!")
    application.run_polling()

if __name__ == "__main__":
    main()
