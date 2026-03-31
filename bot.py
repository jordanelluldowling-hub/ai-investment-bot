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
    "police", "law enforcement", "body camera",
    "intelligence agency", "FBI", "CIA",
    "restaurant robot", "hotel robot", "service robot",
    "quantum security", "quantum encryption",
    "bitcoin mining", "crypto mining",
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


def is_high_urgency(text):
    """Only return True if Claude rated this as HIGH urgency."""
    return "urgency: high" in text.lower() or "high" in text.lower()[:300]


def analyse_portfolio_impact(title, summary):
    return ask_claude(f"""News: {title}
Summary: {summary}

My Portfolio:
{PORTFOLIO}

In exactly 3 bullet points:
1. IMPACT: Which of my specific holdings does this affect and how?
2. ACTION: Buy more / hold / trim - which holding and why?
3. URGENCY: HIGH / MEDIUM / LOW and one sentence why.

Only rate as HIGH if this could move my portfolio by 5%+ within 48 hours.
Be direct. No preamble.""")


def find_opportunity_plays(title, summary):
    return ask_claude(f"""News: {title}
Summary: {summary}

My existing portfolio:
{PORTFOLIO}

You are an elite small/mid cap stock analyst hunting for the next Nvidia-style opportunity.
The investor has a 5 year horizon, buys dips aggressively, wants 10x+ returns.
They love under the radar companies that dominate a niche like DJI dominates drones.
Only suggest plays you are genuinely excited about - no filler picks.

1. EVENT TYPE: What kind of catalyst is this?
2. TOP 3 PLAYS: Specific stocks NOT already in my portfolio with ticker symbols.
   Focus on small/mid cap niche dominators with 10x potential. One sentence per pick.
3. FITS MY PORTFOLIO: Does this strengthen any existing positions?
4. WHAT TO RESEARCH: 2 most important things to check first.
5. RISK: Biggest reason these plays could go wrong.
6. WINDOW: How long does this opportunity last? (hours/days/weeks/months)
7. CONFIDENCE: HIGH / MEDIUM / LOW - how confident are you in these plays?

Be specific with tickers. Only send if CONFIDENCE is HIGH or MEDIUM. No preamble.""")


def score_congress_trade(title, summary):
    """Ask Claude to score a trade 1-10. Only alert if score >= 7."""
    return ask_claude(f"""A US politician filed this stock trade:
{title}
{summary}

Score this trade from 1-10 for how significant it is as an investment signal.
10 = Pelosi buying a massive position in a sector days before a government contract
1 = A senator selling $1000 of a random stock

Respond with ONLY a number from 1-10. Nothing else.""")


def analyse_congress_trade(title, summary):
    return ask_claude(f"""A US politician just filed a significant stock trade:

{title}
{summary}

My Portfolio:
{PORTFOLIO}

1. WHY SIGNIFICANT: Why would this politician buy/sell this now? What do they likely know?
2. SHOULD I FOLLOW: Should I copy this trade? Yes/No and why.
3. CONNECTION: Does this relate to any of my existing holdings?
4. NEW OPPORTUNITY: If I don't own this stock, is it worth buying? Ticker and reason.
5. URGENCY: HIGH / MEDIUM / LOW - how fast should I act?

Note: Politicians file trades up to 45 days late - factor in the delay.
Be direct. No preamble.""")


def daily_congress_summary(trades):
    """Summarise only the strongest congressional trades of the day."""
    if not trades:
        return None
    trades_text = "\n".join([f"- {t}" for t in trades[:20]])
    return ask_claude(f"""Here are today's congressional stock trade filings:

{trades_text}

My Portfolio:
{PORTFOLIO}

Give me today's strongest congressional trading signals only.
Ignore small, routine or irrelevant trades.

1. TOP 3 STRONGEST SIGNALS TODAY: Only the most significant trades worth acting on.
   For each: Politician, ticker, buy/sell, amount, why it matters.
2. FOLLOW ANY: Which specifically should I copy and how much to invest?
3. PATTERN: Any clear theme across today's trades?
4. VERDICT: Is today's congressional activity bullish or bearish overall?

If there are no strong signals today just say: NO STRONG SIGNALS TODAY.
Be direct. No filler. No preamble.""")


def weekly_new_stock_suggestions():
    return ask_claude(f"""My current investment portfolio:
{PORTFOLIO}

I am a Gen Z investor, 5 year horizon, 500 euros/month.
I want stocks like the next Nvidia or BYD - companies that dominate a niche completely
then expand globally. Early stage, undervalued, 10x+ potential.

Suggest 3 NEW stocks I don't already own to research this week.
Only suggest ones you are genuinely excited about.
For each:
1. Name and ticker
2. What they do in 2 sentences
3. Why they could 10x in 5 years
4. Current size (small/mid/large cap)
5. Biggest risk
6. How it fits my existing portfolio
7. Conviction level: HIGH / MEDIUM

Only include HIGH or MEDIUM conviction picks.
Focus on: niche dominators, AI, space, defense tech, biotech, quantum, robotics,
emerging market disruptors, companies big at home about to go global.
No preamble.""")


def check_congress_trades():
    """Check for new congressional trades. Only alert on high scoring ones."""
    print(f"Checking congressional trades... {datetime.now().strftime('%H:%M')}")
    seen = load_seen()
    found = 0
    all_trades_today = []

    for feed_url in CONGRESS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:20]:
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                all_trades_today.append(f"{title} — {summary[:100]}")

                aid = "congress_" + hashlib.md5(title.encode()).hexdigest()
                if aid in seen:
                    continue

                text = (title + " " + summary).lower()
                is_watched_politician = any(p in text for p in WATCH_POLITICIANS)
                is_our_stock = any(t.lower() in text for t in PORTFOLIO_TICKERS)

                if is_watched_politician or is_our_stock:
                    # Score the trade — only alert if 7 or above
                    try:
                        score_text = score_congress_trade(title, summary)
                        score = int(''.join(filter(str.isdigit, score_text[:5])))
                    except:
                        score = 5

                    print(f"Congress trade score {score}/10: {title}")

                    if score >= 7:
                        found += 1
                        analysis = analyse_congress_trade(title, summary)
                        send_telegram(
                            f"CONGRESSIONAL TRADE ALERT (Score: {score}/10)\n\n"
                            f"{title}\n\n"
                            f"{analysis}"
                        )

                    seen.add(aid)
                    time.sleep(1)

        except Exception as e:
            print(f"Congress feed error {feed_url}: {e}")

    save_seen(seen)
    print(f"Congress check done. Sent {found} high score alerts.")
    return all_trades_today


def send_daily_congress_summary():
    """Send daily summary of strongest congressional trades at 6pm."""
    print("Sending daily congressional trading summary...")
    all_trades = []

    for feed_url in CONGRESS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:30]:
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                all_trades.append(f"{title} — {summary[:100]}")
        except Exception as e:
            print(f"Feed error: {e}")

    if not all_trades:
        send_telegram(
            f"DAILY CONGRESS SUMMARY\n"
            f"{datetime.now().strftime('%d %b %Y')}\n\n"
            f"No congressional trades filed today."
        )
        return

    summary = daily_congress_summary(all_trades)
    if summary:
        send_telegram(
            f"DAILY CONGRESS SUMMARY\n"
            f"{datetime.now().strftime('%d %b %Y')}\n\n"
            f"{summary}"
        )


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

                    # Get portfolio impact and only send if HIGH urgency
                    portfolio_advice = analyse_portfolio_impact(title, summary)

                    if is_high_urgency(portfolio_advice):
                        print(f"HIGH urgency: {title}")
                        found += 1
                        send_telegram(
                            f"PORTFOLIO ALERT\n\n"
                            f"{title}\n\n"
                            f"{portfolio_advice}"
                        )
                        time.sleep(1)

                        opportunity = find_opportunity_plays(title, summary)
                        # Only send opportunity if confidence is high/medium
                        if "confidence: high" in opportunity.lower() or "confidence: medium" in opportunity.lower():
                            send_telegram(
                                f"OPPORTUNITY ALERT\n\n"
                                f"{title}\n\n"
                                f"{opportunity}"
                            )
                    else:
                        print(f"Skipped (not HIGH urgency): {title}")

                    seen.add(aid)
                    time.sleep(1)

        except Exception as e:
            print(f"Error with {feed_url}: {e}")

    save_seen(seen)
    print(f"Done. Sent {found} high urgency alerts.")


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
parser.add_argument("--daily-summary", action="store_true")
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
elif getattr(args, 'daily_summary', False):
    send_daily_congress_summary()
elif args.once:
    check_news()
    check_congress_trades()
else:
    schedule.every(30).minutes.do(check_news)
    schedule.every(1).hours.do(check_congress_trades)
    schedule.every().monday.at("08:00").do(weekly_suggestions)
    schedule.every().day.at("18:00").do(send_daily_congress_summary)
    check_news()
    check_congress_trades()
    while True:
        schedule.run_pending()
        time.sleep(30)
