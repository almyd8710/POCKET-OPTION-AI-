import logging
import asyncio
import traceback
import yfinance as yf
import ta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

# إعدادات التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# معرف المطور الوحيد
ADMIN_ID = 6964741705

# إدارة المستخدمين
approved_users = set()
pending_users = {}
rejected_users = set()

# أزواج العملات المدعومة
symbols = {
    "EURUSD=X": "EUR/USD OTC",
    "EURCHF=X": "EUR/CHF OTC",
    "EURTRY=X": "EUR/TRY OTC",
    "EURJPY=X": "EUR/JPY OTC",
    "EURAUD=X": "EUR/AUD OTC",
    "EURCAD=X": "EUR/CAD OTC"
}

# لوحة الأزرار لاختيار الأزواج
def get_keyboard():
    keyboard = [[InlineKeyboardButton(name, callback_data=sym)] for sym, name in symbols.items()]
    keyboard.append([InlineKeyboardButton("📋 قائمة الطلبات", callback_data="show_requests")])
    return InlineKeyboardMarkup(keyboard)

# تحليل المؤشرات والتوصية
def analyze(symbol):
    df = yf.download(tickers=symbol, interval="1m", period="1d")

    if df.empty:
        return "❌ لا توجد بيانات من السوق."

    df = df.tail(min(len(df), 50))
    df['ema20'] = ta.trend.EMAIndicator(df['Close'], window=min(20, len(df))).ema_indicator()
    df['ema50'] = ta.trend.EMAIndicator(df['Close'], window=min(50, len(df))).ema_indicator()
    df['rsi'] = ta.momentum.RSIIndicator(df['Close']).rsi()
    bb = ta.volatility.BollingerBands(df['Close'])
    df['bb_high'] = bb.bollinger_hband()
    df['bb_low'] = bb.bollinger_lband()

    latest = df.iloc[-1]
    ema20 = latest['ema20']
    ema50 = latest['ema50']
    rsi = latest['rsi']
    close = latest['Close']
    bb_high = latest['bb_high']
    bb_low = latest['bb_low']

    trend = "صاعد ✅" if ema20 > ema50 else "هابط ❌"
    rsi_status = "✅ منطقة تداول طبيعية" if rsi < 70 else "❌ منطقة تشبع"

    if close > bb_high:
        bb_status = "فوق الحد العلوي"
    elif close < bb_low:
        bb_status = "تحت الحد السفلي"
    else:
        bb_status = "داخل النطاق"

    if ema20 > ema50 and rsi < 70 and close > bb_high:
        signal = "شراء ✅"
    elif ema20 < ema50 and rsi > 30 and close < bb_low:
        signal = "بيع ❌"
    else:
        signal = "انتظار 🟡"

    return f"""
🔹 EMA:
- EMA20 = {ema20:.4f}
- EMA50 = {ema50:.4f}
📈 الاتجاه: {trend}

🔸 RSI = {rsi:.2f}
{rsi_status}

🔻 Bollinger Bands: {bb_status}

📌 التوصية: {signal}

📚 شرح المؤشرات:
- EMA20 > EMA50 → صعود
- RSI < 70 → غير مشبع
- Bollinger → يعطي احتمالات الانعكاس
""".strip()

# /start - التحقق من المستخدم
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in rejected_users:
        await update.message.reply_text("❌ تم رفض طلبك مسبقًا. أرسل 'طلب جديد' لإعادة التقديم.")
        return

    if user_id != ADMIN_ID and user_id not in approved_users:
        if user_id not in pending_users:
            pending_users[user_id] = update.effective_user.full_name
            await update.message.reply_text("🔐 حسابك قيد المراجعة من قبل المطور.")
            await context.bot.send_message(ADMIN_ID,
                f"🆕 طلب جديد من المستخدم:\n👤 الاسم: {update.effective_user.full_name}\n🆔 ID: {user_id}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ قبول", callback_data=f"approve_{user_id}"),
                     InlineKeyboardButton("❌ رفض", callback_data=f"reject_{user_id}")]
                ])
            )
        else:
            await update.message.reply_text("⌛ طلبك قيد الانتظار...")
        return

    await update.message.reply_text("👋 اختر زوج العملة لبدء التوصيات:", reply_markup=get_keyboard())

# تغيير الأزواج يدويًا
async def change_pairs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID and user_id not in approved_users:
        await update.message.reply_text("❌ لا تملك صلاحية استخدام هذا الأمر.")
        return
    await update.message.reply_text("🔁 اختر زوجًا جديدًا:", reply_markup=get_keyboard())

# عند الضغط على زر زوج معين
async def handle_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    symbol = query.data
    await query.answer()

    if user_id != ADMIN_ID and user_id not in approved_users:
        await query.message.reply_text("❌ غير مصرح لك باستخدام البوت.")
        return

    await query.message.reply_text("⏳ جاري تحليل السوق...")
    analysis = analyze(symbol)
    await query.message.reply_text(analysis)

    async def periodic():
        while True:
            signal = analyze(symbol)
            if signal:
                await context.bot.send_message(chat_id=query.message.chat_id, text=signal)
            await asyncio.sleep(60)

    context.application.create_task(periodic())

# معالجة الطلبات من المطور
async def handle_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if query.from_user.id != ADMIN_ID:
        await query.answer("❌ ليس لديك صلاحية.")
        return

    if data == "show_requests":
        if not pending_users:
            await query.message.reply_text("✅ لا توجد طلبات حاليًا.")
        else:
            text = "\n".join([f"{name} | ID: `{uid}`" for uid, name in pending_users.items()])
            await query.message.reply_text(f"📋 الطلبات:\n{text}", parse_mode="Markdown")
        return

    if data.startswith("approve_"):
        uid = int(data.split("_")[1])
        if uid in pending_users:
            approved_users.add(uid)
            del pending_users[uid]
            await context.bot.send_message(uid, "✅ تم قبولك. أرسل /start للبدء.")
            await query.answer("تم قبول المستخدم.")
        return

    if data.startswith("reject_"):
        uid = int(data.split("_")[1])
        if uid in pending_users:
            rejected_users.add(uid)
            del pending_users[uid]
            await context.bot.send_message(uid, "❌ تم رفض طلبك. أرسل 'طلب جديد' لإعادة التقديم.")
            await query.answer("تم الرفض.")
        return

# عند إرسال "طلب جديد"
async def new_request_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    if user_id in rejected_users and text.lower() == "طلب جديد":
        await context.bot.send_message(
            ADMIN_ID,
            f"📩 طلب جديد من مستخدم مرفوض:\n👤 الاسم: {update.effective_user.full_name}\n🆔 ID: {user_id}\n📨 الرسالة:\n{text}"
        )
        await update.message.reply_text("✅ تم إرسال طلبك للمطور.")

# معالجة الأخطاء
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error(msg="Exception occurred:", exc_info=context.error)
    tb = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    await context.bot.send_message(ADMIN_ID, f"❌ خطأ:\n{tb[:4000]}")

# تشغيل البوت
app = ApplicationBuilder().token("7728605631:AAFPOZ8ni818s5LspoEUyXH2jrTApK9J_9s").build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("change", change_pairs))
app.add_handler(CallbackQueryHandler(handle_requests, pattern="^(show_requests|approve_|reject_)"))
app.add_handler(CallbackQueryHandler(handle_selection, pattern="^(" + "|".join(symbols.keys()) + ")$"))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), new_request_message))
app.add_error_handler(error_handler)

app.run_polling()
