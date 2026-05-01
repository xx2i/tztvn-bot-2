import logging
import threading
import time
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from groq import Groq

# ══════════════════════════════════════
#           الإعدادات الأساسية
# ══════════════════════════════════════
TELEGRAM_TOKEN = "8698916636:AAHMYHlwv8M5lcuQCc5uv-63jb92_jez-pA"
GROQ_API_KEY   = "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"
TMDB_API_KEY   = "25d84a7d8697acb8dc0dd0fd0660d234"
BOT_NAME       = "tztvn"
MODEL_NAME     = "llama-3.3-70b-versatile"

logging.basicConfig(level=logging.INFO)

# ══════════════════════════════════════
#   Web Server (للـ UptimeRobot)
# ══════════════════════════════════════
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"TZTVN Bot is alive!")
    def log_message(self, format, *args):
        pass  # أخفِ logs السيرفر

def run_server():
    server = HTTPServer(("0.0.0.0", 8080), PingHandler)
    server.serve_forever()

threading.Thread(target=run_server, daemon=True).start()

# ══════════════════════════════════════
#           System Prompt
# ══════════════════════════════════════
SYSTEM_PROMPT = """
أنت الذكاء الاصطناعي الرسمي، الحصري، والناطق باسم منصة "TZTVN" (المنصة الرائدة في عرض الأفلام والمسلسلات والوثائقيات للجمهور التونسي والعربي). أنت تعمل داخل مجموعة تيليجرام خاصة، ووظيفتك الأساسية هي النقاش، التوجيه، وتقديم التوصيات السينمائية لأعضاء المجموعة.

عليك الالتزام الصارم بالقواعد التالية في كل إجابة تقدمها، وبدون أي استثناءات:

1. هوية البوت والولاء:
- أنت لست مساعداً ذكياً عاماً. أنت "مساعد TZTVN السينمائي".
- إذا سُئلت "من أنت؟" تجيب بأنك الذكاء الاصطناعي لمنصة TZTVN.

2. حصرية المحتوى:
- نطاق حديثك يقتصر حصرياً على: الأفلام، المسلسلات، الأبطال، المخرجين، التقييمات السينمائية.
- إذا سألك أحد عن موضوع خارج السينما قل: "عذراً، أنا مبرمج حصرياً للحديث عن سحر السينما والأفلام عبر منصة TZTVN. هل تبحث عن فيلم معين لتشاهده اليوم؟"

3. طول الإجابة:
- إجاباتك دائماً متوسطة الطول (3 إلى 5 أسطر كحد أقصى). لا قصيرة جداً ولا مقالات طويلة.

4. التعامل مع الروابط:
- القنوات الرسمية: @tztvn و @o1tvn وسيرفرات "Server 1 | TZTVN".
- روابط @tztvn أو @o1tvn = آمنة تفاعل معها بإيجابية.
- روابط خارجية غريبة = أخبر المستخدم بلطف أنها لا تنتمي لـ TZTVN.

5. نبرة الصوت:
- كن ودوداً، حماسياً، وعاشقاً للسينما.
- استخدم مصطلحات: "تحفة فنية"، "أحداث مشوقة"، "حبكة درامية".
- شجع المستخدمين دائماً على متابعة جديد TZTVN.

6. معلومات الأفلام:
- عندما يُرفق لك معلومات فيلم من TMDb، استخدمها كمرجع أساسي وقدمها بأسلوب سينمائي جذاب.
- اذكر التقييم وتاريخ الإصدار والوصف بطريقة شيقة.
"""

# ══════════════════════════════════════
#        قائمة الكلمات المحظورة
# ══════════════════════════════════════
BANNED_WORDS = [
    "سكس","نيك","قحبة","قحبه","قحب","عصب","عصبه","عصبة","سيكس","انيكك",
    "بزول","بزل","بوالة","nike","3aseba","bazole","zeb","zebe","zbe","زب",
    "زيب","أنيك","انيك","أنيكك","كس","شرموطه","شراميط","شرموطة","شرمطة",
    "كسس","كيس","معصبين","cimatn","cima","cematn","cmatn","tunflix",
    "cimatncom","cimaa","cemaa","tuniflixsite","tuniflix","3asba","3sba",
    "3asbaa","nikee","nikeee","nique","nque","aseba","asba","aseb","asebaa",
    "eseba","esba","asbba","asebba","asebb","sexe","sex","sexx","chatt",
    "69","زبزوب","rika","rkatn","rka","rikatn","rekatn","nyek","neyk",
    "neyek","neyik","neyeke","nyeke","nyike","nyke","cinmatn","cinma","جنس",
    "الجنس","الزب","لحس","ألحس","مص","مصيه","مصي","egybst","egbest",
    "igybest","egibest","igbst","filmstn","filmtn","cmtn","cimtn","ciyma",
    "cemaatn","3sb","3esba","3asb","nikke","tnyk","nayek","ineyko","menyek",
    "mnyk","mneyk","neyeko","tneyk","tnik","tnekna","nakona","nekouna",
    "nekoune","nekone","nekona","18+","porn","pornhub","xxx","nxxx","nxx",
    "xxn","porno","hot","hote","hots","egybest","igybest","igbest","egbest",
    "tunigazelle","tunigazell","فرجك","بالمني","مني","المني","hdobox",
    "hdo box","زك ام","زك",
]
BANNED_EMOJIS = ["🔥","🥵","🖕","🇮🇱","🍑","🍆","🍌","👅","💦","🔞"]

def contains_banned(text: str) -> bool:
    text_lower = text.lower()
    for word in BANNED_WORDS:
        if word.lower() in text_lower:
            return True
    for emoji in BANNED_EMOJIS:
        if emoji in text:
            return True
    return False

# ══════════════════════════════════════
#         TMDb - بحث عن فيلم/مسلسل
# ══════════════════════════════════════
def search_tmdb(query: str) -> str:
    """يبحث في TMDb ويرجع معلومات الفيلم/المسلسل"""
    try:
        # البحث أولاً في الأفلام
        url = f"https://api.themoviedb.org/3/search/multi"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "ar",
            "page": 1
        }
        r = requests.get(url, params=params, timeout=10)
        data = r.json()

        if not data.get("results"):
            # جرب بالإنجليزية
            params["language"] = "en-US"
            r = requests.get(url, params=params, timeout=10)
            data = r.json()

        if not data.get("results"):
            return ""

        item = data["results"][0]
        media_type = item.get("media_type", "movie")

        if media_type == "movie":
            title     = item.get("title") or item.get("original_title", "غير معروف")
            overview  = item.get("overview", "لا يوجد وصف متاح")
            rating    = item.get("vote_average", 0)
            date      = item.get("release_date", "غير محدد")
            type_ar   = "فيلم"
        elif media_type == "tv":
            title     = item.get("name") or item.get("original_name", "غير معروف")
            overview  = item.get("overview", "لا يوجد وصف متاح")
            rating    = item.get("vote_average", 0)
            date      = item.get("first_air_date", "غير محدد")
            type_ar   = "مسلسل"
        else:
            return ""

        # هل نزل؟
        from datetime import datetime
        status = "✅ نزل"
        if date and date != "غير محدد":
            try:
                release = datetime.strptime(date[:10], "%Y-%m-%d")
                if release > datetime.now():
                    status = f"🔜 لم ينزل بعد - موعد الإصدار: {date[:10]}"
                else:
                    status = f"✅ نزل بتاريخ {date[:10]}"
            except:
                pass

        info = (
            f"📽️ [{type_ar}] {title}\n"
            f"📅 {status}\n"
            f"⭐ التقييم: {rating}/10\n"
            f"📝 {overview[:200]}{'...' if len(overview) > 200 else ''}"
        )
        return info

    except Exception as e:
        logging.error(f"TMDb error: {e}")
        return ""

# ══════════════════════════════════════
#    كشف هل السؤال عن فيلم/مسلسل؟
# ══════════════════════════════════════
MOVIE_KEYWORDS = [
    "فيلم","مسلسل","نزل","يطلع","طلع","اصدر","صدر","موعد","اصدار",
    "متى","هل","عرض","الجزء","سيزون","موسم","ايه","هل نزل","متى ينزل",
    "movie","series","film","release","out","watch","season"
]

def is_movie_question(text: str) -> bool:
    text_lower = text.lower()
    for kw in MOVIE_KEYWORDS:
        if kw in text_lower:
            return True
    return False

def extract_movie_name(text: str) -> str:
    """استخرج اسم الفيلم من السؤال"""
    removes = [
        "هل نزل","هل طلع","هل اصدر","هل صدر","متى ينزل","متى يطلع",
        "متى نزل","موعد","فيلم","مسلسل","الجزء","سيزون","موسم",
        "هل","نزل","طلع","اصدر","صدر","ينزل","يطلع",
        "is","out","has","when","does","movie","series","the","released","release"
    ]
    result = text.strip()
    for r in removes:
        result = result.replace(r, "")
    return result.strip()

# ══════════════════════════════════════
#       Groq Client + Chat History
# ══════════════════════════════════════
groq_client  = Groq(api_key=GROQ_API_KEY)
chat_history: dict = {}

# ══════════════════════════════════════
#           معالج الرسائل
# ══════════════════════════════════════
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    chat_id   = update.message.chat_id
    user_name = update.message.from_user.first_name or "عضو"
    text      = update.message.text

    # ── فحص محتوى المستخدم ──
    if contains_banned(text):
        await update.message.reply_text(
            "⚠️ رسالتك تحتوي على محتوى مخالف لقواعد المجموعة. يرجى الالتزام باللياقة 🙏"
        )
        return

    # ── تهيئة تاريخ المحادثة ──
    if chat_id not in chat_history:
        chat_history[chat_id] = []

    # ── هل تم استدعاء البوت؟ ──
    bot_username = (await context.bot.get_me()).username
    mentioned    = f"@{bot_username}" in text or BOT_NAME.lower() in text.lower()
    is_private   = update.message.chat.type == "private"

    if not (mentioned or is_private):
        # احفظ الرسالة في التاريخ بدون رد
        chat_history[chat_id].append({"role": "user", "content": f"{user_name}: {text}"})
        return

    # ── بحث TMDb إذا السؤال عن فيلم ──
    tmdb_info = ""
    if is_movie_question(text):
        movie_name = extract_movie_name(text)
        if len(movie_name) > 2:
            tmdb_info = search_tmdb(movie_name)

    # ── بناء الرسالة للـ AI ──
    user_message = f"{user_name}: {text}"
    if tmdb_info:
        user_message += f"\n\n[معلومات من قاعدة بيانات TMDb الرسمية:]\n{tmdb_info}"

    chat_history[chat_id].append({"role": "user", "content": user_message})

    # ── طلب الـ AI ──
    try:
        response = groq_client.chat.completions.create(
            model=MODEL_NAME,
            temperature=0.6,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *chat_history[chat_id][-20:]
            ]
        )
        reply = response.choices[0].message.content

        if contains_banned(reply):
            reply = "عذراً، لا يمكنني الإجابة على هذا. 🎬 هل تبحث عن توصية سينمائية؟"

        chat_history[chat_id].append({"role": "assistant", "content": reply})
        await update.message.reply_text(reply)

    except Exception as e:
        logging.error(f"Groq error: {e}")
        await update.message.reply_text("⚠️ حدث خطأ مؤقت، حاول مجدداً بعد لحظات.")

# ══════════════════════════════════════
#        أمر /start
# ══════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 مرحباً بك في مساعد TZTVN السينمائي!\n"
        "أنا هنا لمساعدتك في اكتشاف أفضل الأفلام والمسلسلات.\n"
        "يمكنني البحث عن أي فيلم أو مسلسل وإخبارك هل نزل أم لا! 🔍\n"
        "ناديني بـ @tztvn أو اذكر اسمي في المجموعة 😊"
    )

# ══════════════════════════════════════
#        أمر /search للبحث المباشر
# ══════════════════════════════════════
async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("🔍 استخدم: /search اسم_الفيلم\nمثال: /search Dune")
        return
    query = " ".join(context.args)
    info  = search_tmdb(query)
    if info:
        await update.message.reply_text(f"🎬 نتيجة البحث:\n\n{info}")
    else:
        await update.message.reply_text(f"❌ لم أجد نتائج لـ '{query}'. تأكد من الاسم وحاول مجدداً.")

# ══════════════════════════════════════
#        أمر /reset
# ══════════════════════════════════════
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    chat_history[chat_id] = []
    await update.message.reply_text("✅ تم مسح تاريخ المحادثة!")

# ══════════════════════════════════════
#        تشغيل البوت
# ══════════════════════════════════════
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start",  start))
app.add_handler(CommandHandler("reset",  reset))
app.add_handler(CommandHandler("search", search_cmd))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("✅ TZTVN Bot يعمل الآن مع TMDb + UptimeRobot Support...")
app.run_polling()
