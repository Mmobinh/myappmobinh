import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
)

# === متغیرهای سراسری ===
user_sessions = {}            # user_id: (activation_id, site)
cancel_flags = set()          # user_id هایی که لغو کردن
bad_numbers_message_id = {}   # user_id: message_id پیام شماره‌های خراب
bad_numbers_list = {}         # user_id: [شماره‌های خراب]

# === لیست کشورها ===
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
    # جایگاه اضافی با مقدار 0
    "Country Slot 1": 0, "Country Slot 2": 0, "Country Slot 3": 0,
    "Country Slot 4": 0, "Country Slot 5": 0, "Country Slot 6": 0,
    "Country Slot 7": 0, "Country Slot 8": 0, "Country Slot 9": 0,
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
    # جایگاه اضافی با مقدار 0
    "Country Slot 1": 0, "Country Slot 2": 0, "Country Slot 3": 0,
    "Country Slot 4": 0, "Country Slot 5": 0, "Country Slot 6": 0,
    "Country Slot 7": 0, "Country Slot 8": 0, "Country Slot 9": 0,
    "Country Slot 10": 0,
}

# === توابع کمکی (باید با API واقعی جایگزین بشن) ===

async def get_number_24sms7(api_key):
    # TODO: فراخوانی API 24sms7 و دریافت شماره
    # فرضی:
    # "ACCESS_NUMBER:id:number"
    # یا پیام خطا مثل "NO_NUMBER"
    return "ACCESS_NUMBER:123456:989121234567"

async def get_number_smsbower(api_key):
    # TODO: فراخوانی API smsbower و دریافت شماره
    return "ACCESS_NUMBER:654321:989121234568"

async def check_valid(number):
    # چکر شماره (مثال):
    return number.startswith("98") and len(number) == 12

async def cancel_number(site, activation_id, api_key):
    # لغو شماره فعال شده در سایت مربوطه
    # TODO: درخواست لغو را به API ارسال کن
    pass

async def get_code(site, activation_id, api_key):
    # دریافت وضعیت کد از سایت (مثلاً از آدرس getStatus)
    # جواب می‌تواند:
    # STATUS_WAIT_CODE - منتظر کد هست
    # STATUS_OK:code - کد دریافت شده
    # STATUS_CANCEL - لغو شده
    # TODO: درخواست به API و پاسخ را برگردان
    return "STATUS_WAIT_CODE"


# === منطق اصلی جستجو شماره و دریافت کد ===

async def update_bad_numbers_message(user_id, chat_id, context: ContextTypes.DEFAULT_TYPE):
    bads = bad_numbers_list.get(user_id, [])
    if not bads:
        if user_id in bad_numbers_message_id:
            try:
                await context.bot.edit_message_text(
                    "❌ شماره خراب یافت نشد.",
                    chat_id=chat_id,
                    message_id=bad_numbers_message_id[user_id]
                )
            except:
                pass
        return
    text = "❌ شماره‌های خراب:\n" + "\n".join(bads)
    if user_id in bad_numbers_message_id:
        try:
            await context.bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=bad_numbers_message_id[user_id]
            )
        except:
            pass
    else:
        msg = await context.bot.send_message(chat_id=chat_id, text=text)
        bad_numbers_message_id[user_id] = msg.message_id


async def search_number(user_id, chat_id, msg_id, api_key, site, context: ContextTypes.DEFAULT_TYPE):
    bad_numbers_list[user_id] = []
    if user_id in bad_numbers_message_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=bad_numbers_message_id[user_id])
        except:
            pass
        bad_numbers_message_id.pop(user_id, None)

    while True:
        if user_id in cancel_flags:
            cancel_flags.remove(user_id)
            await context.bot.edit_message_text("🚫 جستجو لغو شد.", chat_id=chat_id, message_id=msg_id)
            return

        if site == "24sms7":
            resp = await get_number_24sms7(api_key)
        else:
            resp = await get_number_smsbower(api_key)

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
            bad_numbers_list.setdefault(user_id, []).append(number)
            await update_bad_numbers_message(user_id, chat_id, context)
            await cancel_number(site, activation_id, api_key)
            await context.bot.edit_message_text(f"❌ شماره {number} ناسالم بود، جستجو ادامه دارد...", chat_id=chat_id, message_id=msg_id)
            await asyncio.sleep(0.5)
            continue

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

        # دریافت خودکار کد تا 10 دقیقه هر 7 ثانیه
        for _ in range(85):
            if user_id in cancel_flags:
                cancel_flags.remove(user_id)
                await context.bot.edit_message_text("🚫 دریافت کد لغو شد.", chat_id=chat_id, message_id=msg_id)
                return

            status = await get_code(site, activation_id, api_key)
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


# === هندلرهای تلگرام ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("24SMS7", callback_data="site_24sms7"),
            InlineKeyboardButton("SMSBOWER", callback_data="site_smsbower"),
        ]
    ]
    await update.message.reply_text("لطفا سایت مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    await query.answer()

    data = query.data

    if data == "cancel_search":
        cancel_flags.add(user_id)
        await query.edit_message_text("🚫 جستجو لغو شد.")
        return

    if data.startswith("site_"):
        site = data.split("_")[1]
        api_key = "YOUR_API_KEY_HERE"  # توکن واقعی را اینجا قرار بده

        # پیام اولیه جستجو
        msg = await query.edit_message_text("⏳ در حال جستجوی شماره سالم...")
        asyncio.create_task(search_number(user_id, chat_id, msg.message_id, api_key, site, context))
        return

    if data == "check_code":
        if user_id not in user_sessions:
            await query.edit_message_text("⚠️ ابتدا شماره دریافت کنید.")
            return
        activation_id, site = user_sessions[user_id]
        api_key = "YOUR_API_KEY_HERE"  # توکن واقعی

        status = await get_code(site, activation_id, api_key)
        if status.startswith("STATUS_OK"):
            code = status.split(":")[1]
            await query.edit_message_text(f"📩 کد دریافت شده:\n`{code}`", parse_mode="Markdown")
        else:
            await query.edit_message_text("⌛️ هنوز کدی دریافت نشده، صبر کنید یا لغو کنید.")
        return

    if data == "cancel_number":
        if user_id not in user_sessions:
            await query.edit_message_text("⚠️ شماره فعال شده‌ای برای لغو وجود ندارد.")
            return
        activation_id, site = user_sessions.pop(user_id)
        api_key = "YOUR_API_KEY_HERE"
        await cancel_number(site, activation_id, api_key)
        await query.edit_message_text("❌ شماره لغو شد.")
        return

async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cancel_flags.add(user_id)
    await update.message.reply_text("🚫 در صورت انجام جستجو، لغو خواهد شد.")

# === اجرای برنامه ===

def main():
    TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cancel", cancel_search))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("Bot started...")
    application.run_polling()

if __name__ == "__main__":
    main()
