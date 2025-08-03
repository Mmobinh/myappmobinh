import os  
import asyncio  
import logging  
import nest_asyncio  
import aiohttp  
import re
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
  
user_sessions = {}  
search_tasks = {}  
cancel_flags = set()  
  
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
                status = data.get("status")  
                if status == "ok":  
                    result = data.get("data", {}).get(f"+{number.strip('+')}", False)  
                    return result is True  
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
    buttons = [  
        [InlineKeyboardButton(name, callback_data=f"country_{site}_{id_}")]  
        for name, id_ in countries.items()  
    ]  
    await query.edit_message_text("🌍 انتخاب کشور:", reply_markup=InlineKeyboardMarkup(buttons))  
  
async def country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):  
    query = update.callback_query  
    await query.answer()  
    _, site, code = query.data.split("_")  
    user_id = query.from_user.id  
    cancel_flags.discard(user_id)  
    msg = await query.edit_message_text("⏳ جستجو برای شماره سالم...")  
    task = asyncio.create_task(search_number(user_id, query.message.chat_id, msg.message_id, code, site, context))  
    search_tasks[user_id] = task  
  
async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):  
    query = update.callback_query  
    await query.answer()  
    user_id = query.from_user.id  
    cancel_flags.add(user_id)  
  
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
        await query.edit_message_text("❌ شماره‌ای برای لغو نیست.")  
  
async def check_code_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):  
    query = update.callback_query  
    user_id = query.from_user.id  
    if user_id not in user_sessions:  
        await query.answer("❌ شماره‌ای فعال نیست.", show_alert=True)  
        return  
    id_, site = user_sessions[user_id]  
    resp = await get_code(site, id_)  
    if resp.startswith("STATUS_OK:"):  
        code = resp[len("STATUS_OK:"):].strip()  
        number = "نامشخص"
        for uid, (uid_id, _) in user_sessions.items():
            if uid == user_id:
                number = f"+{uid_id}"
        await query.answer(f"📩 کد برای شماره {number} دریافت شد:\n{code}", show_alert=True)  
    elif resp == "STATUS_WAIT_CODE":  
        await query.answer("⏳ هنوز کدی دریافت نشده.", show_alert=True)  
    else:  
        await query.answer("❌ خطا در دریافت کد.", show_alert=True)  
  
async def search_number(user_id, chat_id, msg_id, code, site, context):  
    while True:  
        if user_id in cancel_flags:  
            cancel_flags.remove(user_id)  
            await context.bot.edit_message_text("🚫 جستجو لغو شد.", chat_id=chat_id, message_id=msg_id)  
            return  
        resp = await (get_number_24sms7(code) if site == "24sms7" else get_number_smsbower(code))  
        if not resp.startswith("ACCESS_NUMBER"):  
            await asyncio.sleep(1)  # افزایش سرعت  
            continue  
        _, id_, number = resp.split(":")[:3]  
        number = f"+{number}"  
        valid = await check_valid(number)  
        if valid:  
            user_sessions[user_id] = (id_, site)  
            buttons = [  
                [InlineKeyboardButton("📩 دریافت کد", callback_data="checkcode")],  
                [InlineKeyboardButton("❌ لغو شماره", callback_data="cancel_number")]  
            ]  
            await context.bot.edit_message_text(  
                f"📱 شماره سالم: <code>{number}</code>", chat_id=chat_id,  
                message_id=msg_id, parse_mode=ParseMode.HTML,  
                reply_markup=InlineKeyboardMarkup(buttons)  
            )  
            asyncio.create_task(auto_check_code(user_id, chat_id, msg_id, id_, site, number, context))  
            return  
        else:  
            await context.bot.edit_message_text(  
                f"❌ شماره ناسالم: <code>{number}</code>\n🔄 در حال جستجو برای شماره سالم...",  
                chat_id=chat_id, message_id=msg_id, parse_mode=ParseMode.HTML  
            )  
            await cancel_number(site, id_)  
        await asyncio.sleep(1)  # افزایش سرعت  
  
async def auto_check_code(user_id, chat_id, msg_id, id_, site, number, context):  
    while True:  
        await asyncio.sleep(1)  
        if user_id not in user_sessions:  
            return  
        resp = await get_code(site, id_)  
        if resp.startswith("STATUS_OK:"):  
            code = resp[len("STATUS_OK:"):].strip()  
            await context.bot.edit_message_text(  
                f"📩 کد برای شماره <code>{number}</code> دریافت شد:\n<code>{code}</code>",  
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
    application.add_handler(CallbackQueryHandler(cancel_number_callback, pattern="^cancel_number$"))  
    application.add_handler(CallbackQueryHandler(check_code_callback, pattern="^checkcode$"))  
    print("✅ Bot is running...")  
    await application.run_polling()  
  
if __name__ == "__main__":  
    nest_asyncio.apply()  
    loop = asyncio.get_event_loop()  
    loop.create_task(main())  
    loop.run_forever()
