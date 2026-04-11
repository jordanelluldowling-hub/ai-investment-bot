"""
AI Investment News Alert Bot — v2

Monitors 15+ RSS feeds, congressional trades, and IPO filings.
Sends high-signal alerts to Telegram via Claude AI analysis.

Alert types:
  PORTFOLIO ALERT    — how news impacts your 16 holdings
  OPPORTUNITY ALERT  — small/mid cap stocks that could benefit
  CONGRESS SIGNAL    — politician stock trades (scored 1-10)
  IPO ALERT          — upcoming IPOs with pop potential score

Usage (GitHub Actions modes):
    python bot.py --mode news           # Check RSS feeds (hourly)
    python bot.py --mode congress       # Check congressional trades (hourly)
    python bot.py --mode daily-summary  # Daily 6pm congress summary
    python bot.py --mode weekly         # Monday 8am weekly stock picks
    python bot.py --mode ipo            # Check IPO calendar (daily)
    python bot.py --mode test           # Send test Telegram message
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

import config
from congress_tracker import (
    get_all_recent_trades,
    format_trade_alert,
    format_daily_summary,
    analyse_trade_with_claude,
    analyse_daily_trades_with_claude,
)
from ipo_tracker import check_ipos
from tracker import record_alert

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

# --- Seen articles cache ---
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


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message: str) -> bool:
    """Send message to Telegram. Falls back to console if not configured."""
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        log.warning("Telegram not configured — printing to console.")
        print("\n" + "=" * 60)
        print(message)
        print("=" * 60 + "\n")
        return True

    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    # Telegram has a 4096 char limit per message
    chunks = [message[i : i + 4000] for i in range(0, len(message), 4000)]

    for chunk in chunks:
        try:
            resp = requests.post(
                url,
                json={"chat_id": config.TELEGRAM_CHAT_ID, "text": chunk},
                timeout=10,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            log.error(f"Telegram send failed: {e}")
            return False

    return True


# ============================================================
# NEWS MONITORING
# ============================================================

def fetch_relevant_articles() -> list[dict]:
    """Fetch articles from all RSS feeds and filter by keywords."""
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

            if any(
                kw.lower() in title.lower() or kw.lower() in summary.lower()
                for kw in config.TRIGGER_KEYWORDS
            ):
                relevant.append(
                    {"title": title, "summary": summary, "link": link, "id": aid}
                )

    return relevant


def analyse_portfolio_impact(title: str, summary: str) -> str:
    """How does this news affect existing holdings?"""
    client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)
    msg = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=config.MAX_RESPONSE_TOKENS,
        messages=[
            {
                "role": "user",
                "content": f"""
News: {title}
Summary: {summary}

My Portfolio:
{config.PORTFOLIO}

Answer in exactly 3 bullet points:
1. IMPACT: Which of my specific holdings does this affect and how?
2. ACTION: Buy more / sell / hold — specify which ticker and why now.
3. URGENCY: HIGH / MEDIUM / LOW — one sentence explaining the time sensitivity.

Be direct. Name specific tickers. No preamble.
""",
            }
        ],
    )
    return msg.content[0].text


def find_opportunity_plays(title: str, summary: str) -> str:
    """What small/mid cap stocks could benefit most from this event?"""
    client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)
    msg = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=config.MAX_RESPONSE_TOKENS,
        messages=[
            {
                "role": "user",
                "content": f"""
This major news just broke:
{title}

Summary: {summary}

You are a small cap stock analyst. The investor has 20 minutes to research before deciding.

Answer in exactly this format:
1. EVENT TYPE: What kind of catalyst is this? (geopolitical / IPO / sector boom / macro / FDA / contract / other)
2. TOP 3 PLAYS: Specific stocks or ETFs with ticker symbols that could benefit most.
   Prioritise small/mid cap with high upside. One sentence per pick explaining why.
3. WHAT TO RESEARCH: The 2 most important things to check before investing.
4. RISK: Biggest reason this play could go wrong. One sentence.
5. WINDOW: How long does this opportunity likely last? (hours / days / weeks)
6. CONFIDENCE: HIGH / MEDIUM / LOW — how sure are you about these plays?

Be specific with tickers. No preamble.
""",
            }
        ],
    )
    return msg.content[0].text


def urgency_from_analysis(analysis: str) -> str:
    """Extract urgency/confidence level from Claude's response."""
    lower = analysis.lower()
    # Check for explicit urgency/confidence markers
    for high_marker in ["urgency: high", "confidence: high", "high urgency", "high confidence"]:
        if high_marker in lower:
            return "high"
    for med_marker in ["urgency: medium", "confidence: medium", "medium urgency"]:
        if med_marker in lower:
            return "medium"
    # Fallback: check first 300 chars for the word "high"
    if "high" in lower[:300]:
        return "high"
    if "medium" in lower[:300]:
        return "medium"
    return "low"


URGENCY_RANK = {"low": 0, "medium": 1, "high": 2}


def urgency_emoji(level: str) -> str:
    return {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(level, "⚪")


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


# ============================================================
# BUY SIGNAL DETECTOR
# ============================================================

def is_buy_catalyst(title: str, summary: str) -> bool:
    """Check if an article describes a positive company event (buy signal candidate)."""
    text = (title + " " + summary).lower()
    return any(kw.lower() in text for kw in config.BUY_CATALYST_KEYWORDS)


def analyse_buy_catalyst(title: str, summary: str) -> str:
    """
    Use Claude to analyse a positive company event and rate it as a buy signal.
    Returns structured analysis with catalyst strength score 1-10.
    """
    client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)
    msg = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=config.MAX_RESPONSE_TOKENS,
        messages=[
            {
                "role": "user",
                "content": f"""
A company just announced something significant:

HEADLINE: {title}
DETAILS: {summary}

Analyse this as a potential BUY SIGNAL for an investor.

Answer in exactly this format:
CATALYST TYPE: [Patent / FDA Approval / Government Contract / Partnership / Earnings Beat / Product Launch / Funding Round / Expansion / Acquisition / Other]
COMPANY: [Company name and ticker symbol if identifiable]
STRENGTH: [Score 1-10 — how significant is this event? 10 = rare, company-changing. 7+ = strong buy signal]
WHY BUY: [One sentence — why does this make the stock worth buying now?]
UPSIDE: [Realistic gain range, e.g. +20% to +60% over 3-6 months]
TIME TO ACT: [hours / days / weeks — how quickly should an investor research this?]
RISK: [One sentence — biggest reason this might not play out]
ACTION: [BUY NOW / BUY ON DIP / ADD TO WATCHLIST / SKIP]

Only score 7-10 if this is a genuine major event. Be direct. No preamble.
""",
            }
        ],
    )
    return msg.content[0].text


def extract_catalyst_score(analysis: str) -> int:
    """Parse the STRENGTH score from Claude's buy catalyst analysis."""
    for line in analysis.splitlines():
        if line.upper().startswith("STRENGTH:"):
            try:
                value = line.split(":", 1)[1].strip().split()[0]
                return int(value.split("/")[0])
            except (ValueError, IndexError):
                pass
    return 5  # Default mid-score if parsing fails


def format_buy_signal_alert(title: str, analysis: str, link: str, score: int) -> str:
    timestamp = datetime.now().strftime("%d %b %Y %H:%M")
    stars = "⭐" * min(score // 2, 5)
    return (
        f"🚀 BUY SIGNAL {stars}\n"
        f"Catalyst strength: {score}/10\n"
        f"{timestamp}\n\n"
        f"EVENT: {title}\n\n"
        f"{analysis}\n\n"
        f"{link}"
    )


def check_news() -> None:
    """Main news monitoring loop — runs every hour via GitHub Actions."""
    log.info("Starting news check...")
    articles = fetch_relevant_articles()

    if not articles:
        log.info("No new relevant articles found.")
        return

    log.info(f"Found {len(articles)} new article(s). Analysing...")
    seen = load_seen_cache()
    alerts_sent = 0

    for article in articles:
        title = article["title"]
        log.info(f"Analysing: {title}")

        try:
            # --- Portfolio Alert ---
            portfolio_analysis = analyse_portfolio_impact(title, article["summary"])
            urgency = urgency_from_analysis(portfolio_analysis)

            if URGENCY_RANK[urgency] >= URGENCY_RANK[config.MIN_URGENCY]:
                alert = format_portfolio_alert(
                    title, portfolio_analysis, article["link"], urgency
                )
                send_telegram(alert)
                alerts_sent += 1
                record_alert(
                    alert_type="portfolio",
                    headline=title,
                    analysis=portfolio_analysis,
                    tickers=config.YOUR_TICKERS,
                    confidence=urgency,
                )
                log.info(f"Portfolio alert sent [{urgency.upper()}]: {title}")
            else:
                log.info(f"Skipped (urgency={urgency}, min={config.MIN_URGENCY}): {title}")

            time.sleep(1)

            # --- Opportunity Alert (only if confidence is HIGH or MEDIUM) ---
            opportunity_analysis = find_opportunity_plays(title, article["summary"])
            opp_confidence = urgency_from_analysis(opportunity_analysis)

            if opp_confidence in ["high", "medium"]:
                opp_alert = format_opportunity_alert(
                    title, opportunity_analysis, article["link"]
                )
                send_telegram(opp_alert)
                alerts_sent += 1
                record_alert(
                    alert_type="opportunity",
                    headline=title,
                    analysis=opportunity_analysis,
                    confidence=opp_confidence,
                )
                log.info(f"Opportunity alert sent [{opp_confidence.upper()}]: {title}")
            else:
                log.info(f"Opportunity skipped (confidence={opp_confidence}): {title}")

            time.sleep(1)

            # --- Buy Signal Alert (positive company catalyst detected) ---
            if is_buy_catalyst(title, article["summary"]):
                log.info(f"Buy catalyst detected — analysing: {title}")
                catalyst_analysis = analyse_buy_catalyst(title, article["summary"])
                catalyst_score = extract_catalyst_score(catalyst_analysis)

                if catalyst_score >= config.BUY_SIGNAL_THRESHOLD:
                    buy_alert = format_buy_signal_alert(
                        title, catalyst_analysis, article["link"], catalyst_score
                    )
                    send_telegram(buy_alert)
                    alerts_sent += 1
                    record_alert(
                        alert_type="buy_signal",
                        headline=title,
                        analysis=catalyst_analysis,
                        score=catalyst_score,
                        confidence="high" if catalyst_score >= 9 else "medium",
                    )
                    log.info(f"Buy signal sent (score {catalyst_score}/10): {title}")
                else:
                    log.info(f"Buy catalyst scored {catalyst_score}/10 — below threshold, skipped")

        except Exception as e:
            log.error(f"Analysis failed for '{title}': {e}")

        seen.add(article["id"])
        time.sleep(2)  # Rate limit

    save_seen_cache(seen)
    log.info(f"News check complete. {alerts_sent} alert(s) sent.")


# ============================================================
# CONGRESSIONAL TRADING
# ============================================================

def check_congress_trades() -> None:
    """
    Fetch, score, and alert on high-signal congressional stock trades.
    Runs hourly. Only sends alerts for trades scoring >= CONGRESS_SCORE_THRESHOLD.
    """
    log.info("Checking congressional trades...")

    trades = get_all_recent_trades(lookback_days=2)  # Last 48h for hourly runs

    if not trades:
        log.info("No high-signal congressional trades found.")
        return

    for trade in trades:
        # Ask Claude to interpret the trade before sending
        log.info(f"Analysing trade with Claude: {trade['politician']} {trade['ticker']}")
        claude_analysis = analyse_trade_with_claude(trade)
        alert = format_trade_alert(trade, claude_analysis)
        send_telegram(alert)
        record_alert(
            alert_type="congress",
            headline=f"{trade['politician']} — {trade.get('trade_type','').upper()} {trade['ticker']}",
            analysis=claude_analysis,
            tickers=[trade["ticker"]] if trade.get("ticker") else [],
            score=trade.get("score"),
            politician=trade.get("politician"),
        )
        log.info(f"Congress alert sent: {trade['politician']} {trade['ticker']} (score: {trade['score']})")
        time.sleep(2)


def send_daily_congress_summary() -> None:
    """
    Daily 6pm summary of the strongest congressional trade signals.
    Looks back 24 hours and summarises the top 5.
    """
    log.info("Sending daily congress summary...")

    # Use threshold=5 to get meaningful trades for the summary
    trades = get_all_recent_trades(lookback_days=1, score_threshold=5)

    # Ask Claude to identify patterns across all today's trades
    claude_pattern = analyse_daily_trades_with_claude(trades) if trades else ""

    summary = format_daily_summary(trades, claude_pattern)
    send_telegram(summary)
    log.info(f"Daily congress summary sent ({len(trades)} trades).")


# ============================================================
# WEEKLY STOCK PICKS
# ============================================================

def weekly_suggestions() -> None:
    """
    Monday 8am: Claude suggests 3 new stocks to research this week.
    Based on macro conditions, sector trends, and your existing portfolio.
    """
    log.info("Generating weekly stock picks...")

    if not config.CLAUDE_API_KEY:
        log.warning("CLAUDE_API_KEY not set — skipping weekly picks")
        return

    client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)

    try:
        msg = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=config.MAX_WEEKLY_TOKENS,
            messages=[
                {
                    "role": "user",
                    "content": f"""
Today is {datetime.now().strftime('%A %d %B %Y')}.

My current portfolio:
{config.PORTFOLIO}

You are my personal AI stock analyst. Based on current macro conditions (April 2026),
emerging tech trends, and gaps in my existing portfolio:

Suggest 3 NEW stocks I don't already own that I should research this week.
Focus on: small/mid cap with 3-10x potential over 1-3 years.

For each pick, answer:
TICKER: [symbol]
COMPANY: [full name + one sentence what they do]
WHY NOW: [specific catalyst happening in the next 30-90 days]
UPSIDE: [realistic return range, e.g. 3-8x over 2 years]
RISK: [biggest risk in one sentence]
RESEARCH FIRST: [one specific thing to check before buying]

Separate each pick with ---
No preamble. Be direct and specific.
""",
                }
            ],
        )

        picks = msg.content[0].text
        timestamp = datetime.now().strftime("%d %b %Y")
        message = (
            f"📊 WEEKLY STOCK PICKS — {timestamp}\n\n"
            f"3 new stocks to research this week:\n\n"
            f"{picks}\n\n"
            f"Remember: research before you invest. These are starting points."
        )
        send_telegram(message)
        log.info("Weekly picks sent.")

    except Exception as e:
        log.error(f"Weekly picks failed: {e}")


# ============================================================
# TEST
# ============================================================

def run_test() -> None:
    """Send a test message to confirm Telegram is working."""
    timestamp = datetime.now().strftime("%d %b %Y %H:%M")
    message = (
        f"Investment Bot v2 — Online\n"
        f"{timestamp}\n\n"
        f"Systems check:\n"
        f"• RSS feeds: {len(config.RSS_FEEDS)} sources\n"
        f"• Portfolio: {len(config.YOUR_TICKERS)} holdings\n"
        f"• Politicians watched: {len(config.WATCH_POLITICIANS)} names\n"
        f"• Min urgency: {config.MIN_URGENCY.upper()}\n"
        f"• Congress score threshold: {config.CONGRESS_SCORE_THRESHOLD}/10\n\n"
        f"Alert types active:\n"
        f"  PORTFOLIO — impact on your holdings\n"
        f"  OPPORTUNITY — small cap plays\n"
        f"  BUY SIGNAL — company positive catalysts\n"
        f"  CONGRESS — politician stock trades\n"
        f"  IPO — upcoming IPO alerts\n\n"
        f"All systems operational."
    )
    ok = send_telegram(message)
    if ok:
        log.info("Test message sent successfully.")
    else:
        log.error("Test message failed — check TELEGRAM_TOKEN and TELEGRAM_CHAT_ID.")


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="AI Investment Bot v2")
    parser.add_argument(
        "--mode",
        choices=["news", "congress", "daily-summary", "weekly", "ipo", "test"],
        default="news",
        help="Which function to run",
    )
    args = parser.parse_args()

    # Validate API key for modes that need Claude
    needs_claude = args.mode in ["news", "weekly", "ipo"]
    if needs_claude and not config.CLAUDE_API_KEY:
        log.error("CLAUDE_API_KEY is not set. Set it as a GitHub Secret.")
        return

    mode_map = {
        "news": check_news,
        "congress": check_congress_trades,
        "daily-summary": send_daily_congress_summary,
        "weekly": weekly_suggestions,
        "ipo": lambda: check_ipos(send_fn=send_telegram),
        "test": run_test,
    }

    log.info(f"Running mode: {args.mode}")
    mode_map[args.mode]()


if __name__ == "__main__":
    main()
