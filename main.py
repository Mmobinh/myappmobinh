#!/usr/bin/env python3
# coding: utf-8

import os
import asyncio
import logging
import nest_asyncio
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from aiohttp import web

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY_SMSBOWER = os.getenv("API_KEY_SMSBOWER")
CHECKER_API_KEY = os.getenv("CHECKER_API_KEY")
SERVICE = "tg"

# only smsbower
COUNTRIES = {
    "smsbower": {
        "Kazakhstan": 2, "Iran": 57, "Russia": 0, "Ukraine": 1, "Mexico": 54, "Italy": 86,
        "Spain": 56, "Czech Republic": 63, "Paraguay": 87, "Hong Kong": 14, "macao": 20,
        "irland": 23, "serbia": 29, "romani": 32, "estonia": 34, "germany": 43,
        "auustria": 50, "belarus": 51, "tiwan": 55, "newziland": 67, "belgium": 82,
        "moldova": 85, "armenia": 148, "maldiv": 159, "guadlouap": 160, "denmark": 172,
        "norway": 174, "switzerland": 173, "giblarator": 201
    }
}

MAX_PARALLEL_REQUESTS = {"smsbower": 5}

# runtime state
user_sessions = {}
search_tasks = {}
cancel_flags = set()
valid_numbers = {}

# --- HTTP helper ---
async def fetch_url(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as response:
                return await response.text()
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logging.error(f"Error fetching URL {url}: {e}")
        return "ERROR"

# --- smsbower endpoints (only) ---
async def get_number_smb(code):
    url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getNumber&service={SERVICE}&country={code}&providerIds=2285phoneException=7700,7708"
    return await fetch_url(url)

async def get_code_smb(id_):
    url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getStatus&id={id_}"
    return await fetch_url(url)

async def cancel_number_smb(id_):
    url = f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=setStatus&status=8&id={id_}"
    await fetch_url(url)

# --- checker for number validity (external) ---
async def check_valid(number):
    # expects number like +123456789
    if not CHECKER_API_KEY:
        # if no checker provided, assume valid to let flow continue (or you can change to False)
        logging.warning("No CHECKER_API_KEY set — assuming numbers are valid by default.")
        return True
    url = "http://checker.irbots.com:2021/check"
    params = {"key": CHECKER_API_KEY, "numbers": number.strip("+")}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=20) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("status") == "ok" and data["data"].get(f"+{number.strip('+')}", False) is True
    except Exception as e:
        logging.error(f"Checker request failed: {e}")
    return False

# --- Telegram handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # directly show countries (only smsbower)
    countries = COUNTRIES["smsbower"]
    country_buttons = [InlineKeyboardButton(name, callback_data=f"country_{id_}") for name, id_ in countries.items()]
    buttons = chunk_buttons(country_buttons, 3)
    buttons.append([InlineKeyboardButton("❌ لغو همه جستجوها", callback_data="global_cancel")])
    await update.message.reply_text("🌍 انتخاب کشور (smsbower):", reply_markup=InlineKeyboardMarkup(buttons))

def chunk_buttons(button_list, n):
    return [button_list[i:i + n] for i in range(0, len(button_list), n)]

async def country_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    cancel_flags.discard(user_id)
    valid_numbers[user_id] = []
    _, code = query.data.split("_")
    msg = await query.edit_message_text("⏳ در حال جستجو برای شماره سالم...", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ کنسل جستجو", callback_data="cancel_search")],
        [InlineKeyboardButton("🔙 بازگشت به کشورها", callback_data="back_to_countries")]
    ]))
    max_requests = MAX_PARALLEL_REQUESTS.get("smsbower", 1)
    tasks = [asyncio.create_task(search_number(user_id, query.message.chat_id, msg.message_id, code, context)) for _ in range(max_requests)]
    search_tasks[user_id] = tasks

async def back_to_countries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    countries = COUNTRIES["smsbower"]
    country_buttons = [InlineKeyboardButton(name, callback_data=f"country_{id_}") for name, id_ in countries.items()]
    buttons = chunk_buttons(country_buttons, 3)
    buttons.append([InlineKeyboardButton("❌ لغو همه جستجوها", callback_data="global_cancel")])
    await query.edit_message_text("🌍 انتخاب کشور (smsbower):", reply_markup=InlineKeyboardMarkup(buttons))

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
    await query.edit_message_text("🚫 جستجو لغو شد.", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت به کشورها", callback_data="back_to_countries")]
    ]))

async def global_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("لغو همه جستجوها")
    # cancel all users' tasks
    for uid, tasks in list(search_tasks.items()):
        for t in tasks:
            t.cancel()
        search_tasks.pop(uid, None)
        cancel_flags.add(uid)
        valid_numbers[uid] = []
    await query.edit_message_text("🚫 همه جستجوها لغو شد.", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت به کشورها", callback_data="back_to_countries")]
    ]))

# the main search loop for smsbower
async def search_number(user_id, chat_id, msg_id, code, context):
    async def delayed_cancel(id_):
        await asyncio.sleep(122)
        active_ids = [i[0] for i in valid_numbers.get(user_id, [])]
        if id_ not in active_ids:
            await cancel_number_smb(id_)

    while user_id not in cancel_flags:
        # limit quantities per user (smsbower up to 5)
        if len(valid_numbers.get(user_id, [])) >= MAX_PARALLEL_REQUESTS["smsbower"]:
            break
        resp = await get_number_smb(code)
        if not resp or not resp.startswith("ACCESS_NUMBER"):
            await asyncio.sleep(1)
            continue
        # format: ACCESS_NUMBER:ID:NUMBER
        parts = resp.split(":")
        if len(parts) < 3:
            await asyncio.sleep(1)
            continue
        _, id_, number = parts[:3]
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
                    [InlineKeyboardButton("🔙 بازگشت به کشورها", callback_data="back_to_countries")]
                ])
            )
            valid_numbers[user_id].append((id_, "smsbower", number, msg.message_id))
            # spawn background checker for this id
            asyncio.create_task(auto_check_code(user_id, chat_id, msg.message_id, id_, number, context))
        else:
            # mark as not valid and schedule delayed cancel
            try:
                await context.bot.edit_message_text(
                    f"❌ شماره ناسالم: <code>{number}</code>\n🔄 در حال جستجو برای شماره سالم...",
                    chat_id=chat_id, message_id=msg_id, parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("❌ کنسل جستجو", callback_data="cancel_search")],
                        [InlineKeyboardButton("🔙 بازگشت به کشورها", callback_data="back_to_countries")]
                    ])
                )
            except Exception as e:
                logging.error(f"Error editing message: {e}")
            asyncio.create_task(delayed_cancel(id_))
        await asyncio.sleep(1)

    if user_id in cancel_flags:
        cancel_flags.discard(user_id)
        try:
            await context.bot.edit_message_text("🚫 جستجو لغو شد.", chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass

async def auto_check_code(user_id, chat_id, msg_id, id_, number, context):
    while True:
        await asyncio.sleep(1)
        resp = await get_code_smb(id_)
        if resp.startswith("STATUS_OK:"):
            code = resp[len("STATUS_OK:"):].strip()
            try:
                await context.bot.edit_message_text(
                    f"📩 کد برای شماره <code>{number}</code> دریافت شد:\n<code>{code}</code>",
                    chat_id=chat_id, message_id=msg_id, parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 بازگشت به کشورها", callback_data="back_to_countries")]
                    ])
                )
            except Exception as e:
                logging.error(f"Error editing message with code: {e}")
            return
        elif resp == "STATUS_WAIT_CODE" or "STATUS_WAIT" in resp:
            # still waiting
            continue
        else:
            # unknown or error state; keep waiting or break depending on response
            await asyncio.sleep(1)

async def dynamic_check_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    id_ = query.data.split("_", 1)[1]
    for rec in valid_numbers.get(user_id, []):
        if rec[0] == id_:
            site, number, msg_id = rec[1], rec[2], rec[3]
            resp = await get_code_smb(id_)
            if resp.startswith("STATUS_OK:"):
                code = resp[len("STATUS_OK:"):].strip()
                try:
                    await context.bot.edit_message_text(
                        f"📩 کد برای شماره <code>{number}</code> دریافت شد:\n<code>{code}</code>",
                        chat_id=query.message.chat_id, message_id=msg_id, parse_mode=ParseMode.HTML,
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔙 بازگشت به کشورها", callback_data="back_to_countries")]
                        ])
                    )
                except Exception as e:
                    logging.error(f"Error editing message in dynamic_check_code: {e}")
            elif resp == "STATUS_WAIT_CODE":
                await query.answer("⏳ هنوز کدی دریافت نشده.", show_alert=True)
            else:
                await query.answer("❌ خطا در دریافت کد.", show_alert=True)
            break

async def dynamic_cancel_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    id_ = query.data.split("_", 1)[1]
    new_list = []
    for rec in valid_numbers.get(user_id, []):
        if rec[0] == id_:
            # cancel at provider
            await cancel_number_smb(rec[0])
            try:
                await context.bot.edit_message_text(
                    f"❌ شماره لغو شد: <code>{rec[2]}</code>",
                    chat_id=query.message.chat_id, message_id=rec[3], parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 بازگشت به کشورها", callback_data="back_to_countries")]
                    ])
                )
            except Exception as e:
                logging.error(f"Error editing message: {e}")
        else:
            new_list.append(rec)
    valid_numbers[user_id] = new_list

# --- simple web server for health check ---
async def web_handler(request):
    return web.Response(text="✅ Bot is Alive!")

async def start_webserver():
    app = web.Application()
    app.add_routes([web.get('/', web_handler)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

# --- main ---
async def main():
    await start_webserver()
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(country_selected, pattern="^country_"))
    application.add_handler(CallbackQueryHandler(back_to_countries, pattern="^back_to_countries$"))
    application.add_handler(CallbackQueryHandler(cancel_search, pattern="^cancel_search$"))
    application.add_handler(CallbackQueryHandler(global_cancel, pattern="^global_cancel$"))
    application.add_handler(CallbackQueryHandler(dynamic_check_code, pattern="^checkcode_"))
    application.add_handler(CallbackQueryHandler(dynamic_cancel_number, pattern="^cancel_"))
    await application.run_polling()

if __name__ == "__main__":
    nest_asyncio.apply()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")




