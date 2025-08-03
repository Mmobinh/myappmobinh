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
SERVICE = "tg"

COUNTRIES_24SMS7 = {
    "Iran": 57,
    "Russia": 0,
}

COUNTRIES_SMSBOWER = {
    "Kazakhstan": 2,
}

user_sessions = {}
search_tasks = {}
cancel_flags = set()

async def get_number_24sms7(code):
    url = f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getNumber&service={SERVICE}&country={code}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def get_number_smsbower(code):
    url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getNumber&service={SERVICE}&country={code}&maxPrice=58.67"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def get_code(site, id_):
    url = {
        "24sms7": f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getStatus&id={id_}",
        "smsbower": f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getStatus&id={id_}",
    }[site]
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()

async def cancel_number(site, id_):
    url = {
        "24sms7": f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=setStatus&status=8&id={id_}",
        "smsbower": f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=setStatus&status=8&id={id_}",
    }[site]
    async with aiohttp.ClientSession() as s:
        await s.get(url)

async def check_valid(number):
    url = "http://checker.irbots.com:2021/check"
    params = {
        "key": CHECKER_API_KEY,
        "numbers": number.strip("+")
    }
    async with aiohttp.ClientSession() as s:
        async with s.get(url, params=params) as r:
            if r.status == 200:
                data = await r.json()
                return data.get("data", {}).get(f"+{number.strip('+')}", False)
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
    buttons = [[InlineKeyboardButton(name, callback_data=f"country_{site}_{id_}")] for name, id_ in countries.items()]
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_start")])
    await query.edit_message_text("🌍 انتخاب کشور:", reply_markup=InlineKeyboardMarkup(buttons))

async def back_to_sites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await site_selected(update, context)

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await start(update, context)

async def country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, site, code = query.data.split("_")
    user_id = query.from_user.id
    cancel_flags.discard(user_id)
    msg = await query.edit_message_text("⏳ در حال جستجو...", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ کنسل جستجو", callback_data="cancel_search")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_sites")]
    ]))
    search_count = 5 if site == "smsbower" else 1
    for _ in range(search_count):
        asyncio.create_task(search_number(user_id, query.message.chat_id, code, site, context))

async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cancel_flags.add(query.from_user.id)

async def cancel_number_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session_id = query.data.split("|")[1]
    user_id = query.from_user.id
    if user_id in user_sessions:
        for sid, (id_, site) in user_sessions[user_id].items():
            if sid == session_id:
                await cancel_number(site, id_)
                del user_sessions[user_id][sid]
                await query.edit_message_text("❌ شماره لغو شد.")
                return

async def check_code_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    session_id = query.data.split("|")[1]
    user_id = query.from_user.id
    if user_id in user_sessions and session_id in user_sessions[user_id]:
        id_, site = user_sessions[user_id][session_id]
        resp = await get_code(site, id_)
        if resp.startswith("STATUS_OK:"):
            code = resp[len("STATUS_OK:"):].strip()
            await query.answer(f"📩 کد:\n{code}", show_alert=True)
        elif resp == "STATUS_WAIT_CODE":
            await query.answer("⏳ هنوز کدی دریافت نشده.", show_alert=True)
        else:
            await query.answer("❌ خطا در دریافت کد.", show_alert=True)

async def search_number(user_id, chat_id, code, site, context):
    session_id = os.urandom(4).hex()
    while True:
        if user_id in cancel_flags:
            return
        resp = await (get_number_24sms7(code) if site == "24sms7" else get_number_smsbower(code))
        if not resp.startswith("ACCESS_NUMBER"):
            await asyncio.sleep(1)
            continue
        _, id_, number = resp.split(":")[:3]
        number = f"+{number}"
        if await check_valid(number):
            user_sessions.setdefault(user_id, {})[session_id] = (id_, site)
            buttons = [
                [InlineKeyboardButton("📩 دریافت کد", callback_data=f"checkcode|{session_id}")],
                [InlineKeyboardButton("❌ لغو شماره", callback_data=f"cancel_number|{session_id}")]
            ]
            msg = await context.bot.send_message(
                chat_id, f"📱 شماره سالم: <code>{number}</code>",
                parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons)
            )
            asyncio.create_task(auto_check_code(user_id, msg.chat.id, msg.message_id, id_, site, number, context, session_id))
            return
        else:
            asyncio.create_task(cancel_number(site, id_))
        await asyncio.sleep(1)

async def auto_check_code(user_id, chat_id, msg_id, id_, site, number, context, session_id):
    for _ in range(60):
        await asyncio.sleep(1)
        if user_id not in user_sessions or session_id not in user_sessions[user_id]:
            return
        resp = await get_code(site, id_)
        if resp.startswith("STATUS_OK:"):
            code = resp[len("STATUS_OK:"):].strip()
            await context.bot.edit_message_text(
                f"✅ کد برای شماره <code>{number}</code> دریافت شد:\n<code>{code}</code>",
                chat_id=chat_id, message_id=msg_id, parse_mode=ParseMode.HTML
            )
            return

async def web_handler(request):
    return web.Response(text="✅ Bot is Alive!")

async def start_webserver():
    app = web.Application()
    app.add_routes([web.get('/', web_handler)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

async def main():
    await start_webserver()
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(site_selected, pattern="^site_"))
    application.add_handler(CallbackQueryHandler(country_selected, pattern="^country_"))
    application.add_handler(CallbackQueryHandler(cancel_search, pattern="^cancel_search$"))
    application.add_handler(CallbackQueryHandler(cancel_number_callback, pattern="^cancel_number\|"))
    application.add_handler(CallbackQueryHandler(check_code_callback, pattern="^checkcode\|"))
    application.add_handler(CallbackQueryHandler(back_to_start, pattern="^back_to_start$"))
    application.add_handler(CallbackQueryHandler(back_to_sites, pattern="^back_to_sites$"))
    print("✅ Bot is running...")
    await application.run_polling()

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())
