import os
import logging
import threading
import requests
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from groq import Groq
from rapidfuzz import fuzz

TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_TOKEN")
TMDB_API_KEY    = os.environ.get("TMDB_API_KEY")
OMDB_API_KEY    = os.environ.get("OMDB_API_KEY")
TRAKT_CLIENT_ID = os.environ.get("TRAKT_CLIENT_ID")
BOT_NAME        = "tztvn"
MODEL_NAME      = os.environ.get("MODEL_NAME", "meta-llama/llama-4-scout-17b-16e-instruct")

GROQ_API_KEYS = [
    os.environ.get("GROQ_API_KEY"),
    os.environ.get("GROQ_API_KEY_1"),
    os.environ.get("GROQ_API_KEY_2"),
    os.environ.get("GROQ_API_KEY_3"),
]
GROQ_API_KEYS = [k for k in dict.fromkeys(GROQ_API_KEYS) if k]

TAVILY_API_KEYS = [
    os.environ.get("TAVILY_API_KEY"),
    os.environ.get("TAVILY_API_KEY_1"),
    os.environ.get("TAVILY_API_KEY_2"),
    os.environ.get("TAVILY_API_KEY_3"),
]
TAVILY_API_KEYS = [k for k in dict.fromkeys(TAVILY_API_KEYS) if k]

logging.basicConfig(level=logging.INFO)

# ── Web Server ──────────────────────────────────────────────────────────────
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"TZTVN Bot is alive!")
    def log_message(self, format, *args):
        pass

threading.Thread(
    target=lambda: HTTPServer(("0.0.0.0", 8080), PingHandler).serve_forever(),
    daemon=True
).start()

# ── System Prompt ───────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
أنت مساعد سينمائي ذكي اسمك tztvn، تعمل في مجموعة تيليجرام.

قواعد أساسية:
- ردودك بالعربية دائماً، واضحة ومنظمة، 4 إلى 8 أسطر.
- لا تبدأ بـ "بالطبع" أو "أهلاً" أو "مرحباً" في كل رد.
- لا تذكر @tztvn إلا إذا سألك أحد صراحةً عن المنصة أو روابط المشاهدة.
- إذا وصلتك بيانات فيلم، قدّمها بأسلوب محادثة طبيعي وحماس — لا تنسخ المعلومات حرفياً.
- إذا كان التقييم عالياً عبّر عن حماسك، وإذا كان منخفضاً كن صريحاً.
- إذا لم تجد الفيلم، قل ذلك بصراحة واقترح بديلاً مشابهاً.
- إذا أُرسلت لك اقتراحات "هل تقصد؟" فاعرضها بشكل واضح للمستخدم.
- إذا وصلك سياق من بحث ويب، استخدمه فقط كما هو ولا تخترع معلومات غير موجودة فيه.
- عند الأسئلة عن الأخبار الجديدة أو موعد النزول أو حالة الإصدار، اعتمد على بحث الويب إذا توفر.
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

# ── Fuzzy Helpers ────────────────────────────────────────────────────────────
REMOVE_WORDS = [
    "فيلم","مسلسل","سيريال","انمي","anime","movie","film","series","show",
    "season","episode","هل نزل","هل طلع","هل اصدر","هل صدر","متى ينزل",
    "متى يطلع","متى نزل","موعد","الجزء","سيزون","موسم","هل","نزل","طلع",
    "اصدر","صدر","ينزل","يطلع","اخبرني عن","ما هو","ما هي","اعطني معلومات عن",
    "is","out","has","when","does","the","released","release","tell me about",
    "@tztvn","tztvn","watch","actor","director","مخرج","ممثل","تقييم"
]

def normalize_title(text: str) -> str:
    if not text:
        return ""
    result = text.lower().strip()
    for w in REMOVE_WORDS:
        result = result.replace(w.lower(), " ")
    return " ".join(result.split())

def fuzzy_score(query: str, candidate: str) -> int:
    q = normalize_title(query)
    c = normalize_title(candidate)
    if not q or not c:
        return 0
    return max(
        fuzz.ratio(q, c),
        fuzz.partial_ratio(q, c),
        fuzz.token_sort_ratio(q, c),
        fuzz.token_set_ratio(q, c),
    )

# ── OMDb: بحث متعدد النتائج أولاً ───────────────────────────────────────────
def omdb_search_list(query: str) -> list:
    if not OMDB_API_KEY:
        return []
    try:
        r = requests.get(
            "http://www.omdbapi.com/",
            params={"apikey": OMDB_API_KEY, "s": query, "page": 1},
            timeout=10
        )
        data = r.json()
        results = []
        for item in data.get("Search", []):
            title   = item.get("Title", "")
            year    = item.get("Year", "")
            imdb_id = item.get("imdbID", "")
            score   = fuzzy_score(query, title)
            results.append({"title": title, "year": year, "imdb_id": imdb_id, "score": score})
        results.sort(key=lambda x: x["score"], reverse=True)
        return results
    except Exception as e:
        logging.error(f"OMDb search list error: {e}")
        return []

def omdb_get_by_id(imdb_id: str) -> dict:
    if not OMDB_API_KEY or not imdb_id:
        return {}
    try:
        r = requests.get(
            "http://www.omdbapi.com/",
            params={"apikey": OMDB_API_KEY, "i": imdb_id, "plot": "short"},
            timeout=8
        )
        data = r.json()
        if data.get("Response") != "True":
            return {}
        result = {
            "title": data.get("Title", ""),
            "year": data.get("Year", ""),
            "genre": data.get("Genre", ""),
            "director": data.get("Director", ""),
            "actors": data.get("Actors", ""),
            "runtime": data.get("Runtime", ""),
            "plot": data.get("Plot", ""),
            "imdb_id": data.get("imdbID", ""),
            "imdb_rating": "",
            "rt_rating": "",
        }
        for rating in data.get("Ratings", []):
            src = rating.get("Source", "")
            val = rating.get("Value", "")
            if "Internet Movie Database" in src:
                result["imdb_rating"] = val
            elif "Rotten Tomatoes" in src:
                result["rt_rating"] = val
        return result
    except Exception as e:
        logging.error(f"OMDb get by id error: {e}")
        return {}

# ── TMDb: بحث متعدد اللغات ──────────────────────────────────────────────────
def tmdb_search_list(query: str) -> list:
    if not TMDB_API_KEY:
        return []
    try:
        seen_ids = set()
        results = []
        for lang in ["ar", "en-US", "fr-FR"]:
            r = requests.get(
                "https://api.themoviedb.org/3/search/multi",
                params={"api_key": TMDB_API_KEY, "query": query, "language": lang, "page": 1},
                timeout=10
            )
            for item in r.json().get("results", []):
                media_type = item.get("media_type")
                if media_type not in ["movie", "tv"]:
                    continue
                tmdb_id = item.get("id")
                if tmdb_id in seen_ids:
                    continue
                seen_ids.add(tmdb_id)
                title = (
                    item.get("title") or item.get("name")
                    or item.get("original_title") or item.get("original_name") or ""
                )
                aliases = list(dict.fromkeys(filter(None, [
                    item.get("title"), item.get("name"),
                    item.get("original_title"), item.get("original_name")
                ])))
                score = max([fuzzy_score(query, a) for a in aliases] or [0])
                year = (item.get("release_date") or item.get("first_air_date") or "")[:4]
                results.append({
                    "tmdb_id": tmdb_id,
                    "media_type": media_type,
                    "title": title,
                    "year": year,
                    "aliases": aliases,
                    "score": score,
                    "overview": item.get("overview", ""),
                    "vote": item.get("vote_average", 0),
                })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results
    except Exception as e:
        logging.error(f"TMDb search list error: {e}")
        return []

def tmdb_get_details(tmdb_id: int, media_type: str) -> dict:
    if not TMDB_API_KEY:
        return {}
    try:
        det = requests.get(
            f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/external_ids",
            params={"api_key": TMDB_API_KEY}, timeout=8
        ).json()
        imdb_id = det.get("imdb_id", "")
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
        except Exception:
            pass
        return {"imdb_id": imdb_id, "watch": watch}
    except Exception as e:
        logging.error(f"TMDb get details error: {e}")
        return {}

def get_justwatch(imdb_id_or_query: str) -> str:
    try:
        base = "https://imdb.iamidiotareyoutoo.com"
        r = requests.get(f"{base}/justwatch", params={"q": imdb_id_or_query}, timeout=10)
        jw_data = r.json()
        providers = []
        items_list = jw_data if isinstance(jw_data, list) else [jw_data]
        for item in items_list:
            name = item.get("provider_name") or item.get("name", "")
            if name:
                providers.append(name)
        if providers:
            return " | ".join(f"▶️ {p}" for p in providers[:5])
    except Exception:
        pass
    return ""

CONFIDENCE_HIGH = 75
CONFIDENCE_MEDIUM = 50

def smart_movie_search(query: str) -> dict:
    clean_query = normalize_title(query)
    if not clean_query:
        return {"status": "not_found"}

    omdb_candidates = omdb_search_list(clean_query)
    if omdb_candidates:
        best = omdb_candidates[0]
        if best["score"] >= CONFIDENCE_HIGH:
            detail = omdb_get_by_id(best["imdb_id"])
            if detail:
                jw = get_justwatch(best["imdb_id"])
                return {"status": "found", "card": _build_omdb_card(detail, jw)}
        if best["score"] >= CONFIDENCE_MEDIUM:
            suggestions = [f"{c['title']} ({c['year']})" for c in omdb_candidates[:3]]
            return {"status": "suggestions", "suggestions": suggestions, "query": query}

    tmdb_candidates = tmdb_search_list(clean_query)
    if tmdb_candidates:
        best = tmdb_candidates[0]
        if best["score"] >= CONFIDENCE_HIGH:
            extra = tmdb_get_details(best["tmdb_id"], best["media_type"])
            omdb_detail = {}
            if extra.get("imdb_id"):
                omdb_detail = omdb_get_by_id(extra["imdb_id"])
            return {"status": "found", "card": _build_tmdb_card(best, extra, omdb_detail)}
        if best["score"] >= CONFIDENCE_MEDIUM:
            suggestions = [f"{c['title']} ({c['year']})" for c in tmdb_candidates[:3]]
            return {"status": "suggestions", "suggestions": suggestions, "query": query}

    return {"status": "not_found"}

def _build_omdb_card(d: dict, jw: str = "") -> str:
    lines = []
    title = d.get("title", "")
    year = d.get("year", "")
    lines.append(f"🎬 {title} ({year})" if year else f"🎬 {title}")
    if d.get("genre"):
        lines.append(f"🎭 {d['genre']}")
    if d.get("director"):
        lines.append(f"🎥 المخرج: {d['director']}")
    if d.get("runtime"):
        lines.append(f"⏱️ المدة: {d['runtime']}")
    ratings = []
    if d.get("imdb_rating"):
        ratings.append(f"⭐ IMDb: {d['imdb_rating']}")
    if d.get("rt_rating"):
        ratings.append(f"🍅 RT: {d['rt_rating']}")
    if ratings:
        lines.append(" | ".join(ratings))
    if jw:
        lines.append(f"📺 شاهده على: {jw}")
    else:
        lines.append("📺 غير متوفر حالياً على منصات البث")
    plot = d.get("plot", "")
    if plot:
        lines.append(f"📝 {plot[:220]}{'...' if len(plot) > 220 else ''}")
    return "\n".join(lines)

def _build_tmdb_card(item: dict, extra: dict, omdb: dict) -> str:
    lines = []
    title = item.get("title", "")
    year = item.get("year", "")
    type_ar = "مسلسل" if item.get("media_type") == "tv" else "فيلم"
    lines.append(f"🎬 [{type_ar}] {title} ({year})" if year else f"🎬 [{type_ar}] {title}")
    if omdb.get("genre"):
        lines.append(f"🎭 {omdb['genre']}")
    if omdb.get("director"):
        lines.append(f"🎥 المخرج: {omdb['director']}")
    if omdb.get("runtime"):
        lines.append(f"⏱️ المدة: {omdb['runtime']}")
    ratings = []
    vote = item.get("vote", 0)
    if vote:
        ratings.append(f"⭐ TMDb: {vote}/10")
    if omdb.get("imdb_rating"):
        ratings.append(f"🎭 IMDb: {omdb['imdb_rating']}")
    if omdb.get("rt_rating"):
        ratings.append(f"🍅 RT: {omdb['rt_rating']}")
    if ratings:
        lines.append(" | ".join(ratings))
    watch = extra.get("watch", "")
    if watch:
        lines.append(f"📺 شاهده على: {watch}")
    else:
        lines.append("📺 غير متوفر حالياً على منصات البث")
    overview = item.get("overview", "") or omdb.get("plot", "")
    if overview:
        lines.append(f"📝 {overview[:220]}{'...' if len(overview) > 220 else ''}")
    return "\n".join(lines)

def get_trakt_trending(media_type: str = "movies", limit: int = 5) -> list:
    try:
        r = requests.get(
            f"https://api.trakt.tv/{media_type}/trending",
            headers={
                "Content-Type": "application/json",
                "trakt-api-version": "2",
                "trakt-api-key": TRAKT_CLIENT_ID
            },
            params={"limit": limit},
            timeout=10
        )
        results = []
        for item in r.json()[:limit]:
            obj = item.get("movie") or item.get("show") or {}
            results.append({"title": obj.get("title", ""), "year": obj.get("year", "")})
        return results
    except Exception as e:
        logging.error(f"Trakt error: {e}")
        return []

SEARCH_NEEDED_KEYWORDS = [
    "خبر", "أخبار", "جديد", "جديده", "جديدة", "اليوم", "الان", "الآن", "حديث",
    "مؤخراً", "مؤخرًا", "متى ينزل", "موعد النزول", "موعد الاصدار", "إصدار", "اصدار",
    "released", "release date", "latest", "news", "update", "updates", "streaming now"
]

def needs_web_search(text: str) -> bool:
    lowered = text.lower()
    return any(k.lower() in lowered for k in SEARCH_NEEDED_KEYWORDS)

def tavily_web_search(query: str) -> str:
    if not TAVILY_API_KEYS:
        return ""
    for key in TAVILY_API_KEYS:
        try:
            r = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": key,
                    "query": query,
                    "search_depth": "advanced",
                    "topic": "general",
                    "max_results": 5,
                    "include_answer": True,
                    "include_raw_content": False,
                },
                timeout=20,
            )
            if r.status_code == 200:
                data = r.json()
                lines = []
                if data.get("answer"):
                    lines.append(f"ملخص البحث: {data['answer']}")
                for item in data.get("results", [])[:5]:
                    title = item.get("title", "")
                    url = item.get("url", "")
                    content = (item.get("content", "") or "")[:300]
                    lines.append(f"- {title}\n  {content}\n  المصدر: {url}")
                if lines:
                    return "[نتائج بحث الويب]\n" + "\n".join(lines)
            elif r.status_code in (401, 429):
                continue
        except Exception as e:
            logging.error(f"Tavily error with key rotation: {e}")
            continue
    return ""

def call_groq(messages: list):
    last_error = None
    for key in GROQ_API_KEYS:
        try:
            client = Groq(api_key=key)
            return client.chat.completions.create(
                model=MODEL_NAME,
                temperature=0.7,
                messages=messages,
            )
        except Exception as e:
            last_error = e
            logging.error(f"Groq key failed, trying next key: {e}")
            continue
    raise last_error if last_error else RuntimeError("No Groq API key configured")

groq_client = None
chat_history = {}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    chat_id = update.message.chat_id
    user_name = update.message.from_user.first_name or "عضو"
    text = update.message.text

    if contains_banned(text):
        await update.message.reply_text("⚠️ رسالتك تحتوي على محتوى مخالف. يرجى الالتزام باللياقة 🙏")
        return

    if chat_id not in chat_history:
        chat_history[chat_id] = []

    bot_me = await context.bot.get_me()
    mentioned = f"@{bot_me.username}" in text or BOT_NAME.lower() in text.lower()
    is_private = update.message.chat.type == "private"

    if not (mentioned or is_private):
        chat_history[chat_id].append({"role": "user", "content": f"{user_name}: {text}"})
        return

    clean_text = text.replace(f"@{bot_me.username}", "").replace("tztvn", "").strip()

    movie_context = ""
    search_query = normalize_title(clean_text)

    if search_query and len(search_query) >= 2:
        result = smart_movie_search(search_query)
        if result["status"] == "found":
            movie_context = f"[بيانات الفيلم من قواعد البيانات:]\n{result['card']}"
        elif result["status"] == "suggestions":
            sug = result["suggestions"]
            sug_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(sug))
            movie_context = (
                f"[لم أجد نتيجة مؤكدة لـ '{result['query']}'، أقرب الاقتراحات:]\n"
                f"{sug_text}\n"
                "[اطلب من المستخدم التأكيد: هل تقصد أحد هذه؟]"
            )
        else:
            movie_context = f"[لم يُعثر على فيلم أو مسلسل بهذا الاسم: '{search_query}']"

    web_context = ""
    if needs_web_search(clean_text):
        web_context = tavily_web_search(clean_text)

    user_message = f"{user_name}: {clean_text}"
    if movie_context:
        user_message += f"\n\n{movie_context}"
    if web_context:
        user_message += f"\n\n{web_context}"

    chat_history[chat_id].append({"role": "user", "content": user_message})

    try:
        response = call_groq([
            {"role": "system", "content": SYSTEM_PROMPT},
            *chat_history[chat_id][-20:]
        ])
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
        "وأقدر أبحث لك عن الأخبار الجديدة وموعد النزول أيضاً.\n"
        "جرب: /search Inception أو /trending"
    )

async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("🔍 مثال: /search Inception")
        return
    query = " ".join(context.args)
    await update.message.reply_text("🔍 جاري البحث...")
    result = smart_movie_search(query)
    if result["status"] == "found":
        await update.message.reply_text(result["card"])
    elif result["status"] == "suggestions":
        sug = result["suggestions"]
        msg = f"🤔 لم أجد '{query}' بالضبط، هل تقصد:\n"
        for i, s in enumerate(sug, 1):
            msg += f"  {i}. {s}\n"
        msg += "\nأرسل الاسم مرة أخرى بشكل أوضح 😊"
        await update.message.reply_text(msg)
    else:
        await update.message.reply_text(
            f"❌ لم أجد معلومات عن '{query}'.\n"
            "جرب كتابة الاسم بالإنجليزية أو تأكد من الاسم الصحيح."
        )

async def trending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    movies = get_trakt_trending("movies", 5)
    shows = get_trakt_trending("shows", 5)
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
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("search", search_cmd))
    app.add_handler(CommandHandler("trending", trending_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ TZTVN Bot يعمل الآن!")
    app.run_polling()

if __name__ == "__main__":
    main()
