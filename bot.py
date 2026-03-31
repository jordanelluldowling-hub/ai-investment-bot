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
- Nvidia (NVDA) $50 - AI infrastructure
- Bitcoin (BTC) $50 - Crypto
- Rheinmetall (RHM) $50 - Defense

TIER 2 - HIGH CONVICTION:
- Palantir (PLTR) $40 - AI + government
- IonQ (IONQ) $35 - Quantum computing
- Rocket Lab (RKLB) $35 - Space
- Axon Enterprise (AXON) $35 - AI law enforcement
- BigBear.ai (BBAI) $30 - Defense AI analytics

TIER 3 - MOONSHOTS:
- BTQ Technologies (BTQ) $25 - Quantum cybersecurity
- Richtech Robotics (RR) $25 - Restaurant/hotel AI robots
- Ondas Holdings (ONDS) $20 - AI drones for railways and defense
- Cellebrite (CLBT) $20 - Intelligence agency phone extraction
- IREN (IREN) $20 - AI data centres + Bitcoin mining
- Solana (SOL) $10 - Crypto
- Injective (INJ) $5 - Decentralised exchange crypto

WILDCARD:
- CoreWeave (CRWV) $50 - Nvidia backed AI cloud

Monthly budget: 500 euros
Strategy: Buy dips, hold 5 years, never sell Tier 1
"""

PORTFOLIO_TICKERS = [
    "Nvidia", "NVDA", "Bitcoin", "BTC",
    "Rheinmetall", "RHM", "Palantir", "PLTR",
    "IonQ", "IONQ", "Rocket Lab", "RKLB",
    "Axon", "AXON", "BigBear", "BBAI",
    "BTQ Technologies", "BTQ",
    "Richtech Robotics", "RR",
    "Ondas", "ONDS", "Cellebrite", "CLBT",
    "IREN", "Solana", "SOL",
    "Injective", "INJ", "CoreWeave", "CRWV",
]

OPPORTUNITY_KEYWORDS = [
    "artificial intelligence", "AI boom", "AI chip", "machine learning",
    "semiconductor", "quantum computing", "robotics", "automation",
    "data centre", "OpenAI", "Microsoft", "Google", "Meta", "Apple",
    "SpaceX", "space race", "NASA", "satellite", "defense spending",
    "NATO", "military contract", "drone", "Lockheed", "arms",
    "oil", "gas", "gold", "silver", "lithium", "uranium", "nuclear",
    "OPEC", "energy crisis", "hydrogen", "solar", "Strait of Hormuz",
    "interest rate", "Federal Reserve", "Fed", "rate cut", "rate hike",
    "inflation", "recession", "bank collapse", "IMF", "central bank",
    "Middle East", "Israel", "Iran", "Ukraine", "Russia", "China",
    "Taiwan", "sanctions", "war", "conflict",
    "IPO", "goes public", "merger", "acquisition", "takeover",
    "bankruptcy", "short squeeze", "market crash", "stock surge",
    "drug approval", "FDA", "cancer", "vaccine", "biotech", "pandemic",
    "bitcoin", "crypto", "ethereum", "ETF approval", "crypto regulation",
    "flying taxi", "electric vehicle", "BYD", "Tesla",
    "supply chain", "port strike", "food crisis",
    "cloud computing", "AI cloud", "railway", "railroad",
    "police", "law enforcement", "body camera", "taser",
    "intelligence agency", "FBI", "CIA", "phone extraction",
    "restaurant robot", "hotel robot", "service robot",
    "quantum security", "quantum encryption", "post quantum",
    "bitcoin mining", "crypto mining", "AI data centre",
    "decentralised exchange", "DeFi",
]

ALL_KEYWORDS = list(set(PORTFOLIO_TICKERS + OPPORTUNITY_KEYWORDS))

RSS_FEEDS = [
    "https://feeds.reuters.com/reuters/businessNews",
    "https://feeds.bbci.co.uk/news/business/rss.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://oilprice.com/rss/main",
]

CONGRESS_FEEDS = [
    "https://housestockwatcher.com/rss",
    "https://senatestockwatcher.com/rss",
]

WATCH_POLITICIANS = [
    "pelosi", "paul pelosi",
    "tuberville", "crenshaw",
    "collins", "loeffler",
    "burr", "greene",
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


def analyse_portfolio_impact(title, summary):
    return ask_claude(f"""News: {title}
Summary: {summary}

My Portfolio:
{PORTFOLIO}

In exactly 3 bullet points:
1. IMPACT: Which of my specific holdings does this affect and how?
2. ACTION: Buy more / hold / trim - which holding and why?
3. URGENCY: HIGH / MEDIUM / LOW and one sentence why.

Be direct. No preamble.""")


def find_opportunity_plays(title, summary):
    return ask_claude(f"""News: {title}
Summary: {summary}

My existing portfolio:
{PORTFOLIO}

You are an elite small/mid cap stock analyst hunting for the next Nvidia-style opportunity.
The investor has a 5 year horizon, buys dips aggressively, wants 10x+ returns.
They love under the radar companies that dominate a niche like DJI dominates drones.

1. EVENT TYPE: What kind of catalyst is this?
2. TOP 3 PLAYS: Specific stocks NOT already in my portfolio with ticker symbols.
   Focus on small/mid cap niche dominators with 10x potential. One sentence per pick.
3. FITS MY PORTFOLIO: Does this strengthen any existing positions?
4. WHAT TO RESEARCH: 2 most important things to check first.
5. RISK: Biggest reason these plays could go wrong.
6. WINDOW: How long does this opportunity last? (hours/days/weeks/months)

Be specific with tickers. Prioritise undiscovered niche dominators. No preamble.""")


def analyse_congress_trade(politician, ticker, trade_type, amount, summary):
    return ask_claude(f"""A US politician just filed a stock trade:

Politician: {politician}
Stock: {ticker}
Trade type: {trade_type}
Amount: {amount}
Details: {summary}

My Portfolio:
{PORTFOLIO}

1. WHY SIGNIFICANT: Why would this politician buy/sell this now? What do they likely know?
2. SHOULD I FOLLOW: Should I copy this trade? Yes/No and why.
3. CONNECTION: Does this relate to any of my existing holdings?
4. NEW OPPORTUNITY: If I don't own this stock, is it worth buying? Give ticker and reason.
5. URGENCY: HIGH / MEDIUM / LOW - how fast should I act?

Remember: Politicians file trades up to 45 days late - factor in the delay.
Be direct. No preamble.""")


def weekly_new_stock_suggestions():
    return ask_claude(f"""My current investment portfolio:
{PORTFOLIO}

I am a Gen Z investor, 5 year horizon, 500 euros/month.
I want stocks like the next Nvidia or BYD - companies that dominate a niche completely
then expand globally. Early stage, undervalued, 10x+ potential.

Suggest 3 NEW stocks I don't already own to research this week.
For each:
1. Name and ticker
2. What they do in 2 sentences
3. Why they could 10x in 5 years
4. Current size (small/mid/large cap)
5. Biggest risk
6. How it fits my existing portfolio

Focus on: niche dominators, AI, space, defense tech, biotech, quantum, robotics,
emerging market disruptors, companies big at home about to go global.
Prioritise undiscovered gems nobody is talking about. No preamble.""")


def check_congress_trades():
    print(f"Checking congressional trades... {datetime.now().strftime('%H:%M')}")
    seen = load_seen()
    found = 0

    for feed_url in CONGRESS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:20]:
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                aid = "congress_" + hashlib.md5(title.encode()).hexdigest()

                if aid in seen:
                    continue

                text = (title + " " + summary).lower()
                is_watched_politician = any(p in text for p in WATCH_POLITICIANS)
                is_our_stock = any(t.lower() in text for t in PORTFOLIO_TICKERS)

                if is_watched_politician or is_our_stock:
                    print(f"Congress trade found: {title}")
                    found += 1

                    analysis = analyse_congress_trade(
                        politician=title,
                        ticker=title,
                        trade_type="Purchase" if "purchase" in text or "bought" in text else "Sale",
                        amount=summary[:100],
                        summary=summary
                    )

                    send_telegram(
                        f"CONGRESSIONAL TRADE ALERT\n\n"
                        f"{title}\n\n"
                        f"{analysis}"
                    )

                    seen.add(aid)
                    time.sleep(1)

        except Exception as e:
            print(f"Congress feed error {feed_url}: {e}")

    save_seen(seen)
    print(f"Congress check done. Found {found} relevant trades.")


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

                    portfolio_advice = analyse_portfolio_impact(title, summary)
                    send_telegram(
                        f"PORTFOLIO ALERT\n\n"
                        f"{title}\n\n"
                        f"{portfolio_advice}"
                    )
                    time.sleep(1)

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
    if datetime.now().weekday() == 0:
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
parser.add_argument("--congress", action="store_true")
args = parser.parse_args()

if args.weekly:
    suggestions = weekly_new_stock_suggestions()
    send_telegram(
        f"WEEKLY STOCK PICKS\n"
        f"{datetime.now().strftime('%d %b %Y')}\n\n"
        f"3 new stocks to research this week:\n\n"
        f"{suggestions}"
    )
elif args.congress:
    check_congress_trades()
elif args.once:
    check_news()
    check_congress_trades()
else:
    schedule.every(30).minutes.do(check_news)
    schedule.every(1).hours.do(check_congress_trades)
    schedule.every().monday.at("08:00").do(weekly_suggestions)
    check_news()
    check_congress_trades()
    while True:
        schedule.run_pending()
        time.sleep(30)
