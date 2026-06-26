import os
import json
import hashlib
import asyncio
import feedparser
import logging
from datetime import datetime, timezone
from telegram import Bot
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = int(os.environ["CHAT_ID"])
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "3600"))  # каждый час

SEEN_FILE = "seen.json"

# RSS источники
FEEDS = [
    # Reddit животные с поведением
    {"url": "https://www.reddit.com/r/aww/.rss", "name": "Reddit aww"},
    {"url": "https://www.reddit.com/r/AnimalsBeingBros/.rss", "name": "Reddit AnimalsBeingBros"},
    {"url": "https://www.reddit.com/r/AnimalsBeingDerps/.rss", "name": "Reddit AnimalsBeingDerps"},
    # Reddit люди в неожиданных ситуациях
    {"url": "https://www.reddit.com/r/Unexpected/.rss", "name": "Reddit Unexpected"},
    {"url": "https://www.reddit.com/r/HumansBeingBros/.rss", "name": "Reddit HumansBeingBros"},
    {"url": "https://www.reddit.com/r/mildlyinteresting/.rss", "name": "Reddit mildlyinteresting"},
    {"url": "https://www.reddit.com/r/nextfuckinglevel/.rss", "name": "Reddit nextfuckinglevel"},
    {"url": "https://www.reddit.com/r/BeAmazed/.rss", "name": "Reddit BeAmazed"},
    {"url": "https://www.reddit.com/r/interestingasfuck/.rss", "name": "Reddit interestingasfuck"},
    {"url": "https://www.reddit.com/r/OldPeopleFacebook/.rss", "name": "Reddit OldPeople"},
    {"url": "https://www.reddit.com/r/KidsAreFuckingStupid/.rss", "name": "Reddit Kids"},
    # Русскоязычные
    {"url": "https://pikabu.ru/xmlfeeds.php?cmd=popular", "name": "Пикабу Горячее"},
    {"url": "https://fishki.net/rss.xml", "name": "Фишки"},
]

# Ключевые слова которые повышают вирусный потенциал
VIRAL_KEYWORDS = [
    # English
    "record", "first time", "viral", "shocking", "unexpected", "incredible",
    "million", "world cup", "goal", "saves", "goalkeeper", "fans",
    "animal", "bear", "whale", "koala", "dog", "cat", "lion", "shark",
    "rescue", "saved", "miracle", "amazing", "unbelievable",
    "robot", "ai", "discovery", "found", "mystery",
    "fight", "crash", "explosion", "fire", "flood", "genius", "escape",
    # Русские
    "рекорд", "впервые", "вирусный", "неожиданно", "миллион",
    "животное", "медведь", "кит", "акула", "лев", "спас", "чудо",
    "побег", "взрыв", "пожар", "находка", "открытие", "невероятно",
    "уникальный", "феномен", "шокирующий", "удивительный", "невероятный",
]

NEGATIVE_KEYWORDS = [
    "политик", "выборы", "война", "убийство", "теракт",
    "election", "politics", "murder", "terror", "attack", "weapon",
    "stock", "market", "economy", "finance", "tax",
]

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen)[-500:], f)  # храним последние 500

def entry_id(entry):
    return hashlib.md5((entry.get("link", "") + entry.get("title", "")).encode()).hexdigest()

def score_entry(entry):
    title = (entry.get("title", "") + " " + entry.get("summary", "")).lower()
    score = 0
    for kw in VIRAL_KEYWORDS:
        if kw.lower() in title:
            score += 1
    for kw in NEGATIVE_KEYWORDS:
        if kw.lower() in title:
            score -= 3
    return score

def make_hook(title):
    """Генерирует простой хук на основе заголовка"""
    title_clean = title.strip()
    hooks = [
        f"«{title_clean}» — вот что происходит...",
        f"Это случилось прямо сейчас: {title_clean}",
        f"Весь интернет говорит об этом: {title_clean}",
    ]
    import random
    return random.choice(hooks)

def format_message(entry, source_name, score):
    title = entry.get("title", "Без названия")
    link = entry.get("link", "")
    summary = entry.get("summary", "")[:200] + "..." if len(entry.get("summary", "")) > 200 else entry.get("summary", "")
    
    stars = "🔥" * min(score, 5) if score > 0 else "📰"
    
    short_title = title[:50] + "..." if len(title) > 50 else title
    
    msg = f"""{stars} *{short_title}*

📌 Источник: {source_name}
🔗 {link}

📝 {summary}

🎬 Хук для видео:
_{make_hook(title)}_"""
    
    return msg

async def check_feeds(context: ContextTypes.DEFAULT_TYPE):
    bot = context.bot
    seen = load_seen()
    new_items = []

    for feed_info in FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            for entry in feed.entries[:10]:  # последние 10 новостей
                eid = entry_id(entry)
                if eid in seen:
                    continue
                score = score_entry(entry)
                if score >= 1:  # минимум 1 вирусное ключевое слово
                    new_items.append((score, entry, feed_info["name"]))
                seen.add(eid)
        except Exception as e:
            logger.error(f"Ошибка парсинга {feed_info['name']}: {e}")

    save_seen(seen)

    # Сортируем по score — сначала самые вирусные
    new_items.sort(key=lambda x: x[0], reverse=True)

    if not new_items:
        logger.info("Новых вирусных новостей нет")
        return

    # Отправляем максимум 5 за раз чтобы не спамить
    for score, entry, source in new_items[:5]:
        try:
            msg = format_message(entry, source, score)
            await bot.send_message(
                chat_id=CHAT_ID,
                text=msg,
                parse_mode="Markdown",
                disable_web_page_preview=False
            )
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Ошибка отправки: {e}")

async def start(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔥 *VIRAL ФАКТОР — Бот новостей*\n\n"
        "Я слежу за вирусными новостями и присылаю тебе горячие темы каждый час.\n\n"
        "Команды:\n"
        "/check — проверить прямо сейчас\n"
        "/status — статус бота",
        parse_mode="Markdown"
    )

async def check_now(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Проверяю новости прямо сейчас...")
    await check_feeds(context)
    await update.message.reply_text("✅ Готово!")

async def status(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"✅ Бот работает\n"
        f"⏱ Проверка каждые {CHECK_INTERVAL // 60} минут\n"
        f"📡 Источников: {len(FEEDS)}\n"
        f"🕐 Сейчас: {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
    )

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check_now))
    app.add_handler(CommandHandler("status", status))
    
    # Проверка каждый час
    app.job_queue.run_repeating(check_feeds, interval=CHECK_INTERVAL, first=60)
    
    logger.info("Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
