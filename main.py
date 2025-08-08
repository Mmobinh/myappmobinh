import os, asyncio, logging, nest_asyncio, aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from aiohttp import web

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY_24SMS7 = os.getenv("API_KEY_24SMS7")
API_KEY_SMSBOWER = os.getenv("API_KEY_SMSBOWER")
API_KEY_TIGER = os.getenv("API_KEY_TIGER")
CHECKER_API_KEY = os.getenv("CHECKER_API_KEY")
SERVICE = "tg"

COUNTRIES = {
    "24sms7": {"Iran": 57, "Russia": 0, "Ukraine": 1, "Mexico": 54, "Italy": 86, "Spain": 56},
    "smsbower": {"Kazakhstan": 2, "Iran": 57, "Russia": 0, "Ukraine": 1, "Mexico": 54},
    "tiger": {"Iran": 57, "Russia": 0, "Ukraine": 1, "Mexico": 54}
}

MAX_PARALLEL_REQUESTS = {"24sms7": 1, "smsbower": 5, "tiger": 1}

user_sessions, search_tasks, cancel_flags, valid_numbers = {}, {}, set(), {}

async def fetch_url(url):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url) as r:
                return await r.text()
    except aiohttp.ClientError as e:
        logging.error(f"Fetch error {url}: {e}")
        return "ERROR"

async def get_number(site, code):
    urls = {
        "24sms7": f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getNumber&service={SERVICE}&country={code}",
        "smsbower": f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getNumber&service={SERVICE}&country={code}&phoneException=7700,7708",
        "tiger": f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getNumber&service={SERVICE}&country={code}&maxPrice=25&providerIds=55,234,188",
    }
    return await fetch_url(urls.get(site, ""))

async def get_code(site, id_):
    urls = {
        "24sms7": f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getStatus&id={id_}",
        "smsbower": f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getStatus&id={id_}",
        "tiger": f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getStatus&id={id_}",
    }
    return await fetch_url(urls[site])

async def cancel_number(site, id_):
    urls = {
        "24sms7": f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=setStatus&status=8&id={id_}",
        "smsbower": f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=setStatus&status=8&id={id_}",
        "tiger": f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=setStatus&status=8&id={id_}",
    }
    await fetch_url(urls[site])

async def check_valid(number):
    url = "http://checker.irbots.com:2021/check"
    params = {"key": CHECKER_API_KEY, "numbers": number.strip("+")}
    async with aiohttp.ClientSession() as s:
        async with s.get(url, params=params) as r:
            if r.status == 200:
                d = await r.json()
                return d.get("status") == "ok" and d["data"].get(f"+{number.strip('+')}", False) is True
    return False

def chunk_buttons(btns, n):
    return [btns[i:i+n] for i in range(0,len(btns),n)]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [[InlineKeyboardButton(s.capitalize(), callback_data=f"site_{s}")] for s in COUNTRIES]
    await update.message.reply_text("🌐 انتخاب سرویس:", reply_markup=InlineKeyboardMarkup(buttons))

async def site_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    site = q.data.split("_")[1]
    countries = COUNTRIES.get(site, {})
    btns = [InlineKeyboardButton(n, callback_data=f"country_{site}_{c}") for n,c in countries.items()]
    btns = chunk_buttons(btns, 3)
    btns.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")])
    await q.edit_message_text("🌍 انتخاب کشور:", reply_markup=InlineKeyboardMarkup(btns))

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    buttons = [[InlineKeyboardButton(s.capitalize(), callback_data=f"site_{s}")] for s in COUNTRIES]
    await q.edit_message_text("🌐 انتخاب سرویس:", reply_markup=InlineKeyboardMarkup(buttons))

async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id
    await q.answer("جستجو لغو شد")
    cancel_flags.add(user_id)
    valid_numbers[user_id] = []
    for t in search_tasks.get(user_id, []):
        t.cancel()
    search_tasks.pop(user_id, None)
    await q.edit_message_text("🚫 جستجو لغو شد.")

async def search_number(user_id, chat_id, msg_id, code, site, context):
    async def delayed_cancel(id_):
        await asyncio.sleep(122)
        if id_ not in [v[0] for v in valid_numbers.get(user_id, [])]:
            await cancel_number(site, id_)

    while user_id not in cancel_flags:
        limit = 1 if site in ["24sms7", "tiger"] else 5
        if len(valid_numbers.get(user_id, [])) >= limit:
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
                chat_id, f"📱 شماره سالم: <code>{number}</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📩 دریافت کد", callback_data=f"checkcode_{id_}")],
                    [InlineKeyboardButton("❌ لغو شماره", callback_data=f"cancel_{id_}")],
                    [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")]
                ])
            )
            valid_numbers.setdefault(user_id, []).append((id_, site, number, msg.message_id))
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
            asyncio.create_task(delayed_cancel(id_))
        await asyncio.sleep(1)

    if user_id in cancel_flags:
        cancel_flags.remove(user_id)
        await context.bot.edit_message_text("🚫 جستجو لغو شد.", chat_id=chat_id, message_id=msg_id)

async def auto_check_code(user_id, chat_id, msg_id, id_, site, number, context):
    while True:
        await asyncio.sleep(1)
        resp = await get_code(site, id_)
        if resp.startswith("STATUS_OK:"):
            code = resp[len("STATUS_OK:"):].strip()
            await context.bot.edit_message_text(
                f"📩 کد برای شماره `{number}` دریافت شد:\n`{code}`",
                chat_id=chat_id, message_id=msg_id, parse_mode=ParseMode.HTML
            )
            return

async def dynamic_check_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user_id = q.from_user.id
    await q.answer()
    data = q.data
    if data.startswith("checkcode_"):
        id_ = data.split("_")[1]
        for rec in valid_numbers.get(user_id, []):
            if rec[0] == id_:
                site = rec[1]
                resp = await get_code(site, id_)
                if resp.startswith("STATUS_OK:"):
                    code = resp[len("STATUS_OK:"):].strip()
                    await q.edit_message_text(
                        f"📩 کد برای شماره `{rec[2]}` دریافت شد:\n`{code}`",
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await q.answer("⏳ هنوز کدی دریافت نشده.", show_alert=True)
                return
        await q.edit_message_text("❌ شماره پیدا نشد یا لغو شده است.")
    elif data.startswith("cancel_"):
        id_ = data.split("_")[1]
        new_list = []
        for rec in valid_numbers.get(user_id, []):
            if rec[0] == id_:
                await cancel_number(rec[1], id_)
                try:
                    await q.edit_message_text(
                        f"❌ شماره لغو شد: `{rec[2]}`",
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")]])
                    )
                except Exception as e:
                    logging.error(f"Error editing message: {e}")
            else:
                new_list.append(rec)
        valid_numbers[user_id] = new_list

async def web_handler(request): return web.Response(text="✅ Bot is Alive!")

async def start_webserver():
    app = web.Application()
    app.add_routes([web.get('/', web_handler)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

async def main():
    nest_asyncio.apply()
    await start_webserver()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(site_selected, pattern="^site_"))
    app.add_handler(CallbackQueryHandler(back_to_start, pattern="^back_to_start$"))
    app.add_handler(CallbackQueryHandler(country_selected, pattern="^country_"))
    app.add_handler(CallbackQueryHandler(cancel_search, pattern="^cancel_search$"))
    app.add_handler(CallbackQueryHandler(dynamic_check_code, pattern="^(checkcode_|cancel_)"))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
