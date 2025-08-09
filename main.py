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
CHECKER_API_KEY = os.getenv("CHECKER_API_KEY")
SERVICE = "tg"

COUNTRIES = {
    "24sms7": {"Iran":57,"Russia":0,"Ukraine":1,"Mexico":54,"Italy":86,"Spain":56,"Czech Republic":63,"Kazakhstan":2,
               "Paraguay":87,"Hong Kong":14,"macao":20,"irland":23,"serbia":29,"romani":32,"estonia":34,"germany":43,
               "auustria":50,"belarus":51,"tiwan":55,"newziland":67,"belgium":82,"moldova":85,"armenia":148,"maldiv":159,
               "guadlouap":160,"denmark":172,"norway":174,"switzerland":173,"giblarator":201},
    "smsbower": {"Kazakhstan":2,"Iran":57,"Russia":0,"Ukraine":1,"Mexico":54,"Italy":86,"Spain":56,"Czech Republic":63,
                 "Paraguay":87,"Hong Kong":14,"macao":20,"irland":23,"serbia":29,"romani":32,"estonia":34,"germany":43,
                 "auustria":50,"belarus":51,"tiwan":55,"newziland":67,"belgium":82,"moldova":85,"armenia":148,"maldiv":159,
                 "guadlouap":160,"denmark":172,"norway":174,"switzerland":173,"giblarator":201},
    "tiger": {"Iran":57,"Russia":0,"Ukraine":1,"Mexico":54,"Italy":86,"Spain":56,"Czech Republic":63,"Kazakhstan":2,
              "Paraguay":87,"Hong Kong":14,"macao":20,"irland":23,"serbia":29,"romani":32,"estonia":34,"germany":43,
              "auustria":50,"belarus":51,"tiwan":55,"newziland":67,"belgium":82,"moldova":85,"armenia":148,"maldiv":159,
              "guadlouap":160,"denmark":172,"norway":174,"switzerland":173,"giblarator":201}
}

MAX_PARALLEL_REQUESTS = {"24sms7":2,"smsbower":5,"tiger":1}

user_sessions = {}
search_tasks = {}
cancel_flags = set()
valid_numbers = {}

async def fetch_url(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                return await resp.text()
    except Exception as e:
        logging.error(f"fetch_url error: {e}")
        return "ERROR"

async def get_number(site, code):
    urls = {
        "24sms7":f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getNumber&service={SERVICE}&country={code}",
        "smsbower":f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getNumber&service={SERVICE}&country={code}&maxPrice=0.75&phoneException=7700,7708",
        "tiger":f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getNumber&service={SERVICE}&country={code}&maxPrice=50"
    }
    return await fetch_url(urls.get(site,""))

async def get_code(site, id_):
    urls = {
        "24sms7":f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getStatus&id={id_}",
        "smsbower":f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getStatus&id={id_}",
        "tiger":f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getStatus&id={id_}"
    }
    return await fetch_url(urls.get(site,""))

async def cancel_number(site, id_):
    urls = {
        "24sms7":f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=setStatus&status=8&id={id_}",
        "smsbower":f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=setStatus&status=8&id={id_}",
        "tiger":f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=setStatus&status=8&id={id_}"
    }
    await fetch_url(urls.get(site,""))

async def check_valid(number):
    url = "http://checker.irbots.com:2021/check"
    params = {"key":CHECKER_API_KEY, "numbers":number.strip("+")}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("status")=="ok" and data["data"].get(f"+{number.strip('+')}", False) is True
    return False

def chunk_buttons(buttons, n):
    return [buttons[i:i+n] for i in range(0,len(buttons),n)]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [[InlineKeyboardButton(site.capitalize(), callback_data=f"site_{site}")] for site in COUNTRIES.keys()]
    await update.message.reply_text("🌐 انتخاب سرویس:", reply_markup=InlineKeyboardMarkup(buttons))

async def site_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    site = query.data.split("_")[1]
    countries = COUNTRIES.get(site,{})
    country_buttons = [InlineKeyboardButton(name, callback_data=f"country_{site}_{id_}") for name,id_ in countries.items()]
    buttons = chunk_buttons(country_buttons, 3)
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")])
    await query.edit_message_text("🌍 انتخاب کشور:", reply_markup=InlineKeyboardMarkup(buttons))

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    buttons = [[InlineKeyboardButton(site.capitalize(), callback_data=f"site_{site}")] for site in COUNTRIES.keys()]
    await query.edit_message_text("🌐 انتخاب سرویس:", reply_markup=InlineKeyboardMarkup(buttons))

async def back_to_sites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await back_to_start(update, context)

async def country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    cancel_flags.discard(user_id)
    valid_numbers[user_id] = []
    site, code = query.data.split("_")[1], query.data.split("_")[2]
    msg = await query.edit_message_text("⏳ جستجو برای شماره سالم...", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ کنسل جستجو", callback_data="cancel_search")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_sites")]
    ]))

    max_req = MAX_PARALLEL_REQUESTS.get(site,1)
    tasks = [asyncio.create_task(search_number(user_id, query.message.chat_id, msg.message_id, code, site, context)) for _ in range(max_req)]
    search_tasks[user_id] = tasks

async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer("جستجو لغو شد")
    cancel_flags.add(user_id)
    valid_numbers[user_id] = []
    tasks = search_tasks.get(user_id, [])
    for task in tasks:
        task.cancel()
    search_tasks.pop(user_id, None)
    await query.edit_message_text("🚫 جستجو لغو شد.")

async def start_timer(chat_id, msg_id, number, context):
    total_seconds = 1500  # 25 minutes
    while total_seconds >= 0:
        mins, secs = divmod(total_seconds, 60)
        timer_text = f"⏳ زمان باقی‌مانده: {mins:02}:{secs:02}"
        try:
            await context.bot.edit_message_text(
                f"📱 شماره سالم: <code>{number}</code>\n{timer_text}",
                chat_id=chat_id,
                message_id=msg_id,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📩 دریافت کد", callback_data=f"checkcode_{msg_id}")],
                    [InlineKeyboardButton("❌ لغو شماره", callback_data=f"cancel_{msg_id}")],
                    [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_sites")]
                ])
            )
        except:
            break
        await asyncio.sleep(1)
        total_seconds -= 1

async def search_number(user_id, chat_id, msg_id, code, site, context):
    async def delayed_cancel(id_, site_):
        await asyncio.sleep(122)
        active_ids = [i[0] for i in valid_numbers.get(user_id,[])]
        if id_ not in active_ids:
            await cancel_number(site_, id_)

    while user_id not in cancel_flags:
        if (site in ["24sms7","tiger"] and len(valid_numbers[user_id])>=1) or (site=="smsbower" and len(valid_numbers[user_id])>=5):
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
                    [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_sites")]
                ])
            )
            valid_numbers[user_id].append((id_, site, number, msg.message_id))
            asyncio.create_task(auto_check_code(user_id, chat_id, msg.message_id, id_, site, number, context))
            asyncio.create_task(start_timer(chat_id, msg.message_id, number, context))
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
    if user_id in cancel_flags:
        cancel_flags.discard(user_id)
        await context.bot.edit_message_text("🚫 جستجو لغو شد.", chat_id=chat_id, message_id=msg_id)

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
            return
    await query.answer("❌ شماره یافت نشد.", show_alert=True)

async def cancel_number_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    id_ = query.data.split("_")[1]
    for i, rec in enumerate(valid_numbers.get(user_id, [])):
        if rec[0] == id_:
            site = rec[1]
            await cancel_number(site, id_)
            valid_numbers[user_id].pop(i)
            await query.edit_message_text("❌ شماره لغو شد.")
            return
    await query.answer("❌ شماره یافت نشد.", show_alert=True)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(site_selected, pattern="^site_"))
    app.add_handler(CallbackQueryHandler(country_selected, pattern="^country_"))
    app.add_handler(CallbackQueryHandler(cancel_search, pattern="^cancel_search$"))
    app.add_handler(CallbackQueryHandler(dynamic_check_code, pattern="^checkcode_"))
    app.add_handler(CallbackQueryHandler(cancel_number_button, pattern="^cancel_"))
    app.add_handler(CallbackQueryHandler(back_to_start, pattern="^back_to_start$"))
    app.add_handler(CallbackQueryHandler(back_to_sites, pattern="^back_to_sites$"))
    app.run_polling()

if __name__ == "__main__":
    main()
