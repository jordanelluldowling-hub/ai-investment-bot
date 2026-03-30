"""
AI Investment News Alert Bot
Monitors RSS news feeds, analyses relevant headlines with Claude,
and sends two types of alerts to Telegram:
  1. PORTFOLIO ALERT  — impact on your existing holdings
  2. OPPORTUNITY ALERT — small/mid cap stocks that could benefit from the event

Usage:
    python bot.py              # Run continuously (every 30 minutes)
    python bot.py --once       # Run a single check and exit
    python bot.py --test       # Send a test Telegram message and exit
"""

import argparse
import hashlib
import json
import logging
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
    return hashlib.md5(f"{title}{link}".encode()).hexdigest()


# --- News Fetching ---

def fetch_relevant_articles() -> list[dict]:
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

def analyse_portfolio_impact(title: str, summary: str) -> str:
    """How does this news affect existing holdings?"""
    client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)
    message = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=config.MAX_RESPONSE_TOKENS,
        messages=[{"role": "user", "content": f"""
News: {title}
Summary: {summary}

My Portfolio:
{config.PORTFOLIO}

In exactly 3 bullet points:
1. IMPACT: How does this affect my specific holdings?
2. ACTION: Buy / sell / hold — which holding specifically and why?
3. URGENCY: HIGH / MEDIUM / LOW and one sentence why.

Be direct. No preamble.
"""}],
    )
    return message.content[0].text


def find_opportunity_plays(title: str, summary: str) -> str:
    """What small/mid cap stocks could benefit most from this event?"""
    client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)
    message = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=config.MAX_RESPONSE_TOKENS,
        messages=[{"role": "user", "content": f"""
This major news just broke:
{title}

Summary: {summary}

You are a small cap stock analyst. The investor will spend 20 minutes researching
before deciding whether to invest. Give them the best starting point.

Answer in exactly this format:
1. EVENT TYPE: What kind of catalyst is this? (geopolitical / IPO / sector boom / macro / other)
2. TOP 3 PLAYS: Specific stocks or ETFs with ticker symbols that could benefit most.
   Prioritise small/mid cap with high upside. One sentence per pick explaining why.
3. WHAT TO RESEARCH: The 2 most important things to check before investing.
4. RISK: Biggest reason this play could go wrong. One sentence.
5. WINDOW: How long does this opportunity likely last? (hours / days / weeks)

Be specific with tickers. No preamble.
"""}],
    )
    return message.content[0].text


def urgency_from_analysis(analysis: str) -> str:
    lower = analysis.lower()
    if "urgency: high" in lower or "high" in lower[:200]:
        return "high"
    if "urgency: medium" in lower or "medium" in lower[:200]:
        return "medium"
    return "low"


URGENCY_RANK = {"low": 0, "medium": 1, "high": 2}


def urgency_emoji(level: str) -> str:
    return {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(level, "⚪")


# --- Telegram ---

def send_telegram(message: str) -> bool:
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        log.warning("Telegram not configured — printing to console.")
        print("\n" + "=" * 60)
        print(message)
        print("=" * 60 + "\n")
        return True

    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": message},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        log.error(f"Telegram send failed: {e}")
        return False


def format_portfolio_alert(title: str, analysis: str, link: str, urgency: str) -> str:
    emoji = urgency_emoji(urgency)
    timestamp = datetime.now().strftime("%d %b %Y %H:%M")
    return (
        f"{emoji} PORTFOLIO ALERT {emoji}\n"
        f"{timestamp}\n\n"
        f"NEWS: {title}\n\n"
        f"YOUR HOLDINGS:\n{analysis}\n\n"
        f"{link}"
    )


def format_opportunity_alert(title: str, analysis: str, link: str) -> str:
    timestamp = datetime.now().strftime("%d %b %Y %H:%M")
    return (
        f"💰 OPPORTUNITY ALERT 💰\n"
        f"{timestamp}\n\n"
        f"NEWS: {title}\n\n"
        f"STOCKS TO RESEARCH:\n{analysis}\n\n"
        f"{link}"
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
            # Alert 1 — impact on existing portfolio
            portfolio_analysis = analyse_portfolio_impact(title, article["summary"])
            urgency = urgency_from_analysis(portfolio_analysis)

            if URGENCY_RANK[urgency] >= URGENCY_RANK[config.MIN_URGENCY]:
                alert = format_portfolio_alert(title, portfolio_analysis, article["link"], urgency)
                send_telegram(alert)
                log.info(f"Portfolio alert sent [{urgency.upper()}]: {title}")

            time.sleep(1)

            # Alert 2 — opportunity plays for manual research + investing
            opportunity_analysis = find_opportunity_plays(title, article["summary"])
            opp_alert = format_opportunity_alert(title, opportunity_analysis, article["link"])
            send_telegram(opp_alert)
            log.info(f"Opportunity alert sent: {title}")

        except Exception as e:
            log.error(f"Analysis failed for '{title}': {e}")

        seen.add(article["id"])
        time.sleep(1)

    save_seen_cache(seen)
    log.info("News check complete.")


def run_test() -> None:
    message = (
        "Investment Bot Connected\n\n"
        "Your AI investment alert bot is running.\n"
        "For every major news event you will get:\n\n"
        "1. PORTFOLIO ALERT — impact on your existing holdings\n"
        "2. OPPORTUNITY ALERT — small cap stocks to research and potentially invest in\n\n"
        f"Monitoring {len(config.RSS_FEEDS)} feeds | "
        f"{len(config.TRIGGER_KEYWORDS)} keywords | "
        f"Checking every {config.CHECK_INTERVAL_MINUTES} minutes"
    )
    success = send_telegram(message)
    if success:
        print("Test alert sent successfully.")
    else:
        print("Test alert failed. Check your TELEGRAM_TOKEN and TELEGRAM_CHAT_ID.")


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Investment News Alert Bot")
    parser.add_argument("--once", action="store_true", help="Run one check and exit")
    parser.add_argument("--test", action="store_true", help="Send test Telegram message and exit")
    args = parser.parse_args()

    if not config.CLAUDE_API_KEY and not args.test:
        log.error("CLAUDE_API_KEY is not set in config.py")
        return

    if args.test:
        run_test()
        return

    if args.once:
        check_news()
        return

    log.info(f"Bot started. Checking every {config.CHECK_INTERVAL_MINUTES} minutes.")
    send_telegram(
        "Investment Bot Started\n"
        f"Monitoring {len(config.RSS_FEEDS)} feeds every {config.CHECK_INTERVAL_MINUTES} minutes.\n"
        "You will get PORTFOLIO alerts + OPPORTUNITY alerts for every major event."
    )

    schedule.every(config.CHECK_INTERVAL_MINUTES).minutes.do(check_news)
    check_news()

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
