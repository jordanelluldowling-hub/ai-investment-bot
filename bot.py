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

# --- Your Portfolio ---
PORTFOLIO = """
TIER 1 - CORE (never sell):
- Nvidia (NVDA) - AI infrastructure
- Bitcoin (BTC) - Crypto
- Rheinmetall (RHM) - Defense

TIER 2 - HIGH CONVICTION:
- Palantir (PLTR) - AI + government
- IonQ (IONQ) - Quantum computing
- Rocket Lab (RKLB) - Space
- Tempus AI (TEM) - AI healthcare
- Cloudflare (NET) - Cybersecurity

TIER 3 - MOONSHOTS:
- SoundHound AI (SOUN) - Voice AI
- Serve Robotics (SERV) - Delivery robots
- Archer Aviation (ACHR) - Flying taxis
- Recursion Pharma (RXRX) - AI drug discovery

Monthly budget: €500
Strategy: Buy dips, hold 5 years, never sell Tier 1
"""

# --- Your current tickers (for direct monitoring) ---
PORTFOLIO_TICKERS = [
    "Nvidia", "NVDA", "Bitcoin", "BTC",
    "Rheinmetall", "RHM", "Palantir", "PLTR",
    "IonQ", "IONQ", "Rocket Lab", "RKLB",
    "Tempus AI", "TEM", "Cloudflare", "NET",
    "SoundHound", "SOUN", "Serve Robotics", "SERV",
    "Archer Aviation", "ACHR", "Recursion", "RXRX",
]

# --- Broad opportunity keywords ---
OPPORTUNITY_KEYWORDS = [
    # AI & Tech
    "artificial intelligence", "AI boom", "AI chip", "machine learning",
    "semiconductor", "quantum computing", "robotics", "automation",
    "data centre", "OpenAI", "Microsoft", "Google", "Meta", "Apple",
    # Space & Defense
    "SpaceX", "space race", "NASA", "satellite", "defense spending",
    "NATO", "military contract", "drone", "Lockheed", "arms",
    # Energy & Commodities
    "oil", "gas", "gold", "silver", "lithium", "uranium", "nuclear",
    "OPEC", "energy crisis", "hydrogen", "solar", "Strait of Hormuz",
    # Macro
    "interest rate", "Federal Reserve", "Fed", "rate cut", "rate hike",
    "inflation", "recession", "bank collapse", "IMF", "central bank",
    # Geopolitical
    "Middle East", "Israel", "Iran", "Ukraine", "Russia", "China",
    "Taiwan", "sanctions", "war", "conflict", "nuclear",
    # Deals & Markets
    "IPO", "goes public", "merger", "acquisition", "takeover",
    "bankruptcy", "short squeeze", "market crash", "stock surge",
    # Biotech & Health
    "drug approval", "FDA", "cancer", "vaccine", "biotech", "pandemic",
    # Crypto
    "bitcoin", "crypto", "ethereum", "ETF approval", "crypto regulation",
    # Emerging themes
    "flying taxi", "electric vehicle", "BYD", "Tesla",
    "supply chain", "port strike", "food crisis",
]

ALL_KEYWORDS = list(set(PORTFOLIO_TICKERS + OPPORTUNITY_KEYWORDS))

RSS_FEEDS = [
    "https://feeds.reuters.com/reuters/businessNews",
    "https://feeds.bbci.co.uk/news/business/rss.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://oilprice.com/rss/main",
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
        resp = requests.post(
            url,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message},
            timeout=10
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"Telegram error: {e}")


def ask_claude(prompt):
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text


def is_portfolio_stock(title, summary):
    text = (title + " " + summary).lower()
    return any(ticker.lower() in text for ticker in PORTFOLIO_TICKERS)


def analyse_portfolio_impact(title, summary):
    return ask_claude(f"""News: {title}
Summary: {summary}

My Portfolio:
{PORTFOLIO}

In exactly 3 bullet points:
1. IMPACT: Which of my specific holdings does this affect and how?
2. ACTION: Buy more / hold / trim — which holding and why?
3. URGENCY: HIGH / MEDIUM / LOW and one sentence why.

Be direct. No preamble.""")


def find_opportunity_plays(title, summary):
    return ask_claude(f"""News: {title}
Summary: {summary}

My existing portfolio:
{PORTFOLIO}

You are an elite small/mid cap stock analyst hunting for the next Nvidia-style opportunity.
The investor has a 5 year horizon and will buy dips aggressively.

Answer in exactly this format:
1. EVENT TYPE: What kind of catalyst is this?
2. TOP 3 PLAYS: Specific stocks NOT already in my portfolio with ticker symbols.
   Focus on small/mid cap with 5x+ potential. One sentence per pick explaining why.
3. FITS MY PORTFOLIO: Does this strengthen any of my existing positions? Which ones?
4. WHAT TO RESEARCH: 2 most important things to check before investing.
5. RISK: Biggest reason these plays could go wrong.
6. WINDOW: How long does this opportunity last? (hours/days/weeks/months)

Be specific with tickers. Prioritise undiscovered gems over well-known stocks. No preamble.""")


def weekly_new_stock_suggestions():
    """Every week suggest 3 new stocks to consider adding to the portfolio."""
    return ask_claude(f"""My current investment portfolio:
{PORTFOLIO}

I am a Gen Z investor with a 5 year horizon, €500/month to invest.
I want stocks that could do what Nvidia did — early stage, undervalued, huge potential.

Suggest 3 NEW stocks I don't already own that I should research this week.
For each stock:
1. Name and ticker
2. What they do in 2 sentences
3. Why they could 5-10x in 5 years
4. Current market cap (small/mid/large)
5. Biggest risk
6. How it fits alongside my existing portfolio

Focus on: AI, space, defense tech, biotech, quantum, robotics, emerging markets.
Prioritise undiscovered gems. No preamble.""")


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

                if any(k.lower() in title.lower() or k.lower() in summary.lower()
                       for k in ALL_KEYWORDS):
                    print(f"Found: {title}")
                    found += 1

                    # Alert 1 — portfolio impact
                    portfolio_advice = analyse_portfolio_impact(title, summary)
                    send_telegram(
                        f"PORTFOLIO ALERT\n\n"
                        f"{title}\n\n"
                        f"{portfolio_advice}"
                    )
                    time.sleep(1)

                    # Alert 2 — new opportunity plays
                    opportunity = find_opportunity_plays(title, summary)
                    send_telegram(
                        f"OPPORTUNITY ALERT\n\n"
                        f"{title}\n\n"
                        f"{opportunity}"
                    )

                    seen.add(aid)
                    time.sleep(1)

        except Exception as e:
            print(f"Error with {feed_url}: {e}")

    save_seen(seen)
    print(f"Done. Found {found} relevant articles.")


def weekly_suggestions():
    """Send weekly new stock suggestions every Monday."""
    if datetime.now().weekday() == 0:  # Monday
        print("Sending weekly stock suggestions...")
        suggestions = weekly_new_stock_suggestions()
        send_telegram(
            f"WEEKLY STOCK PICKS\n"
            f"{datetime.now().strftime('%d %b %Y')}\n\n"
            f"3 new stocks to research this week:\n\n"
            f"{suggestions}"
        )


import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--once", action="store_true")
parser.add_argument("--weekly", action="store_true")
args = parser.parse_args()

if args.weekly:
    suggestions = weekly_new_stock_suggestions()
    send_telegram(
        f"WEEKLY STOCK PICKS\n"
        f"{datetime.now().strftime('%d %b %Y')}\n\n"
        f"3 new stocks to research this week:\n\n"
        f"{suggestions}"
    )
elif args.once:
    check_news()
else:
    schedule.every(30).minutes.do(check_news)
    schedule.every().monday.at("08:00").do(weekly_suggestions)
    check_news()
    while True:
        schedule.run_pending()
        time.sleep(30)
