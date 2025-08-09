import os, asyncio, logging, nest_asyncio, aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from aiohttp import web
logging.basicConfig(level=logging.INFO)
BOT_TOKEN,API_KEY_24SMS7,API_KEY_SMSBOWER,API_KEY_TIGER,CHECKER_API_KEY=os.getenv("BOT_TOKEN"),os.getenv("API_KEY_24SMS7"),os.getenv("API_KEY_SMSBOWER"),os.getenv("API_KEY_TIGER"),os.getenv("CHECKER_API_KEY")
SERVICE="tg"
COUNTRIES={"24sms7":{"Iran":57,"Russia":0,"Ukraine":1,"Mexico":54,"Italy":86,"Spain":56,"Czech Republic":63,"Kazakhstan":2,"Paraguay":87,"Hong Kong":14,"macao":20,"irland":23,"serbia":29,"romani":32,"estonia":34,"germany":43,"auustria":50,"belarus":51,"tiwan":55,"newziland":67,"belgium":82,"moldova":85,"armenia":148,"maldiv":159,"guadlouap":160,"denmark":172,"norway":174,"switzerland":173,"giblarator":201},"smsbower":{"Kazakhstan":2,"Iran":57,"Russia":0,"Ukraine":1,"Mexico":54,"Italy":86,"Spain":56,"Czech Republic":63,"Paraguay":87,"Hong Kong":14,"macao":20,"irland":23,"serbia":29,"romani":32,"estonia":34,"germany":43,"auustria":50,"belarus":51,"tiwan":55,"newziland":67,"belgium":82,"moldova":85,"armenia":148,"maldiv":159,"guadlouap":160,"denmark":172,"norway":174,"switzerland":173,"giblarator":201},"tiger":{"Iran":57,"Russia":0,"Ukraine":1,"Mexico":54,"Italy":86,"Spain":56,"Czech Republic":63,"Kazakhstan":2,"Paraguay":87,"Hong Kong":14,"macao":20,"irland":23,"serbia":29,"romani":32,"estonia":34,"germany":43,"auustria":50,"belarus":51,"tiwan":55,"newziland":67,"belgium":82,"moldova":85,"armenia":148,"maldiv":159,"guadlouap":160,"denmark":172,"norway":174,"switzerland":173,"giblarator":201}}
MAX_PARALLEL_REQUESTS={"24sms7":1,"smsbower":5,"tiger":1}
user_sessions,search_tasks,cancel_flags,valid_numbers={}, {}, set(), {}
async def fetch_url(url):
    try:
        async with aiohttp.ClientSession() as s: async with s.get(url) as r: return await r.text()
    except aiohttp.ClientError as e: logging.error(f"Error fetching URL {url}: {e}"); return "ERROR"
async def get_number(site,code):
    urls={"24sms7":f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getNumber&service={SERVICE}&country={code}","smsbower":f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getNumber&service={SERVICE}&country={code}&phoneException=7700,7708","tiger":f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getNumber&service={SERVICE}&country={code}&maxPrice=25&providerIds=55,234,188"};return await fetch_url(urls.get(site,""))
async def get_code(site,id_): return await fetch_url({"24sms7":f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=getStatus&id={id_}","smsbower":f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=getStatus&id={id_}","tiger":f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=getStatus&id={id_}"}[site])
async def cancel_number(site,id_): await fetch_url({"24sms7":f"https://24sms7.com/stubs/handler_api.php?api_key={API_KEY_24SMS7}&action=setStatus&status=8&id={id_}","smsbower":f"https://smsbower.online/stubs/handler_api.php?api_key={API_KEY_SMSBOWER}&action=setStatus&status=8&id={id_}","tiger":f"https://api.tiger-sms.com/stubs/handler_api.php?api_key={API_KEY_TIGER}&action=setStatus&status=8&id={id_}"}[site])
async def check_valid(number):
    url="http://checker.irbots.com:2021/check";params={"key":CHECKER_API_KEY,"numbers":number.strip("+")}
    async with aiohttp.ClientSession() as s: async with s.get(url,params=params) as r:
        if r.status==200: d=await r.json(); return d.get("status")=="ok" and d["data"].get(f"+{number.strip('+')}",False) is True
        return False
async def start(update,context): await update.message.reply_text("🌐 انتخاب سرویس:",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(site.capitalize(),callback_data=f"site_{site}")] for site in COUNTRIES]))
def chunk_buttons(lst,n): return [lst[i:i+n] for i in range(0,len(lst),n)]
async def site_selected(update,context):
    q=update.callback_query;await q.answer();site=q.data.split("_")[1];c=COUNTRIES.get(site,{})
    btns=chunk_buttons([InlineKeyboardButton(k,callback_data=f"country_{site}_{v}") for k,v in c.items()],3);btns.append([InlineKeyboardButton("🔙 بازگشت",callback_data="back_to_start")])
    await q.edit_message_text("🌍 انتخاب کشور:",reply_markup=InlineKeyboardMarkup(btns))
async def back_to_start(update,context):
    q=update.callback_query;await q.answer()
    await q.edit_message_text("🌐 انتخاب سرویس:",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(site.capitalize(),callback_data=f"site_{site}")] for site in COUNTRIES]))
async def country_selected(update,context):
    q=update.callback_query;uid=q.from_user.id;cancel_flags.discard(uid);valid_numbers[uid]=[]
    _,site,code=q.data.split("_");msg=await q.edit_message_text("⏳ جستجو برای شماره سالم...",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ کنسل جستجو",callback_data="cancel_search")],[InlineKeyboardButton("🔙 بازگشت",callback_data="back_to_sites")]]))
    max_req=MAX_PARALLEL_REQUESTS.get(site,1);tasks=[asyncio.create_task(search_number(uid,q.message.chat_id,msg.message_id,code,site,context)) for _ in range(max_req)];search_tasks[uid]=tasks
async def cancel_search(update,context):
    q=update.callback_query;uid=q.from_user.id;await q.answer("جستجو لغو شد");cancel_flags.add(uid);valid_numbers[uid]=[];[t.cancel() for t in search_tasks.get(uid,[])];search_tasks.pop(uid,None)
    await q.edit_message_text("🚫 جستجو لغو شد.")
async def search_number(uid,cid,mid,code,site,context):
    async def delayed_cancel(id_,s_): await asyncio.sleep(122);active=[i[0] for i in valid_numbers.get(uid,[])]; 
    if id_ not in active: await cancel_number(s_,id_)
    while uid not in cancel_flags:
        if (site in ["24sms7","tiger"] and len(valid_numbers[uid])>=1) or (site=="smsbower" and len(valid_numbers[uid])>=5): break
        resp=await get_number(site,code)
        if not resp.startswith("ACCESS_NUMBER"): await asyncio.sleep(1);continue
        _,id_,num=resp.split(":")[:3];num=f"+{num}";valid=await check_valid(num)
        if valid:
            m=await context.bot.send_message(chat_id=cid,text=f"📱 شماره سالم: <code>{num}</code>",parse_mode=ParseMode.HTML,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📩 دریافت کد",callback_data=f"checkcode_{id_}")],[InlineKeyboardButton("❌ لغو شماره",callback_data=f"cancel_{id_}")],[InlineKeyboardButton("🔙 بازگشت",callback_data="back_to_sites")]]))
            valid_numbers[uid].append((id_,site,num,m.message_id));asyncio.create_task(auto_check_code(uid,cid,m.message_id,id_,site,num,context))
        else:
            await context.bot.edit_message_text(f"❌ شماره ناسالم: <code>{num}</code>\n🔄 در حال جستجو...",chat_id=cid,message_id=mid,parse_mode=ParseMode.HTML,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ کنسل جستجو",callback_data="cancel_search")],[InlineKeyboardButton("🔙 بازگشت",callback_data="back_to_sites")]]))
            asyncio.create_task(delayed_cancel(id_,site))
        await asyncio.sleep(1)
    if uid in cancel_flags: cancel_flags.discard(uid);await context.bot.edit_message_text("🚫 جستجو لغو شد.",chat_id=cid,message_id=mid)
async def auto_check_code(uid,cid,mid,id_,site,num,context):
    while True:
        await asyncio.sleep(1);resp=await get_code(site,id_)
        if resp.startswith("STATUS_OK:"):
            code=resp[len("STATUS_OK:"):].strip()
            await context.bot.edit_message_text(f"📩 کد برای شماره <code>{num}</code> دریافت شد:\n<code>{code}</code>",chat_id=cid,message_id=mid,parse_mode=ParseMode.HTML);return
async def dynamic_check_code(update,context):
    q=update.callback_query;uid=q.from_user.id;await q.answer();id_=q.data.split("_")[1]
    for rec in valid_numbers.get(uid,[]):
        if rec[0]==id_:
            site,num,mid=rec[1],rec[2],rec[3];resp=await get_code(site,id_)
            if resp.startswith("STATUS_OK:"):
                code=resp[len("STATUS_OK:"):].strip();await context.bot.edit_message_text(f"📩 کد برای شماره <code>{num}</code> دریافت شد:\n<code>{code}</code>",chat_id=q.message.chat_id,message_id=mid,parse_mode=ParseMode.HTML)
            elif resp=="STATUS_WAIT_CODE": await q.answer("⏳ هنوز کدی دریافت نشده.",show_alert=True)
            else: await q.answer("❌ خطا در دریافت کد.",show_alert=True)
            break
async def dynamic_cancel_number(update,context):
    q=update.callback_query;uid=q.from_user.id;await q.answer();id_=q.data.split("_")[1];new=[]
    for rec in valid_numbers.get(uid,[]):
        if rec[0]==id_:
            await cancel_number(rec[1],rec[0])
            try: await context.bot.edit_message_text(f"❌ شماره لغو شد: <code>{rec[2]}</code>",chat_id=q.message.chat_id,message_id=rec[3],parse_mode=ParseMode.HTML,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت",callback_data="back_to_sites")]]))
            except Exception as e: logging.error(f"Error editing message: {e}")
        else: new.append(rec)
    valid_numbers[uid]=new
async def web_handler(request): return web.Response(text="✅ Bot is Alive!")
async def start_webserver():
    app=web.Application();app.add_routes([web.get('/',web_handler)]);runner=web.AppRunner(app);await runner.setup();await web.TCPSite(runner,"0.0.0.0",8080).start()
async def main():
    await start_webserver();app=ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CallbackQueryHandler(site_selected,pattern="^site_"))
    app.add_handler(CallbackQueryHandler(back_to_start,pattern="^back_to_start$"))
    app.add_handler(CallbackQueryHandler(country_selected,pattern="^country_"))
    app.add_handler(CallbackQueryHandler(cancel_search,pattern="^cancel_search$"))
    app.add_handler(CallbackQueryHandler(dynamic_check_code,pattern="^checkcode_"))
    app.add_handler(CallbackQueryHandler(dynamic_cancel_number,pattern="^cancel_"))
    await app.run_polling()
if __name__=="__main__": nest_asyncio.apply();asyncio.run(main())
