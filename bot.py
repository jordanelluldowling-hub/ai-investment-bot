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
import re
import time
from datetime import datetime, timedelta
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
from sentiment_tracker import check_sentiment
from batch_processor import add_to_batch_queue, submit_batch, retrieve_batch_results
from moonshot_detector import run_moonshot_scan

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
                relevant.append({
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "id": aid,
                    "source_tier": config.get_source_tier(feed_url),
                })

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


# ============================================================
# TICKER EXTRACTION
# ============================================================

# Words that look like tickers but aren't
_NON_TICKERS = {
    "AT", "BE", "BY", "DO", "GO", "IF", "IN", "IS", "IT", "ME",
    "MY", "NO", "OF", "ON", "OR", "SO", "TO", "UP", "US", "WE",
    "AND", "BUT", "FOR", "NOT", "THE", "WHO", "WHY", "CEO", "CFO",
    "IPO", "ETF", "USA", "GDP", "CPI", "FDA", "SEC", "OTC",
    "GAS", "EPS", "RSI", "ATH", "DCA", "BUY", "SELL", "HIGH",
    "LOW", "HOLD", "NEWS", "RATE", "TOP", "KEY", "NEW", "NOW",
    "GET", "SET", "YES", "NAV", "TAX", "ESG", "OIL", "LNG",
}


def extract_tickers(text: str) -> list[str]:
    """Extract likely stock ticker symbols from Claude's analysis text."""
    candidates = re.findall(r'\b([A-Z]{2,5})\b', text)
    seen = set()
    result = []
    for t in candidates:
        if t not in _NON_TICKERS and t not in seen:
            seen.add(t)
            result.append(t)
    return result[:6]  # Cap at 6 tickers per alert


# ============================================================
# SECOND-OPINION QUALITY GATE
# ============================================================

def review_opportunity(title: str, analysis: str) -> tuple[bool, int]:
    """
    Second Claude call that acts as a strict quality controller.
    Reviews the opportunity analysis and scores it 0-100.
    Only returns True (send) if score >= 70.

    This prevents Claude from marking its own homework.
    """
    if not config.CLAUDE_API_KEY:
        return True, 75  # If no key, allow through

    client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)
    try:
        msg = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=150,
            messages=[{
                "role": "user",
                "content": f"""You are a strict investment alert quality controller.

NEWS: {title}

OPPORTUNITY ANALYSIS TO REVIEW:
{analysis}

Score this analysis 0-100 based on:
+ Specific named tickers with clear reasoning (+30)
+ Genuine, significant catalyst with real edge (+25)
+ Clear opportunity window that isn't already priced in (+25)
+ Realistic risk/reward (+20)

Deduct heavily for: vague tickers, obvious/already-known plays,
generic analysis, poor risk/reward, no clear edge.

Answer in exactly 2 lines:
SCORE: [0-100]
DECISION: [SEND / SKIP]""",
            }],
        )
        raw = msg.content[0].text
        score = 50
        decision = "SKIP"
        for line in raw.splitlines():
            if line.startswith("SCORE:"):
                try:
                    score = int(line.split(":", 1)[1].strip().split()[0])
                except (ValueError, IndexError):
                    pass
            if line.startswith("DECISION:"):
                decision = line.split(":", 1)[1].strip().upper()

        should_send = decision == "SEND" and score >= 70
        log.info(f"Opportunity review: score={score}, decision={decision}")
        return should_send, score

    except Exception as e:
        log.error(f"Opportunity review failed: {e}")
        return True, 75  # On error, allow through


# ============================================================
# TICKER DEDUPLICATION
# ============================================================

def was_recently_alerted(tickers: list[str], hours: int = 48) -> list[str]:
    """
    Returns list of tickers that were already alerted in the last N hours.
    Empty list means none were recently alerted (safe to send).
    """
    from tracker import load_alerts
    cutoff = datetime.now() - timedelta(hours=hours)
    recent_alerts = load_alerts()
    recent_tickers: set[str] = set()

    for alert in recent_alerts:
        try:
            sent_at = datetime.fromisoformat(alert.get("sent_at", ""))
            if sent_at >= cutoff:
                for t in alert.get("tickers", []):
                    recent_tickers.add(t.upper())
        except (ValueError, KeyError):
            continue

    return [t for t in tickers if t.upper() in recent_tickers]


# ============================================================
# CONVERGENCE DETECTOR — TRIPLE SIGNAL
# ============================================================

def get_recent_alert_types_for_tickers(tickers: list[str], days: int = 3) -> dict[str, set]:
    """
    For each ticker, return which alert types have fired in the last N days.
    e.g. {"NVDA": {"congress", "buy_signal"}}
    """
    from tracker import load_alerts
    cutoff = datetime.now() - timedelta(days=days)
    all_alerts = load_alerts()
    ticker_types: dict[str, set] = {}

    for alert in all_alerts:
        try:
            sent_at = datetime.fromisoformat(alert.get("sent_at", ""))
            if sent_at < cutoff:
                continue
            atype = alert.get("type", "")
            for t in alert.get("tickers", []):
                t = t.upper()
                if t not in ticker_types:
                    ticker_types[t] = set()
                ticker_types[t].add(atype)
        except (ValueError, KeyError):
            continue

    return ticker_types


def format_convergence_alert(ticker: str, alert_types: set, headlines: list[str]) -> str:
    """Format a convergence (triple signal) alert — the strongest possible signal."""
    timestamp = datetime.now().strftime("%d %b %Y %H:%M")
    types_str = " + ".join(t.replace("_", " ").upper() for t in sorted(alert_types))
    headlines_str = "\n".join(f"  • {h[:100]}" for h in headlines[:3])

    return (
        f"🔥 CONVERGENCE ALERT — TRIPLE SIGNAL 🔥\n"
        f"{timestamp}\n\n"
        f"TICKER: {ticker}\n"
        f"SIGNALS ALIGNED: {types_str}\n\n"
        f"WHAT THIS MEANS: Multiple independent sources are all\n"
        f"flagging {ticker} at the same time. This is the strongest\n"
        f"possible signal the bot can generate.\n\n"
        f"RECENT TRIGGERS:\n{headlines_str}\n\n"
        f"ACTION: Research {ticker} immediately — check price, news,\n"
        f"congressional activity, and fundamentals before acting."
    )


def check_and_send_convergence(tickers: list[str], alert_type: str, headline: str) -> None:
    """
    After any alert fires, check if this creates a convergence (3+ alert types
    on the same ticker). If so, send a special TRIPLE SIGNAL alert.
    """
    ticker_types = get_recent_alert_types_for_tickers(tickers, days=3)

    for ticker in tickers:
        types_seen = ticker_types.get(ticker.upper(), set())
        types_seen = types_seen | {alert_type}  # Include the current one

        if len(types_seen) >= 3:
            log.info(f"CONVERGENCE on {ticker}: {types_seen}")
            # Collect recent headlines for this ticker
            from tracker import load_alerts
            cutoff = datetime.now() - timedelta(days=3)
            headlines = [
                a.get("headline", "")
                for a in load_alerts()
                if ticker.upper() in [t.upper() for t in a.get("tickers", [])]
                and datetime.fromisoformat(a.get("sent_at", "2000-01-01")) >= cutoff
            ]
            headlines.append(headline)

            alert = format_convergence_alert(ticker, types_seen, headlines)
            send_telegram(alert)
            record_alert(
                alert_type="convergence",
                headline=f"TRIPLE SIGNAL on {ticker}",
                analysis=alert,
                tickers=[ticker],
                score=10,
                confidence="high",
            )
            break  # One convergence alert per check is enough


# ============================================================
# MORNING BRIEFING
# ============================================================

def morning_briefing() -> None:
    """
    Daily 8am (Mon-Sat): top 3 signals from the past 24 hours.
    Gives a quick 'what to watch today' summary.
    """
    from tracker import load_alerts
    log.info("Generating morning briefing...")

    cutoff = datetime.now() - timedelta(hours=24)
    recent = [
        a for a in load_alerts()
        if datetime.fromisoformat(a.get("sent_at", "2000-01-01")) >= cutoff
    ]

    if not recent:
        send_telegram(
            f"☀️ MORNING BRIEFING — {datetime.now().strftime('%d %b %Y')}\n\n"
            f"No high-signal alerts in the last 24 hours.\n"
            f"Markets are quiet — stay patient."
        )
        return

    # Sort by score descending, take top 5
    scored = sorted(
        recent,
        key=lambda a: (a.get("score") or 0),
        reverse=True,
    )[:5]

    lines = [f"☀️ MORNING BRIEFING — {datetime.now().strftime('%d %b %Y')}\n"]
    lines.append("Top signals from the last 24 hours:\n")

    for i, alert in enumerate(scored, 1):
        atype = alert.get("type", "?").replace("_", " ").upper()
        tickers = ", ".join(alert.get("tickers", [])[:3]) or "?"
        score = alert.get("score")
        score_str = f" | Score {score}/10" if score else ""
        headline = alert.get("headline", "")[:80]
        lines.append(f"{i}. {atype} | {tickers}{score_str}")
        lines.append(f"   {headline}")

    # Watchlist for today
    all_tickers = []
    for a in scored:
        all_tickers.extend(a.get("tickers", []))
    watchlist = list(dict.fromkeys(all_tickers))[:6]  # Unique, ordered, max 6
    if watchlist:
        lines.append(f"\nWATCH TODAY: {' | '.join(watchlist)}")

    send_telegram("\n".join(lines))
    log.info("Morning briefing sent.")


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
        source_tier = article.get("source_tier", 2)

        # Tier 3 sources (e.g. ZeroHedge) — queue for overnight batch processing
        if source_tier == 3:
            log.info(f"Tier 3 source — queuing for overnight batch: {title[:60]}")
            add_to_batch_queue(article)
            seen.add(article["id"])
            continue

        log.info(f"Analysing [Tier {source_tier}]: {title}")

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

            # --- Opportunity Alert ---
            # Step 1: Generate analysis
            opportunity_analysis = find_opportunity_plays(title, article["summary"])
            opp_confidence = urgency_from_analysis(opportunity_analysis)

            if opp_confidence in ["high", "medium"]:
                # Step 2: Extract tickers for deduplication + convergence check
                opp_tickers = extract_tickers(opportunity_analysis)

                # Step 3: Deduplication — skip if same tickers alerted in last 48h
                recent_dupes = was_recently_alerted(opp_tickers, hours=48)
                if recent_dupes:
                    log.info(f"Opportunity skipped — tickers {recent_dupes} already alerted in last 48h")
                else:
                    # Step 4: Second-opinion quality gate
                    should_send, review_score = review_opportunity(title, opportunity_analysis)

                    if should_send:
                        opp_alert = format_opportunity_alert(
                            title, opportunity_analysis, article["link"]
                        )
                        send_telegram(opp_alert)
                        alerts_sent += 1
                        record_alert(
                            alert_type="opportunity",
                            headline=title,
                            analysis=opportunity_analysis,
                            tickers=opp_tickers,
                            score=review_score // 10,  # Convert 0-100 to 0-10
                            confidence=opp_confidence,
                        )
                        log.info(f"Opportunity sent [score={review_score}]: {title}")
                        # Step 5: Check for convergence (triple signal)
                        check_and_send_convergence(opp_tickers, "opportunity", title)
                    else:
                        log.info(f"Opportunity blocked by quality gate (score={review_score}): {title}")
            else:
                log.info(f"Opportunity skipped (confidence={opp_confidence}): {title}")

            time.sleep(1)

            # --- Buy Signal Alert (positive company catalyst detected) ---
            if is_buy_catalyst(title, article["summary"]):
                log.info(f"Buy catalyst detected — analysing: {title}")
                catalyst_analysis = analyse_buy_catalyst(title, article["summary"])
                catalyst_score = extract_catalyst_score(catalyst_analysis)

                if catalyst_score >= config.BUY_SIGNAL_THRESHOLD:
                    buy_tickers = extract_tickers(catalyst_analysis)
                    buy_alert = format_buy_signal_alert(
                        title, catalyst_analysis, article["link"], catalyst_score
                    )
                    send_telegram(buy_alert)
                    alerts_sent += 1
                    record_alert(
                        alert_type="buy_signal",
                        headline=title,
                        analysis=catalyst_analysis,
                        tickers=buy_tickers,
                        score=catalyst_score,
                        confidence="high" if catalyst_score >= 9 else "medium",
                    )
                    log.info(f"Buy signal sent (score {catalyst_score}/10): {title}")
                    # Check for convergence
                    check_and_send_convergence(buy_tickers, "buy_signal", title)
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
        congress_tickers = [trade["ticker"]] if trade.get("ticker") else []
        record_alert(
            alert_type="congress",
            headline=f"{trade['politician']} — {trade.get('trade_type','').upper()} {trade['ticker']}",
            analysis=claude_analysis,
            tickers=congress_tickers,
            score=trade.get("score"),
            politician=trade.get("politician"),
        )
        log.info(f"Congress alert sent: {trade['politician']} {trade['ticker']} (score: {trade['score']})")
        # Check for convergence with recent news/buy signals
        check_and_send_convergence(
            congress_tickers, "congress",
            f"{trade['politician']} traded {trade['ticker']}"
        )
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
    from batch_processor import get_queue_size
    batch_queued = get_queue_size()

    message = (
        f"Investment Bot v2 — Online\n"
        f"{timestamp}\n\n"
        f"Systems check:\n"
        f"• RSS feeds: {len(config.RSS_FEEDS)} sources\n"
        f"• Portfolio: {len(config.YOUR_TICKERS)} holdings\n"
        f"• Politicians watched: {len(config.WATCH_POLITICIANS)} names\n"
        f"• Min urgency: {config.MIN_URGENCY.upper()}\n"
        f"• Congress score threshold: {config.CONGRESS_SCORE_THRESHOLD}/10\n"
        f"• Batch queue: {batch_queued} articles pending\n\n"
        f"Alert types active:\n"
        f"  PORTFOLIO — impact on your holdings\n"
        f"  OPPORTUNITY — small cap plays\n"
        f"  BUY SIGNAL — company positive catalysts\n"
        f"  CONGRESS — politician stock trades\n"
        f"  IPO — upcoming IPO alerts\n"
        f"  SENTIMENT — Reddit/StockTwits spikes\n"
        f"  MOONSHOT — extended thinking deep analysis\n"
        f"  BATCH — overnight Tier 3 source processing\n\n"
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
        choices=[
            "news", "congress", "daily-summary", "weekly", "ipo", "morning",
            "performance", "sentiment", "batch-submit", "batch-retrieve", "moonshot", "test",
        ],
        default="news",
        help="Which function to run",
    )
    args = parser.parse_args()

    # Validate API key for modes that need Claude
    needs_claude = args.mode in ["news", "weekly", "ipo", "sentiment", "batch-submit", "moonshot"]
    if needs_claude and not config.CLAUDE_API_KEY:
        log.error("CLAUDE_API_KEY is not set. Set it as a GitHub Secret.")
        return

    mode_map = {
        "news": check_news,
        "congress": check_congress_trades,
        "daily-summary": send_daily_congress_summary,
        "weekly": weekly_suggestions,
        "ipo": lambda: check_ipos(send_fn=send_telegram),
        "morning": morning_briefing,
        "performance": _run_performance,
        "sentiment": lambda: check_sentiment(send_fn=send_telegram),
        "batch-submit": lambda: submit_batch(send_fn=send_telegram),
        "batch-retrieve": lambda: retrieve_batch_results(send_fn=send_telegram),
        "moonshot": lambda: run_moonshot_scan(send_fn=send_telegram),
        "test": run_test,
    }

    log.info(f"Running mode: {args.mode}")
    mode_map[args.mode]()


def _run_performance() -> None:
    """Import and run the weekly performance report."""
    import performance
    performance.send_weekly_performance_report()


if __name__ == "__main__":
    main()
