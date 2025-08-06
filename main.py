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
    "macao": 20,
    "irland": 23,
    "serbia": 29,
    "romani": 32,
    "estonia": 34,
    "germany": 43,
    "auustria": 50,
    "belarus": 51,
    "tiwan": 55,
    "newziland": 67,
    "belgium": 82,
    "moldova": 85,
    "armenia": 148,
    "maldiv": 159,
    "guadlouap": 160,
    "denmark": 172,
    "norway": 174,
    "switzerland": 173,
    "giblarator": 201,
    "Country Slot 8": 0,
    "Country Slot 9": 0,
    "Country Slot 10": 0,
}

COUNTRIES_SMSBOWER = {
    "Kazakhstan": 2,
    "Country Slot 1": 0,
    "Country Slot 2": 0,
    "try Slot 3": 0,
    "Country Slot 4": 0,
    "Country Slot 5": 0,
    "Country Slot 6": 0,
    "Country Slot 7": 0,
    "Country Slot 8": 0,
    "Country Slot 9": 0,
    "Country Slot 10": 0,
}

OPERATORS_SMSBOWER = {
    "All": "",
    "Provider 2195": "2195",
    "Provider 2194": "2194",
    "Provider 2196": "2196",
    "Provider 1000": "1000",
}

COUNTRIES_TIGER_SMS = {
    "Iran": 57,
    "Russia": 0,
    "Ukraine": 1,
    "armanei": 148,
    "Mexico": 54,
    "Italy": 86,
    "Spain": 56,
    "Czech Republic": 63,
    "Kazakhstan": 2,
    "Paraguay": 87,
    "Hong Kong": 14,
    "macao": 20,
    "irland": 23,
    "serbia": 29,
    "romani": 32,
    "estonia": 34,
    "germany": 43,
    "auustria": 50,
    "belarus": 51,
    "tiwan": 55,
    "newziland": 67,
    "belgium": 82,
    "moldova": 85,
    "armenia": 148,
    "maldiv": 159,
    "guadlouap": 160,
    "denmark": 172,
    "norway": 174,
    "switzerland": 173,
    "giblarator": 201,
    "peru": 65,
    "Country Slot 2": 0,
    "try Slot 3": 0,
    "england": 16,
    "uzbekistan": 40,
    "zimbabwe": 96,
    "zambie": 147,
    "bolivi": 92,
    "Country Slot 9": 0,
    "Country Slot 10": 0,
}

OPERATORS_TIGER = {
    "All": "",
    "Provider 1": "1",
    "Provider 2": "2",
    "Provider 3": "3",
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

# برای ذخیره انتخاب اپراتور و ماکزیمم قیمت کاربر
user_preferences = {}

async def get_number_24sms7(code):
    url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getNumber&service={SERVICE}&country={code}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def get_number_smsbower(code, operator, max_price):
    url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getNumber&service={SERVICE}&country={code}"
    if operator:
        url += f"&providerIds={operator}"
    if max_price:
        url += f"&maxPrice={max_price}"
    url += "&exceptProviderIds=&phoneException=7700,7708"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def get_number_tiger(code, operator, max_price):
    url = f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getNumber&service={SERVICE}&country={code}"
    if max_price:
        url += f"&maxPrice={max_price}"
    if operator:
        url += f"&providerIds={operator}"
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

def chunk_buttons(button_list, n):
    return [button_list[i:i + n] for i in range(0, len(button_list), n)]

async def site_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    site = query.data.split("_")[1]
    user_id = query.from_user.id
    user_sessions[user_id] = {"site": site}

    if site == "24sms7":
        countries = COUNTRIES_24SMS7
        buttons = [InlineKeyboardButton(name, callback_data=f"country_{site}_{id_}") for name, id_ in countries.items()]
        buttons = chunk_buttons(buttons, 3)
        buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")])
        await query.edit_message_text("🌍 انتخاب کشور:", reply_markup=InlineKeyboardMarkup(buttons))
    elif site == "smsbower":
        countries = COUNTRIES_SMSBOWER
        buttons = [InlineKeyboardButton(name, callback_data=f"country_{site}_{id_}") for name, id_ in countries.items()]
        buttons = chunk_buttons(buttons, 3)
        buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")])
        await query.edit_message_text("🌍 انتخاب کشور:", reply_markup=InlineKeyboardMarkup(buttons))
    elif site == "tiger":
        countries = COUNTRIES_TIGER_SMS
        buttons = [InlineKeyboardButton(name, callback_data=f"country_{site}_{id_}") for name, id_ in countries.items()]
        buttons = chunk_buttons(buttons, 3)
        buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")])
        await query.edit_message_text("🌍 انتخاب کشور:", reply_markup=InlineKeyboardMarkup(buttons))

async def back_to_sites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, context)

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, context)

async def operator_and_price_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # format: country_smsbower_2 or country_tiger_57 etc.
    _, site, code = data.split("_")
    user_id = query.from_user.id

    user_sessions[user_id]["country_code"] = code

    # آماده کردن دکمه‌های انتخاب اپراتور و قیمت حداکثر برای سایت‌های smsbower و tiger
    if site == "smsbower":
        operator_buttons = [InlineKeyboardButton(name, callback_data=f"operator_smsbower_{code}_{op}") for name, op in OPERATORS_SMSBOWER.items()]
        max_price_buttons = [
            InlineKeyboardButton("قیمت حداکثر: 10", callback_data=f"maxprice_smsbower_{code}_10"),
            InlineKeyboardButton("قیمت حداکثر: 20", callback_data=f"maxprice_smsbower_{code}_20"),
            InlineKeyboardButton("قیمت حداکثر: 30", callback_data=f"maxprice_smsbower_{code}_30"),
            InlineKeyboardButton("بدون محدودیت قیمت", callback_data=f"maxprice_smsbower_{code}_0"),
        ]
        buttons = chunk_buttons(operator_buttons, 2) + [chunk_buttons(max_price_buttons, 2)[0], chunk_buttons(max_price_buttons, 2)[1]]
        buttons.append([InlineKeyboardButton("شروع جستجو", callback_data=f"start_search_smsbower_{code}")])
        buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_sites")])
        await query.edit_message_text("📡 انتخاب اپراتور:", reply_markup=InlineKeyboardMarkup(buttons))
        # مقدار پیش‌فرض
        user_preferences[user_id] = {"operator": "", "max_price": 0}

    elif site == "tiger":
        operator_buttons = [InlineKeyboardButton(name, callback_data=f"operator_tiger_{code}_{op}") for name, op in OPERATORS_TIGER.items()]
        max_price_buttons = [
            InlineKeyboardButton("قیمت حداکثر: 10", callback_data=f"maxprice_tiger_{code}_10"),
            InlineKeyboardButton("قیمت حداکثر: 20", callback_data=f"maxprice_tiger_{code}_20"),
            InlineKeyboardButton("قیمت حداکثر: 30", callback_data=f"maxprice_tiger_{code}_30"),
            InlineKeyboardButton("بدون محدودیت قیمت", callback_data=f"maxprice_tiger_{code}_0"),
        ]
        buttons = chunk_buttons(operator_buttons, 2) + [chunk_buttons(max_price_buttons, 2)[0], chunk_buttons(max_price_buttons, 2)[1]]
        buttons.append([InlineKeyboardButton("شروع جستجو", callback_data=f"start_search_tiger_{code}")])
        buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_sites")])
        await query.edit_message_text("📡 انتخاب اپراتور:", reply_markup=InlineKeyboardMarkup(buttons))
        user_preferences[user_id] = {"operator": "", "max_price": 0}

    else:
        # برای 24sms7 مستقیم شروع جستجو
        await country_selected(update, context)

async def operator_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # format: operator_smsbower_2_2195 or operator_tiger_57_1 etc.
    _, site, code, operator = data.split("_", 3)
    user_id = query.from_user.id
    prefs = user_preferences.get(user_id, {"operator": "", "max_price": 0})
    prefs["operator"] = operator
    user_preferences[user_id] = prefs
    await query.answer(f"اپراتور انتخاب شد: {operator}", show_alert=True)

async def max_price_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # format: maxprice_smsbower_2_10 or maxprice_tiger_57_0 etc.
    _, site, code, max_price = data.split("_", 3)
    user_id = query.from_user.id
    prefs = user_preferences.get(user_id, {"operator": "", "max_price": 0})
    prefs["max_price"] = int(max_price)
    user_preferences[user_id] = prefs
    await query.answer(f"حداکثر قیمت انتخاب شد: {max_price}", show_alert=True)

async def start_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # format: start_search_smsbower_2 or start_search_tiger_57 or start_search_24sms7_57
    parts = data.split("_")
    site = parts[2]
    code = parts[3]

    user_id = query.from_user.id
    user_sessions[user_id]["country_code"] = code
    if site in ["smsbower", "tiger"]:
        prefs = user_preferences.get(user_id, {"operator": "", "max_price": 0})
        operator = prefs.get("operator", "")
        max_price = prefs.get("max_price", 0)
    else:
        operator = ""
        max_price = 0

    await query.edit_message_text("🔄 در حال جستجوی شماره... لطفا صبر کنید.")

    # لغو جستجوی قبلی در صورت وجود
    if user_id in search_tasks:
        search_tasks[user_id].cancel()
    cancel_flags.discard(user_id)

    # شروع تسک جستجو
    task = asyncio.create_task(search_number_loop(user_id, site, code, operator, max_price, update, context))
    search_tasks[user_id] = task

async def search_number_loop(user_id, site, code, operator, max_price, update, context):
    try:
        while True:
            if user_id in cancel_flags:
                await context.bot.send_message(chat_id=user_id, text="❌ جستجو لغو شد.")
                cancel_flags.discard(user_id)
                break

            # درخواست شماره جدید از API
            if site == "24sms7":
                resp = await get_number_24sms7(code)
            elif site == "smsbower":
                resp = await get_number_smsbower(code, operator, max_price)
            elif site == "tiger":
                resp = await get_number_tiger(code, operator, max_price)
            else:
                await context.bot.send_message(chat_id=user_id, text="❌ سرویس نامعتبر است.")
                break

            if resp.startswith("ACCESS_NUMBER"):
                parts = resp.split(":")
                if len(parts) < 2:
                    await context.bot.send_message(chat_id=user_id, text="خطا در دریافت شماره.")
                    break
                id_ = parts[1]
                # دریافت شماره
                number = await fetch_number_from_id(site, id_)
                valid = await check_valid(number)
                if valid:
                    # ذخیره شماره معتبر برای کاربر
                    valid_numbers[user_id] = (number, id_, site)
                    await context.bot.send_message(chat_id=user_id, text=f"✅ شماره معتبر یافت شد:\n{number}\nکد را صبر کنید...")
                    # شروع چک کردن کد پیامکی
                    code_received = False
                    for _ in range(20):  # تا 20 بار یا حدود 2 دقیقه بررسی کد
                        if user_id in cancel_flags:
                            await cancel_number(site, id_)
                            await context.bot.send_message(chat_id=user_id, text="❌ جستجو لغو شد.")
                            cancel_flags.discard(user_id)
                            return
                        code_resp = await get_code(site, id_)
                        if "STATUS_OK" in code_resp:
                            code_msg = code_resp.split(":")[-1]
                            await context.bot.send_message(chat_id=user_id, text=f"📩 کد پیامکی:\n{code_msg}")
                            code_received = True
                            break
                        await asyncio.sleep(6)
                    if not code_received:
                        await context.bot.send_message(chat_id=user_id, text="⏳ کدی دریافت نشد. شماره لغو شد.")
                        await cancel_number(site, id_)
                else:
                    await context.bot.send_message(chat_id=user_id, text=f"⚠️ شماره نامعتبر: {number}\nجستجوی مجدد...")
                    await cancel_number(site, id_)
            else:
                await context.bot.send_message(chat_id=user_id, text="🚫 شماره‌ای در دسترس نیست، کمی بعد تلاش کنید.")
                await asyncio.sleep(10)
    except asyncio.CancelledError:
        await context.bot.send_message(chat_id=user_id, text="❌ جستجو متوقف شد.")
    except Exception as e:
        await context.bot.send_message(chat_id=user_id, text=f"❌ خطا رخ داد: {str(e)}")

async def fetch_number_from_id(site, id_):
    # تابعی برای دریافت شماره از API با توجه به سایت و id
    # این تابع باید درخواست API یا دیتایی که شماره رو میده رو برگردونه
    # در اینجا به صورت نمونه کد فرضی نوشته شده
    # تو باید متناسب با API واقعی‌ات اصلاحش کنی
    if site == "24sms7":
        url = f"https://24sms7.com/api/getNumber?id={id_}&api_key={API_KEY_24SMS7}"
    elif site == "smsbower":
        url = f"https://smsbower.online/api/getNumber?id={id_}&api_key={API_KEY_SMSBOWER}"
    elif site == "tiger":
        url = f"https://api.tiger-sms.com/api/getNumber?id={id_}&api_key={API_KEY_TIGER}"
    else:
        return None

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            text = await resp.text()
            # فرض می‌کنیم پاسخ فقط شماره هست، یا json شامل شماره است
            return text.strip()

async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cancel_flags.add(user_id)
    await update.message.reply_text("درخواست لغو جستجو ثبت شد...")

def main():
    nest_asyncio.apply()
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(site_selected, pattern="^site_"))
    application.add_handler(CallbackQueryHandler(back_to_sites, pattern="^back_to_sites$"))
    application.add_handler(CallbackQueryHandler(back_to_start, pattern="^back_to_start$"))
    application.add_handler(CallbackQueryHandler(operator_and_price_selection, pattern="^country_"))
    application.add_handler(CallbackQueryHandler(operator_selected, pattern="^operator_"))
    application.add_handler(CallbackQueryHandler(max_price_selected, pattern="^maxprice_"))
    application.add_handler(CallbackQueryHandler(start_search, pattern="^start_search_"))

    application.add_handler(CommandHandler("cancel", cancel_search))

    application.run_polling()

if __name__ == "__main__":
    main()
