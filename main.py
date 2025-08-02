import os
import logging
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler
)

logging.basicConfig(level=logging.INFO)

CHECKER_API_KEY = os.getenv("CHECKER_API_KEY")
SMSBOWER_API_KEY = os.getenv("SMSBOWER_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

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

CHOOSING, CANCELLED = range(2)

async def check_valid(numbers):
    url = "http://checker.irbots.com:2021/check"
    if isinstance(numbers, list):
        numbers_str = ",".join(numbers)
    else:
        numbers_str = numbers

    params = {
        "key": CHECKER_API_KEY,
        "numbers": numbers_str
    }

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logging.error(f"Checker API returned status code {resp.status}")
                    return {num: False for num in numbers_str.split(",")}

                resp_json = await resp.json()

                if resp_json.get("status") != "ok":
                    logging.error(f"Checker API error: {resp_json.get('msg', 'No message')}")
                    return {num: False for num in numbers_str.split(",")}

                results = resp_json.get("data", {})
                final_results = {}

                for num in numbers_str.split(","):
                    val = results.get(num)
                    if val is True:
                        final_results[num] = True
                    else:
                        final_results[num] = False

                return final_results

    except Exception as e:
        logging.error(f"Exception in check_valid: {e}")
        return {num: False for num in numbers_str.split(",")}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(country, callback_data=str(code))]
        for country, code in COUNTRIES_SMSBOWER.items() if code != 0
    ]
    keyboard.append([InlineKeyboardButton("لغو جستجو", callback_data="cancel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("یک کشور را انتخاب کنید:", reply_markup=reply_markup)
    return CHOOSING


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancel":
        await query.edit_message_text("جستجو لغو شد.")
        return CANCELLED

    country_code = int(data)
    await query.edit_message_text(f"در حال دریافت شماره از کشور با کد {country_code}...")

    phone_numbers = []
    max_tries = 10
    for _ in range(max_tries):
        number = await get_phone_number(country_code)
        if not number:
            continue
        phone_numbers.append(number)
        break

    if not phone_numbers:
        await query.edit_message_text("شماره سالم پیدا نشد، دوباره تلاش کنید یا لغو کنید.")
        return CHOOSING

    checked = await check_valid(phone_numbers)

    text = ""
    for num, valid in checked.items():
        if valid:
            text += f"✅ شماره سالم: {num}\n"
        else:
            text += f"❌ شماره خراب: {num}\n"

    await query.edit_message_text(text)
    return CHOOSING


async def get_phone_number(country_code):
    url = (
        f"https://smsbower.online/stubs/handler_api.php?"
        f"api_key={SMSBOWER_API_KEY}&action=getNumber&service=tg&country={country_code}&maxPrice=58.67"
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                text = await resp.text()
                if text.startswith("ACCESS_NUMBER:"):
                    number = text.split(":")[1].strip()
                    return number
                else:
                    return None
    except Exception as e:
        logging.error(f"Error getting phone number: {e}")
        return None


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("جستجو لغو شد.")
    return CANCELLED


def main():
    if not CHECKER_API_KEY or not SMSBOWER_API_KEY or not TELEGRAM_BOT_TOKEN:
        logging.error("Environment variables for API keys or bot token are missing!")
        return

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING: [CallbackQueryHandler(button_handler)],
            CANCELLED: [],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)

    app.run_polling()


if __name__ == "__main__":
    main()
