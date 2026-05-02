import os
import logging
import threading
import requests
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from groq import Groq

TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY    = os.environ.get("GROQ_API_KEY")
TMDB_API_KEY    = os.environ.get("TMDB_API_KEY")
OMDB_API_KEY    = os.environ.get("OMDB_API_KEY")
TRAKT_CLIENT_ID = os.environ.get("TRAKT_CLIENT_ID")
BOT_NAME        = "tztvn"
MODEL_NAME      = "llama-3.3-70b-versatile"

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
أنت مساعد سينمائي ذكي يعمل في مجموعة تيليجرام تابعة لمنصة TZTVN.

شخصيتك:
- عاشق حقيقي للسينما، تتحدث بحماس وعفوية.
- ردودك واضحة ومنظمة، 4 إلى 8 أسطر.
- عندما تحصل على معلومات فيلم، اشرحها بأسلوب جذاب وليس مجرد نسخ.
- لا تكرر ذكر القنوات في كل رسالة — فقط عند الحاجة الفعلية مثل إذا سألوا عن المنصة.
- القنوات الرسمية هي @tztvn و @o1tvn فقط إذا سُئلت عنها.
- إذا لم تجد معلومات عن فيلم معين، قل ذلك بصراحة بدلاً من الاختراع.
- تحدث بالعربية دائماً.
- لا تبدأ ردك بـ "بالطبع" أو "أهلاً" في كل مرة.

عند وصول معلومات فيلم:
- استخدمها كاملة وقدّمها بأسلوب محادثة طبيعية.
- لا تنسخ المعلومات حرفياً بل لخّصها بأسلوبك.
- إذا التقييم عالٍ، عبّر عن حماسك. إذا كان منخفضاً كن صريحاً.
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

# ── IMDb Unofficial — المصدر الأول ──────────────────────────────────────────
def search_imdb_unofficial(query: str) -> dict:
    """
    يبحث في IMDb غير الرسمي أولاً.
    يعيد: title, year, rating, plot, imdb_id, justwatch
    """
    try:
        base = "https://imdb.iamidiotareyoutoo.com"
        r = requests.get(f"{base}/search", params={"q": query}, timeout=10)
        if r.status_code != 200:
            return {}
        data = r.json()
        # النتيجة قد تكون dict أو list
        if isinstance(data, list):
            if not data:
                return {}
            item = data[0]
        elif isinstance(data, dict):
            # إذا فيه مفتاح results
            if data.get("#RESULTS"):
                item = data["#RESULTS"][0]
            else:
                item = data
        else:
            return {}

        imdb_id  = item.get("#IMDB_ID", "") or item.get("imdb_id", "")
        title    = item.get("#TITLE", "") or item.get("title", "")
        year     = item.get("#YEAR", "") or item.get("year", "")
        rating   = item.get("#IMDB_RATING", "") or item.get("rating", "")
        actors   = item.get("#ACTORS", "") or item.get("actors", "")
        plot     = item.get("#PLOT", "") or item.get("plot", "")
        genre    = item.get("#GENRE", "") or item.get("genre", "")

        if not title:
            return {}

        # JustWatch من نفس الـ API
        jw_text = ""
        try:
            jw_q = imdb_id if imdb_id else query
            jw_r = requests.get(f"{base}/justwatch", params={"q": jw_q}, timeout=10)
            jw_data = jw_r.json()
            providers = []
            items_list = jw_data if isinstance(jw_data, list) else [jw_data]
            for jw_item in items_list:
                name = jw_item.get("provider_name") or jw_item.get("name", "")
                if name:
                    providers.append(name)
            if providers:
                jw_text = " | ".join(f"▶️ {p}" for p in providers[:5])
        except:
            pass

        return {
            "title": title, "year": year, "rating": rating,
            "plot": plot, "genre": genre, "actors": actors,
            "imdb_id": imdb_id, "justwatch": jw_text
        }
    except Exception as e:
        logging.error(f"IMDb unofficial error: {e}")
        return {}

# ── OMDb — تقييمات إضافية ───────────────────────────────────────────────────
def get_omdb_data(imdb_id: str = "", title: str = "") -> dict:
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
        result = {"director": data.get("Director", ""), "runtime": data.get("Runtime", "")}
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

# ── TMDb — احتياطي إذا فشل IMDb ─────────────────────────────────────────────
def search_tmdb_fallback(query: str) -> dict:
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
            title   = item.get("title") or item.get("original_title", "")
            date    = item.get("release_date", "")
            type_ar = "فيلم"
        elif media_type == "tv":
            title   = item.get("name") or item.get("original_name", "")
            date    = item.get("first_air_date", "")
            type_ar = "مسلسل"
        else:
            return {}
        overview = item.get("overview", "")
        rating   = item.get("vote_average", 0)
        tmdb_id  = item.get("id")
        imdb_id  = ""
        try:
            det = requests.get(
                f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/external_ids",
                params={"api_key": TMDB_API_KEY}, timeout=8
            ).json()
            imdb_id = det.get("imdb_id", "")
        except:
            pass
        # Watch providers
        watch = ""
        try:
            wp = requests.get(
                f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/watch/providers",
                params={"api_key": TMDB_API_KEY}, timeout=8
            ).json().get("results", {})
            region = wp.get("TN") or wp.get("FR") or wp.get("US") or {}
            platforms = []
            for e in (region.get("flatrate") or region.get("free") or []):
                platforms.append(e.get("provider_name", ""))
            if platforms:
                watch = " | ".join(f"▶️ {p}" for p in platforms[:4])
        except:
            pass
        return {
            "title": title, "type_ar": type_ar, "date": date,
            "rating": rating, "overview": overview,
            "imdb_id": imdb_id, "watch": watch
        }
    except Exception as e:
        logging.error(f"TMDb fallback error: {e}")
        return {}

# ── Trakt Trending ──────────────────────────────────────────────────────────
def get_trakt_trending(media_type: str = "movies", limit: int = 5) -> list:
    try:
        r = requests.get(
            f"https://api.trakt.tv/{media_type}/trending",
            headers={"Content-Type": "application/json", "trakt-api-version": "2", "trakt-api-key": TRAKT_CLIENT_ID},
            params={"limit": limit}, timeout=10
        )
        results = []
        for item in r.json()[:limit]:
            obj = item.get("movie") or item.get("show") or {}
            results.append({"title": obj.get("title", ""), "year": obj.get("year", "")})
        return results
    except Exception as e:
        logging.error(f"Trakt error: {e}")
        return []

# ── Build Movie Card — IMDb أولاً ────────────────────────────────────────────
def build_movie_card(query: str) -> str:
    # 1. ابحث في IMDb أولاً
    imdb_data = search_imdb_unofficial(query)

    if imdb_data:
        title    = imdb_data.get("title", "")
        year     = imdb_data.get("year", "")
        rating   = imdb_data.get("rating", "")
        plot     = imdb_data.get("plot", "لا يوجد وصف")
        genre    = imdb_data.get("genre", "")
        actors   = imdb_data.get("actors", "")
        imdb_id  = imdb_data.get("imdb_id", "")
        jw       = imdb_data.get("justwatch", "")

        # 2. أضف تقييمات OMDb
        omdb = get_omdb_data(imdb_id=imdb_id, title=title)
        rt_rating  = omdb.get("rt", "")
        director   = omdb.get("director", "")
        runtime    = omdb.get("runtime", "")
        final_imdb = omdb.get("imdb", "") or (f"{rating}/10" if rating else "")

        lines = [f"🎬 {title} ({year})"] if year else [f"🎬 {title}"]
        if genre:    lines.append(f"🎭 النوع: {genre}")
        if director: lines.append(f"🎥 المخرج: {director}")
        if runtime:  lines.append(f"⏱️ المدة: {runtime}")

        ratings_parts = []
        if final_imdb: ratings_parts.append(f"⭐ IMDb: {final_imdb}")
        if rt_rating:  ratings_parts.append(f"🍅 RT: {rt_rating}")
        if ratings_parts: lines.append(" | ".join(ratings_parts))

        if jw:
            lines.append(f"📺 شاهده على: {jw}")
        else:
            lines.append("📺 غير متوفر حالياً على منصات البث")

        if plot:
            lines.append(f"📝 {plot[:220]}{'...' if len(plot) > 220 else ''}")

        return "\n".join(lines)

    # 3. إذا فشل IMDb، استخدم TMDb احتياطياً
    tmdb = search_tmdb_fallback(query)
    if not tmdb:
        return ""

    title   = tmdb.get("title", "")
    type_ar = tmdb.get("type_ar", "فيلم")
    date    = tmdb.get("date", "")
    rating  = tmdb.get("rating", 0)
    overview= tmdb.get("overview", "لا يوجد وصف")
    imdb_id = tmdb.get("imdb_id", "")
    watch   = tmdb.get("watch", "")

    # تاريخ الإصدار
    status = "✅ نزل"
    if date:
        try:
            rel = datetime.strptime(date[:10], "%Y-%m-%d")
            if rel > datetime.now():
                status = f"🔜 لم ينزل بعد — {date[:10]}"
            else:
                status = f"✅ نزل {date[:10]}"
        except:
            pass

    omdb = get_omdb_data(imdb_id=imdb_id, title=title)
    lines = [
        f"🎬 [{type_ar}] {title}",
        f"📅 {status}",
    ]
    ratings_parts = [f"⭐ TMDb: {rating}/10"]
    if omdb.get("imdb"): ratings_parts.append(f"🎭 IMDb: {omdb['imdb']}")
    if omdb.get("rt"):   ratings_parts.append(f"🍅 RT: {omdb['rt']}")
    lines.append(" | ".join(ratings_parts))

    if watch:
        lines.append(f"📺 شاهده على: {watch}")
    else:
        lines.append("📺 غير متوفر حالياً على منصات البث")

    lines.append(f"📝 {overview[:220]}{'...' if len(overview) > 220 else ''}")
    return "\n".join(lines)

# ── Movie Keywords ───────────────────────────────────────────────────────────
MOVIE_KEYWORDS = [
    "فيلم","مسلسل","نزل","يطلع","طلع","اصدر","صدر","موعد","اصدار",
    "متى","عرض","الجزء","سيزون","موسم","ممثل","مخرج","تقييم",
    "movie","series","film","release","out","watch","season","actor","director"
]

def is_movie_question(text):
    return any(kw in text.lower() for kw in MOVIE_KEYWORDS)

def extract_movie_name(text):
    removes = [
        "هل نزل","هل طلع","هل اصدر","هل صدر","متى ينزل","متى يطلع",
        "متى نزل","موعد","فيلم","مسلسل","الجزء","سيزون","موسم",
        "هل","نزل","طلع","اصدر","صدر","ينزل","يطلع","اخبرني عن","ما هو",
        "is","out","has","when","does","movie","series","the","released","release","tell me about"
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
    clean_text = text.replace(f"@{bot_me.username}", "").replace("tztvn", "").strip()
    if is_movie_question(clean_text):
        movie_name = extract_movie_name(clean_text)
        if len(movie_name) > 1:
            movie_card = build_movie_card(movie_name)

    user_message = f"{user_name}: {clean_text}"
    if movie_card:
        user_message += f"\n\n[بيانات الفيلم من قواعد البيانات:]\n{movie_card}"
    else:
        user_message += "\n[لم يُعثر على بيانات فيلم محدد]"

    chat_history[chat_id].append({"role": "user", "content": user_message})

    try:
        response = groq_client.chat.completions.create(
            model=MODEL_NAME,
            temperature=0.7,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                *chat_history[chat_id][-20:]
            ]
        )
        reply = response.choices[0].message.content
        if contains_banned(reply):
            reply = "عذراً، لا يمكنني الإجابة على هذا. 🎬"
        chat_history[chat_id].append({"role": "assistant", "content": reply})
        await update.message.reply_text(reply)
    except Exception as e:
        logging.error(f"Groq error: {e}")
        await update.message.reply_text("⚠️ حدث خطأ مؤقت، حاول مجدداً.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 مرحباً! أنا مساعد TZTVN السينمائي.\n"
        "اسألني عن أي فيلم أو مسلسل وسأعطيك كل التفاصيل 😊\n"
        "جرب: /search Inception أو /trending"
    )

async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("🔍 مثال: /search Inception")
        return
    query = " ".join(context.args)
    await update.message.reply_text("🔍 جاري البحث...")
    card = build_movie_card(query)
    if card:
        await update.message.reply_text(card)
    else:
        await update.message.reply_text(
            f"❌ لم أجد معلومات كافية عن '{query}'.\n"
            "جرب كتابة اسم الفيلم بالإنجليزية أو تأكد من الاسم الصحيح."
        )

async def trending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    movies = get_trakt_trending("movies", 5)
    shows  = get_trakt_trending("shows", 5)
    msg = "🎬 الأفلام الأكثر مشاهدة هذا الأسبوع:\n"
    for i, m in enumerate(movies, 1):
        msg += f"  {i}. {m['title']} ({m['year']})\n"
    msg += "\n📺 المسلسلات الأكثر مشاهدة هذا الأسبوع:\n"
    for i, s in enumerate(shows, 1):
        msg += f"  {i}. {s['title']} ({s['year']})\n"
    if not movies and not shows:
        msg = "⚠️ تعذّر جلب قائمة الترند حالياً، حاول لاحقاً."
    await update.message.reply_text(msg)

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_history[update.message.chat_id] = []
    await update.message.reply_text("✅ تم مسح سجل المحادثة.")

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
