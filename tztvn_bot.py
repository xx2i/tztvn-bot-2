import os
import logging
import threading
import requests
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from groq import Groq

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY     = os.environ.get("GROQ_API_KEY")
TMDB_API_KEY     = os.environ.get("TMDB_API_KEY")
OMDB_API_KEY     = os.environ.get("OMDB_API_KEY")
TRAKT_CLIENT_ID  = os.environ.get("TRAKT_CLIENT_ID")
BOT_NAME         = "tztvn"
MODEL_NAME       = "llama-3.3-70b-versatile"

logging.basicConfig(level=logging.INFO)

# ── Web Server ──────────────────────────────────────────────────────────────
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"TZTVN Bot is alive!")
    def log_message(self, format, *args):
        pass

threading.Thread(target=lambda: HTTPServer(("0.0.0.0", 8080), PingHandler).serve_forever(), daemon=True).start()

# ── System Prompt ───────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
أنت الذكاء الاصطناعي الرسمي، الحصري، والناطق باسم منصة "TZTVN". أنت تعمل داخل مجموعة تيليجرام خاصة.
عليك الالتزام بهذه القواعد:
1. أنت "مساعد TZTVN السينمائي" فقط.
2. نطاق حديثك: الأفلام، المسلسلات، التقييمات السينمائية فقط.
3. إجاباتك 3 إلى 5 أسطر فقط.
4. القنوات الرسمية: @tztvn و @o1tvn.
5. كن ودوداً وحماسياً وعاشقاً للسينما.
6. عندما ترفق معلومات الأفلام استخدمها بأسلوب جذاب.
"""

# ── Banned Content ──────────────────────────────────────────────────────────
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

# ── TMDb ────────────────────────────────────────────────────────────────────
def search_tmdb(query: str) -> dict:
    """Returns dict with keys: title, type_ar, date, rating, overview, tmdb_id, imdb_id"""
    try:
        url = "https://api.themoviedb.org/3/search/multi"
        for lang in ["ar", "en-US"]:
            r = requests.get(url, params={"api_key": TMDB_API_KEY, "query": query, "language": lang, "page": 1}, timeout=10)
            data = r.json()
            if data.get("results"):
                break
        if not data.get("results"):
            return {}
        item = data["results"][0]
        media_type = item.get("media_type", "movie")
        if media_type == "movie":
            title    = item.get("title") or item.get("original_title", "غير معروف")
            overview = item.get("overview", "لا يوجد وصف")
            rating   = item.get("vote_average", 0)
            date     = item.get("release_date", "")
            type_ar  = "فيلم"
        elif media_type == "tv":
            title    = item.get("name") or item.get("original_name", "غير معروف")
            overview = item.get("overview", "لا يوجد وصف")
            rating   = item.get("vote_average", 0)
            date     = item.get("first_air_date", "")
            type_ar  = "مسلسل"
        else:
            return {}
        tmdb_id = item.get("id")
        # Get IMDb ID from TMDb details
        imdb_id = ""
        try:
            detail_url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/external_ids"
            det = requests.get(detail_url, params={"api_key": TMDB_API_KEY}, timeout=8).json()
            imdb_id = det.get("imdb_id", "")
        except:
            pass
        return {
            "title": title, "type_ar": type_ar, "date": date,
            "rating": rating, "overview": overview,
            "tmdb_id": tmdb_id, "media_type": media_type, "imdb_id": imdb_id
        }
    except Exception as e:
        logging.error(f"TMDb error: {e}")
        return {}

# ── TMDb Watch Providers (JustWatch) ────────────────────────────────────────
def get_watch_providers(tmdb_id: int, media_type: str) -> str:
    """Returns a string like: Netflix ✅ | Disney+ ✅"""
    try:
        url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/watch/providers"
        r = requests.get(url, params={"api_key": TMDB_API_KEY}, timeout=8)
        data = r.json().get("results", {})
        # Try TN first, then FR, then US
        region_data = data.get("TN") or data.get("FR") or data.get("US") or {}
        if not region_data:
            return ""
        platforms = []
        for entry in (region_data.get("flatrate") or region_data.get("free") or []):
            platforms.append(entry.get("provider_name", ""))
        if platforms:
            return " | ".join(f"✅ {p}" for p in platforms[:4])
        return ""
    except Exception as e:
        logging.error(f"Watch providers error: {e}")
        return ""

# ── OMDb ────────────────────────────────────────────────────────────────────
def get_omdb_ratings(imdb_id: str = "", title: str = "") -> dict:
    """Returns dict with imdb_rating, rt_rating, metacritic"""
    try:
        params = {"apikey": OMDB_API_KEY}
        if imdb_id:
            params["i"] = imdb_id
        elif title:
            params["t"] = title
        else:
            return {}
        r = requests.get("http://www.omdbapi.com/", params=params, timeout=8)
        data = r.json()
        if data.get("Response") != "True":
            return {}
        result = {}
        for rating in data.get("Ratings", []):
            src = rating.get("Source", "")
            val = rating.get("Value", "")
            if "Internet Movie Database" in src:
                result["imdb"] = val
            elif "Rotten Tomatoes" in src:
                result["rt"] = val
            elif "Metacritic" in src:
                result["meta"] = val
        return result
    except Exception as e:
        logging.error(f"OMDb error: {e}")
        return {}

# ── IMDb Unofficial (iamidiotareyoutoo) ─────────────────────────────────────
def get_imdb_unofficial(query: str, imdb_id: str = "") -> dict:
    """Returns dict with title, year, plot, poster, justwatch"""
    try:
        base = "https://imdb.iamidiotareyoutoo.com"
        if imdb_id:
            r = requests.get(f"{base}/search", params={"tt": imdb_id}, timeout=10)
        else:
            r = requests.get(f"{base}/search", params={"q": query}, timeout=10)
        data = r.json()
        if not data:
            return {}
        # Get JustWatch info
        jw_text = ""
        try:
            jw_q = imdb_id if imdb_id else query
            jw = requests.get(f"{base}/justwatch", params={"q": jw_q}, timeout=10).json()
            if jw:
                providers = []
                for item in (jw if isinstance(jw, list) else [jw]):
                    name = item.get("provider_name") or item.get("name", "")
                    if name:
                        providers.append(name)
                if providers:
                    jw_text = " | ".join(f"▶️ {p}" for p in providers[:4])
        except:
            pass
        return {"justwatch_unofficial": jw_text}
    except Exception as e:
        logging.error(f"IMDb unofficial error: {e}")
        return {}

# ── Trakt Trending ──────────────────────────────────────────────────────────
def get_trakt_trending(media_type: str = "movies", limit: int = 5) -> list:
    """Returns list of dicts with title and year"""
    try:
        url = f"https://api.trakt.tv/{media_type}/trending"
        headers = {
            "Content-Type": "application/json",
            "trakt-api-version": "2",
            "trakt-api-key": TRAKT_CLIENT_ID
        }
        r = requests.get(url, headers=headers, params={"limit": limit}, timeout=10)
        data = r.json()
        results = []
        for item in data[:limit]:
            obj = item.get("movie") or item.get("show") or {}
            results.append({
                "title": obj.get("title", ""),
                "year": obj.get("year", "")
            })
        return results
    except Exception as e:
        logging.error(f"Trakt error: {e}")
        return []

# ── Build Full Movie Card ────────────────────────────────────────────────────
def build_movie_card(query: str) -> str:
    tmdb = search_tmdb(query)
    if not tmdb:
        return ""

    title    = tmdb["title"]
    type_ar  = tmdb["type_ar"]
    date     = tmdb.get("date", "")
    rating   = tmdb.get("rating", 0)
    overview = tmdb.get("overview", "")
    tmdb_id  = tmdb.get("tmdb_id")
    imdb_id  = tmdb.get("imdb_id", "")
    media_type = tmdb.get("media_type", "movie")

    # Date status
    status = "✅ نزل"
    if date:
        try:
            release = datetime.strptime(date[:10], "%Y-%m-%d")
            if release > datetime.now():
                status = f"🔜 لم ينزل بعد — {date[:10]}"
            else:
                status = f"✅ نزل {date[:10]}"
        except:
            pass

    # OMDb ratings
    omdb = get_omdb_ratings(imdb_id=imdb_id, title=title)

    # Watch providers from TMDb (JustWatch)
    watch = get_watch_providers(tmdb_id, media_type) if tmdb_id else ""

    # IMDb unofficial (JustWatch backup)
    imdb_unoff = get_imdb_unofficial(query, imdb_id)
    watch_backup = imdb_unoff.get("justwatch_unofficial", "")

    # Build card
    lines = [f"🎬 [{type_ar}] {title}", f"📅 {status}"]

    # Ratings block
    rating_parts = [f"⭐ TMDb: {rating}/10"]
    if omdb.get("imdb"):
        rating_parts.append(f"🎭 IMDb: {omdb['imdb']}")
    if omdb.get("rt"):
        rating_parts.append(f"🍅 RT: {omdb['rt']}")
    lines.append(" | ".join(rating_parts))

    # Where to watch
    final_watch = watch or watch_backup
    if final_watch:
        lines.append(f"📺 شاهده على: {final_watch}")
    else:
        lines.append("📺 غير متوفر على منصات البث حالياً")

    # Overview
    lines.append(f"📝 {overview[:200]}{'...' if len(overview) > 200 else ''}")

    return "\n".join(lines)

# ── Keywords ────────────────────────────────────────────────────────────────
MOVIE_KEYWORDS = [
    "فيلم","مسلسل","نزل","يطلع","طلع","اصدر","صدر","موعد","اصدار",
    "متى","هل","عرض","الجزء","سيزون","موسم",
    "movie","series","film","release","out","watch","season"
]

def is_movie_question(text):
    return any(kw in text.lower() for kw in MOVIE_KEYWORDS)

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

# ── Bot Logic ────────────────────────────────────────────────────────────────
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

    bot_me     = await context.bot.get_me()
    mentioned  = f"@{bot_me.username}" in text or BOT_NAME.lower() in text.lower()
    is_private = update.message.chat.type == "private"

    if not (mentioned or is_private):
        chat_history[chat_id].append({"role": "user", "content": f"{user_name}: {text}"})
        return

    movie_card = ""
    if is_movie_question(text):
        movie_name = extract_movie_name(text)
        if len(movie_name) > 2:
            movie_card = build_movie_card(movie_name)

    user_message = f"{user_name}: {text}"
    if movie_card:
        user_message += f"\n\n[معلومات الفيلم:]\n{movie_card}"

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
    card  = build_movie_card(query)
    if card:
        await update.message.reply_text(f"🎬 نتيجة:\n\n{card}")
    else:
        await update.message.reply_text(f"❌ لم أجد نتائج لـ '{query}'.")

async def trending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    movies = get_trakt_trending("movies", 5)
    shows  = get_trakt_trending("shows", 5)
    msg = "🔥 الأفلام الأكثر مشاهدة الآن:\n"
    for i, m in enumerate(movies, 1):
        msg += f"{i}. {m['title']} ({m['year']})\n"
    msg += "\n📺 المسلسلات الأكثر مشاهدة الآن:\n"
    for i, s in enumerate(shows, 1):
        msg += f"{i}. {s['title']} ({s['year']})\n"
    await update.message.reply_text(msg)

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_history[update.message.chat_id] = []
    await update.message.reply_text("✅ تم مسح تاريخ المحادثة!")

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start",    start))
    app.add_handler(CommandHandler("reset",    reset))
    app.add_handler(CommandHandler("search",   search_cmd))
    app.add_handler(CommandHandler("trending", trending_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ TZTVN Bot يعمل الآن!")
    app.run_polling()

if __name__ == "__main__":
    main()
