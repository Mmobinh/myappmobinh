import asyncio

# ... (بقیه کدها همان است)

bad_numbers_message_id = {}  # user_id: message_id برای پیام شماره‌های خراب
bad_numbers_list = {}  # user_id: list of bad numbers

async def update_bad_numbers_message(user_id, chat_id, context):
    bads = bad_numbers_list.get(user_id, [])
    if not bads:
        # اگر لیست خراب‌ها خالی شد، پیام رو حذف یا تغییر بده
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
            await context.bot.edit_message_text(text, chat_id=chat_id, message_id=bad_numbers_message_id[user_id])
        except:
            pass
    else:
        msg = await context.bot.send_message(chat_id=chat_id, text=text)
        bad_numbers_message_id[user_id] = msg.message_id

async def search_number(user_id, chat_id, msg_id, code, site, context):
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
            # شماره خراب رو تو لیست خراب‌ها اضافه کن و پیامش رو آپدیت کن
            bad_numbers_list.setdefault(user_id, []).append(number)
            await update_bad_numbers_message(user_id, chat_id, context)
            # لغو کن شماره
            await cancel_number(site, activation_id)
            await context.bot.edit_message_text(f"❌ شماره {number} ناسالم بود، جستجو ادامه دارد...", chat_id=chat_id, message_id=msg_id)
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
