import os
import logging
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from groq import Groq

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY   = os.environ.get("GROQ_API_KEY")
TMDB_API_KEY   = os.environ.get("TMDB_API_KEY")
BOT_NAME       = "tztvn"
MODEL_NAME     = "llama-3.3-70b-versatile"

logging.basicConfig(level=logging.INFO)

# Web Server
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"TZTVN Bot is alive!")
    def log_message(self, format, *args):
        pass

def run_server():
    server = HTTPServer(("0.0.0.0", 8080), PingHandler)
    server.serve_forever()

threading.Thread(target=run_server, daemon=True).start()

SYSTEM_PROMPT = """
أنت الذكاء الاصطناعي الرسمي، الحصري، والناطق باسم منصة "TZTVN". أنت تعمل داخل مجموعة تيليجرام خاصة.
عليك الالتزام بهذه القواعد:
1. أنت "مساعد TZTVN السينمائي" فقط.
2. نطاق حديثك: الأفلام، المسلسلات، التقييمات السينمائية فقط.
3. إجاباتك 3 إلى 5 أسطر فقط.
4. القنوات الرسمية: @tztvn و @o1tvn.
5. كن ودوداً وحماسياً وعاشقاً للسينما.
6. عندما ترفق معلومات TMDb استخدمها بأسلوب جذاب.
"""

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

def search_tmdb(query: str) -> str:
    try:
        url = "https://api.themoviedb.org/3/search/multi"
        params = {"api_key": TMDB_API_KEY, "query": query, "language": "ar", "page": 1}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if not data.get("results"):
            params["language"] = "en-US"
            r = requests.get(url, params=params, timeout=10)
            data = r.json()
        if not data.get("results"):
            return ""
        item = data["results"][0]
        media_type = item.get("media_type", "movie")
        if media_type == "movie":
            title    = item.get("title") or item.get("original_title", "غير معروف")
            overview = item.get("overview", "لا يوجد وصف")
            rating   = item.get("vote_average", 0)
            date     = item.get("release_date", "غير محدد")
            type_ar  = "فيلم"
        elif media_type == "tv":
            title    = item.get("name") or item.get("original_name", "غير معروف")
            overview = item.get("overview", "لا يوجد وصف")
            rating   = item.get("vote_average", 0)
            date     = item.get("first_air_date", "غير محدد")
            type_ar  = "مسلسل"
        else:
            return ""
        from datetime import datetime
        status = "✅ نزل"
        if date and date != "غير محدد":
            try:
                release = datetime.strptime(date[:10], "%Y-%m-%d")
                if release > datetime.now():
                    status = f"🔜 لم ينزل بعد - موعد: {date[:10]}"
                else:
                    status = f"✅ نزل {date[:10]}"
            except:
                pass
        return (
            f"📽️ [{type_ar}] {title}\n"
            f"📅 {status}\n"
            f"⭐ {rating}/10\n"
            f"📝 {overview[:200]}{'...' if len(overview) > 200 else ''}"
        )
    except Exception as e:
        logging.error(f"TMDb error: {e}")
        return ""

MOVIE_KEYWORDS = [
    "فيلم","مسلسل","نزل","يطلع","طلع","اصدر","صدر","موعد","اصدار",
    "متى","هل","عرض","الجزء","سيزون","موسم",
    "movie","series","film","release","out","watch","season"
]

def is_movie_question(text):
    t = text.lower()
    return any(kw in t for kw in MOVIE_KEYWORDS)

def extract_movie_name(text):
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

groq_client  = Groq(api_key=GROQ_API_KEY)
chat_history = {}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    chat_id   = update.message.chat_id
    user_name = update.message.from_user.first_name or "عضو"
    text      = update.message.text
    if contains_banned(text):
        await update.message.reply_text("⚠️ رسالتك تحتوي على محتوى مخالف. يرجى الالتزام باللياقة 🙏")
        return
    if chat_id not in chat_history:
        chat_history[chat_id] = []
    bot_me       = await context.bot.get_me()
    mentioned    = f"@{bot_me.username}" in text or BOT_NAME.lower() in text.lower()
    is_private   = update.message.chat.type == "private"
    if not (mentioned or is_private):
        chat_history[chat_id].append({"role": "user", "content": f"{user_name}: {text}"})
        return
    tmdb_info = ""
    if is_movie_question(text):
        movie_name = extract_movie_name(text)
        if len(movie_name) > 2:
            tmdb_info = search_tmdb(movie_name)
    user_message = f"{user_name}: {text}"
    if tmdb_info:
        user_message += f"\n\n[معلومات TMDb:]\n{tmdb_info}"
    chat_history[chat_id].append({"role": "user", "content": user_message})
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
            reply = "عذراً، لا يمكنني الإجابة. 🎬 هل تبحث عن توصية سينمائية؟"
        chat_history[chat_id].append({"role": "assistant", "content": reply})
        await update.message.reply_text(reply)
    except Exception as e:
        logging.error(f"Groq error: {e}")
        await update.message.reply_text("⚠️ حدث خطأ مؤقت، حاول مجدداً.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 مرحباً بك في مساعد TZTVN السينمائي!\n"
        "ناديني بـ @tztvn أو اذكر اسمي في المجموعة 😊"
    )

async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("🔍 مثال: /search Dune")
        return
    query = " ".join(context.args)
    info  = search_tmdb(query)
    if info:
        await update.message.reply_text(f"🎬 نتيجة:\n\n{info}")
    else:
        await update.message.reply_text(f"❌ لم أجد نتائج لـ '{query}'.")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_history[update.message.chat_id] = []
    await update.message.reply_text("✅ تم مسح تاريخ المحادثة!")

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("reset",  reset))
    app.add_handler(CommandHandler("search", search_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ TZTVN Bot يعمل الآن!")
    app.run_polling()

if __name__ == "__main__":
    main()
