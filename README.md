# Pocket Option AI Telegram Bot 🤖

بوت تيليجرام يرسل توصيات تداول باستخدام RSI و EMA و Bollinger Bands كل دقيقة.

## الأوامر:
- /start لبدء البوت واختيار الزوج
- /change لتغيير الزوج في أي وقت

## خطوات التشغيل على Render:
1. ارفع هذه الملفات إلى GitHub في مشروع جديد.
2. ادخل إلى https://render.com وسجّل الدخول.
3. اختر “New Web Service”.
4. اربط المشروع من GitHub.
5. استخدم:
   - Build Command: pip install -r requirements.txt
   - Start Command: python bot.py
6. لا تحتاج Webhook لأن البوت يستخدم long polling (آمن للخطة المجانية).
