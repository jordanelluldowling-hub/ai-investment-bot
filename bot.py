import os
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path

import anthropic
import feedparser
import requests
import schedule

# --- Keys from environment ---
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

PORTFOLIO = """
My current investment portfolio:
- Shell (SHEL) - Oil/Energy stock
- Barrick Gold (GOLD) - Gold mining stock
- Rheinmetall (RHM) - Defense/Aerospace stock
- Bitcoin (BTC) - Cryptocurrency
- BYD (BYDDY) - Electric vehicles stock
- S&P 500 ETF - Broad market exposure
"""

RSS_FEEDS = [
    "https://feeds.reuters.com/reuters/businessNews",
    "https://feeds.bbci.co.uk/news/business/rss.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://oilprice.com/rss/main",
]

KEYWORDS = [
    "oil", "gas", "gold", "silver", "copper", "lithium",
    "OPEC", "energy crisis", "Strait of Hormuz", "crude", "uranium",
    "Middle East", "Israel", "Iran", "Ukraine", "Russia", "China",
    "Taiwan", "conflict", "war", "sanctions", "NATO", "nuclear",
    "interest rate", "Federal Reserve", "Fed", "rate cut", "rate hike",
    "inflation", "recession", "GDP", "bank collapse", "IMF",
    "IPO", "goes public", "merger", "acquisition", "takeover",
    "bankruptcy", "short squeeze", "market crash", "stock surge",
    "SpaceX", "Elon Musk", "Nvidia", "semiconductor", "artificial intelligence",
    "chip shortage", "quantum computing", "Apple", "Microsoft", "Google",
    "Meta", "OpenAI", "robotics", "cybersecurity",
    "BYD", "Tesla", "electric vehicle", "battery", "solar", "hydrogen",
    "defense spending", "Rheinmetall", "Lockheed", "drone", "space race",
    "bitcoin", "crypto", "ethereum", "blockchain", "ETF approval",
    "drug approval", "FDA", "vaccine", "biotech", "pandemic",
    "supply chain", "shipping", "port strike", "food crisis",
    "Shell", "Barrick",
]

CACHE_FILE = Path("seen.json")


def load_seen():
    if CACHE_FILE.exists():
        return set(json.loads(CACHE_FILE.read_text()))
    return set()


def save_seen(seen):
    CACHE_FILE.write_text(json.dumps(list(seen)))


def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")


def ask_claude(prompt):
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text


def check_news():
    print(f"Checking news... {datetime.now().strftime('%H:%M')}")

    if not CLAUDE_API_KEY:
        print("ERROR: CLAUDE_API_KEY not set")
        return
    if not TELEGRAM_TOKEN:
        print("ERROR: TELEGRAM_TOKEN not set")
        return

    seen = load_seen()
    found = 0

    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:10]:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                aid = hashlib.md5(title.encode()).hexdigest()

                if aid in seen:
                    continue

                if any(k.lower() in title.lower() for k in KEYWORDS):
                    print(f"Found: {title}")
                    found += 1

                    portfolio_advice = ask_claude(f"""News: {title}
Summary: {summary}
My Portfolio: {PORTFOLIO}
3 bullet points:
1. IMPACT on my holdings
2. ACTION: buy/sell/hold what specifically
3. URGENCY: HIGH/MEDIUM/LOW and why
Be direct and brief.""")

                    send_telegram(f"PORTFOLIO ALERT\n\n{title}\n\n{portfolio_advice}")
                    time.sleep(1)

                    opportunity = ask_claude(f"""News: {title}
Summary: {summary}
You are a small cap stock analyst.
1. EVENT TYPE: what kind of catalyst?
2. TOP 3 PLAYS: specific stocks/ETFs with tickers that could benefit. Small/mid cap preferred. One sentence each.
3. WHAT TO RESEARCH: 2 most important things to check first.
4. RISK: biggest reason this could go wrong.
5. WINDOW: how long does this opportunity last? (hours/days/weeks)
Be specific with tickers. No preamble.""")

                    send_telegram(f"OPPORTUNITY ALERT\n\n{title}\n\n{opportunity}")

                    seen.add(aid)
                    time.sleep(1)

        except Exception as e:
            print(f"Error with {feed_url}: {e}")

    save_seen(seen)
    print(f"Done. Found {found} relevant articles.")


import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--once", action="store_true")
args = parser.parse_args()

if args.once:
    check_news()
else:
    schedule.every(30).minutes.do(check_news)
    check_news()
    while True:
        schedule.run_pending()
        time.sleep(30)
