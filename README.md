# 🎬 TZTVN Cinema Bot

بوت ذكاء اصطناعي سينمائي لمنصة TZTVN على تيليجرام.

## ✅ الميزات:
- 🤖 ذكاء اصطناعي Groq (llama-3.3-70b)
- 🔍 بحث حقيقي عن الأفلام عبر TMDb API
- 📅 يخبرك هل الفيلم نزل أم لا
- ⭐ تقييمات وتواريخ إصدار حقيقية
- 🛡️ فلتر كلمات محظورة
- 🟢 متوافق مع UptimeRobot (لا ينام)

## 📋 الأوامر:
- /start  - بدء المحادثة
- /search - بحث مباشر عن فيلم (/search Dune)
- /reset  - مسح تاريخ المحادثة

## 🚀 الرفع على Render:
1. ارفع الملفات على GitHub (Private)
2. Render → New → Background Worker
3. ربط GitHub → Start Command: python tztvn_bot.py
4. Deploy ✅

## 🟢 إعداد UptimeRobot:
1. uptimerobot.com → Add Monitor
2. النوع: HTTP(s)
3. الرابط: https://YOUR-APP.onrender.com
4. Interval: 5 دقائق
5. حفظ ✅ البوت لن ينام!

## 📝 ملاحظات:
- البوت يرد فقط عند ذكر @tztvn في المجموعات
- في الخاص يرد على كل شيء
- يحفظ آخر 20 رسالة للسياق
