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
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "3600"))

SEEN_FILE = "seen.json"

FEEDS = [
    {"url": "https://feeds.bbci.co.uk/news/world/rss.xml", "name": "BBC World"},
    {"url": "https://www.odditycentral.com/feed", "name": "Oddity Central"},
    {"url": "https://feeds.bbci.co.uk/sport/football/rss.xml", "name": "BBC Sport"},
    {"url": "https://www.sciencedaily.com/rss/strange_offbeat.xml", "name": "ScienceDaily"},
    {"url": "https://www.sciencedaily.com/rss/plants_animals/animals.xml", "name": "Animals"},
]

VIRAL_KEYWORDS = [
    "record","first time","viral","shocking","unexpected","incredible",
    "million","world cup","goal","saves","goalkeeper","fans",
    "animal","bear","whale","koala","dog","cat","lion","shark",
    "rescue","saved","miracle","amazing","unbelievable",
    "robot","ai","discovery","found","mystery",
    "fight","crash","fire","flood",
]

NEGATIVE_KEYWORDS = [
    "election","politics","murder","terror","attack","weapon",
    "stock","market","economy","finance","tax",
]

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen)[-500:], f)

def entry_id(entry):
    return hashlib.md5((entry.get("link","") + entry.get("title","")).encode()).hexdigest()

def score_entry(entry):
    title = (entry.get("title","") + " " + entry.get("summary","")).lower()
    score = 0
    for kw in VIRAL_KEYWORDS:
        if kw.lower() in title:
            score += 1
    for kw in NEGATIVE_KEYWORDS:
        if kw.lower() in title:
            score -= 3
    return score

def format_message(entry, source_name, score):
    title = entry.get("title","Без названия")
    link = entry.get("link","")
    summary = entry.get("summary","")
    summary = summary[:200] + "..." if len(summary) > 200 else summary
    stars = "🔥" * min(score, 5)
    short = title[:60] + "..." if len(title) > 60 else title
    return f"""{stars} *{short}*

📌 {source_name}
🔗 {link}

📝 {summary}"""

async def check_feeds(context: ContextTypes.DEFAULT_TYPE):
    bot = context.bot
    seen = load_seen()
    new_items = []
    for feed_info in FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            for entry in feed.entries[:10]:
                eid = entry_id(entry)
                if eid in seen:
                    continue
                score = score_entry(entry)
                if score >= 2:
                    new_items.append((score, entry, feed_info["name"]))
                seen.add(eid)
        except Exception as e:
            logger.error(f"Feed error {feed_info['name']}: {e}")
    save_seen(seen)
    new_items.sort(key=lambda x: x[0], reverse=True)
    if not new_items:
        return
    for score, entry, source in new_items[:5]:
        try:
            msg = format_message(entry, source, score)
            await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown", disable_web_page_preview=False)
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Send error: {e}")

async def start(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔥 *VIRAL ФАКТОР бот запущен!*\n\n/check — проверить сейчас\n/status — статус", parse_mode="Markdown")

async def check_now(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Проверяю...")
    await check_feeds(context)
    await update.message.reply_text("✅ Готово!")

async def status(update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"✅ Работает\n⏱ Каждые {CHECK_INTERVAL//60} мин\n📡 Источников: {len(FEEDS)}\n🕐 {datetime.now(timezone.utc).strftime('%H:%M UTC')}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check_now))
    app.add_handler(CommandHandler("status", status))
    app.job_queue.run_repeating(check_feeds, interval=CHECK_INTERVAL, first=60)
    logger.info("Bot started!")
    app.run_polling()

if __name__ == "__main__":
    main()
