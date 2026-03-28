"""
AI Investment News Alert Bot
Monitors RSS news feeds, analyses relevant headlines with Claude,
and sends investment alerts to your Telegram.

Usage:
    python bot.py              # Run continuously (every 30 minutes)
    python bot.py --once       # Run a single check and exit
    python bot.py --test       # Send a test Telegram message and exit
"""

import argparse
import hashlib
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

import anthropic
import feedparser
import requests
import schedule

import config

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log"),
    ],
)
log = logging.getLogger(__name__)

# --- Seen articles cache (prevents duplicate alerts) ---
CACHE_FILE = Path("seen_articles.json")


def load_seen_cache() -> set:
    if CACHE_FILE.exists():
        with open(CACHE_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen_cache(seen: set) -> None:
    with open(CACHE_FILE, "w") as f:
        json.dump(list(seen), f)


def article_id(title: str, link: str) -> str:
    """Stable unique ID for an article."""
    return hashlib.md5(f"{title}{link}".encode()).hexdigest()


# --- News Fetching ---

def fetch_relevant_articles() -> list[dict]:
    """Fetch articles from all RSS feeds that match trigger keywords."""
    seen = load_seen_cache()
    relevant = []

    for feed_url in config.RSS_FEEDS:
        log.info(f"Checking feed: {feed_url}")
        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:
            log.warning(f"Failed to fetch {feed_url}: {e}")
            continue

        for entry in feed.entries[: config.MAX_ITEMS_PER_FEED]:
            title = entry.get("title", "")
            summary = entry.get("summary", entry.get("description", ""))
            link = entry.get("link", "")
            aid = article_id(title, link)

            if aid in seen:
                continue

            if any(kw.lower() in title.lower() or kw.lower() in summary.lower()
                   for kw in config.TRIGGER_KEYWORDS):
                relevant.append({"title": title, "summary": summary, "link": link, "id": aid})

    return relevant


# --- Claude Analysis ---

def analyse_with_claude(title: str, summary: str) -> str:
    """Send article to Claude and get portfolio-specific investment advice."""
    client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)

    prompt = f"""
News Alert: {title}

Summary: {summary}

My Portfolio:
{config.PORTFOLIO}

In exactly 3 bullet points tell me:
1. IMPACT: How does this specifically affect my portfolio holdings?
2. ACTION: Should I buy / sell / hold anything right now? Be specific about which holding.
3. URGENCY: Rate this as HIGH / MEDIUM / LOW and explain why in one sentence.

Be direct and brief. No preamble.
"""

    message = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=config.MAX_RESPONSE_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )

    return message.content[0].text


def urgency_from_analysis(analysis: str) -> str:
    """Extract urgency level from Claude's response."""
    lower = analysis.lower()
    if "urgency: high" in lower or "urgency:** high" in lower or "🔴" in lower:
        return "high"
    if "urgency: medium" in lower or "urgency:** medium" in lower or "🟡" in lower:
        return "medium"
    return "low"


URGENCY_RANK = {"low": 0, "medium": 1, "high": 2}


def urgency_emoji(level: str) -> str:
    return {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(level, "⚪")


# --- Telegram ---

def send_telegram(message: str) -> bool:
    """Send a message to Telegram. Returns True on success."""
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        log.warning("Telegram not configured — printing alert to console instead.")
        print("\n" + "=" * 60)
        print(message)
        print("=" * 60 + "\n")
        return True

    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        log.error(f"Telegram send failed: {e}")
        return False


def format_alert(title: str, analysis: str, link: str, urgency: str) -> str:
    emoji = urgency_emoji(urgency)
    timestamp = datetime.now().strftime("%d %b %Y %H:%M")
    return (
        f"{emoji} <b>INVESTMENT ALERT</b> {emoji}\n"
        f"<i>{timestamp}</i>\n\n"
        f"<b>📰 Headline:</b>\n{title}\n\n"
        f"<b>🤖 AI Analysis:</b>\n{analysis}\n\n"
        f"<a href='{link}'>Read full article</a>"
    )


# --- Main Loop ---

def check_news() -> None:
    log.info("Starting news check...")
    articles = fetch_relevant_articles()

    if not articles:
        log.info("No new relevant articles found.")
        return

    log.info(f"Found {len(articles)} new relevant article(s). Analysing...")
    seen = load_seen_cache()

    for article in articles:
        title = article["title"]
        log.info(f"Analysing: {title}")

        try:
            analysis = analyse_with_claude(title, article["summary"])
        except Exception as e:
            log.error(f"Claude analysis failed for '{title}': {e}")
            seen.add(article["id"])
            continue

        urgency = urgency_from_analysis(analysis)

        if URGENCY_RANK[urgency] >= URGENCY_RANK[config.MIN_URGENCY]:
            alert = format_alert(title, analysis, article["link"], urgency)
            send_telegram(alert)
            log.info(f"Alert sent [{urgency.upper()}]: {title}")
        else:
            log.info(f"Skipped [{urgency.upper()} < min {config.MIN_URGENCY}]: {title}")

        seen.add(article["id"])
        # Small delay between API calls to avoid rate limits
        time.sleep(1)

    save_seen_cache(seen)
    log.info("News check complete.")


def run_test() -> None:
    """Send a test alert to verify Telegram is working."""
    message = (
        "✅ <b>Investment Bot Connected</b>\n\n"
        "Your AI investment alert bot is running correctly.\n"
        "You will receive alerts here when relevant news is detected.\n\n"
        f"<i>Monitoring {len(config.RSS_FEEDS)} feeds | "
        f"{len(config.TRIGGER_KEYWORDS)} keywords | "
        f"Checking every {config.CHECK_INTERVAL_MINUTES} minutes</i>"
    )
    success = send_telegram(message)
    if success:
        print("Test alert sent successfully.")
    else:
        print("Test alert failed. Check your TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in .env")


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Investment News Alert Bot")
    parser.add_argument("--once", action="store_true", help="Run one check and exit")
    parser.add_argument("--test", action="store_true", help="Send test Telegram message and exit")
    args = parser.parse_args()

    if not config.CLAUDE_API_KEY and not args.test:
        log.error("CLAUDE_API_KEY is not set. Copy .env.example to .env and add your key.")
        return

    if args.test:
        run_test()
        return

    if args.once:
        check_news()
        return

    log.info(f"Bot started. Checking news every {config.CHECK_INTERVAL_MINUTES} minutes.")
    send_telegram(
        "🤖 <b>Investment Bot Started</b>\n"
        f"Monitoring {len(config.RSS_FEEDS)} feeds every {config.CHECK_INTERVAL_MINUTES} minutes."
    )

    schedule.every(config.CHECK_INTERVAL_MINUTES).minutes.do(check_news)
    check_news()  # Run immediately on start

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
