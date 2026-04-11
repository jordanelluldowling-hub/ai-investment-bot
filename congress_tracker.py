"""
Congressional Trading Tracker — v2

Fetches stock trades by US politicians and their family members from:
1. HouseStockWatcher (aggregates House of Representatives STOCK Act filings)
2. SenateStockWatcher (aggregates Senate STOCK Act filings)
3. QuiverQuant API (free tier, backup source)

Scores each trade 1-10 and only returns trades scoring >= CONGRESS_SCORE_THRESHOLD.

Usage:
    python congress_tracker.py               # Print recent high-score trades
    python congress_tracker.py --days 14     # Look back 14 days
    python congress_tracker.py --all         # Show all trades (no score filter)
"""

import json
import logging
import re
from datetime import datetime, timedelta

import anthropic
import requests

import config

log = logging.getLogger(__name__)


# --- High-signal politicians (well-timed trades historically) ---
HIGH_SIGNAL_POLITICIANS = {
    "pelosi", "nancy pelosi", "paul pelosi",
    "tuberville", "tommy tuberville",
    "burr", "richard burr",
    "perdue", "david perdue",
    "loeffler", "kelly loeffler", "jeff sprecher",
    "ossoff", "jon ossoff", "alisha kramer",
    "paul", "rand paul", "kelley paul",
    "mcconnell", "mitch mcconnell", "elaine chao",
    "kushner", "jared kushner",
}

# --- Sectors with committee alignment signals ---
# When defense committee members buy defense stocks = strong signal
SECTOR_KEYWORDS = {
    "defense": ["LMT", "RTX", "NOC", "BA", "GD", "RHM", "AXON", "ONDS"],
    "tech": ["NVDA", "MSFT", "AAPL", "META", "GOOGL", "PLTR", "IONQ", "CRWV", "RGTI"],
    "pharma": ["PFE", "JNJ", "MRNA", "BMY", "ABBV", "LLY"],
    "energy": ["XOM", "CVX", "SHEL", "COP", "SLB"],
    "finance": ["JPM", "BAC", "GS", "V", "MA"],
    "crypto": ["BTC", "ETH", "COIN", "MSTR", "MARA"],
}


def fetch_house_trades(lookback_days: int = 7) -> list[dict]:
    """Fetch recent House of Representatives stock trades from HouseStockWatcher."""
    log.info("Fetching House stock trade data...")
    try:
        resp = requests.get(
            config.HOUSE_TRADES_URL,
            headers={"User-Agent": "investment-bot/2.0 (research purposes)"},
            timeout=30,
        )
        resp.raise_for_status()
        all_trades = resp.json()
    except Exception as e:
        log.error(f"Failed to fetch House trades: {e}")
        return []

    cutoff = datetime.now() - timedelta(days=lookback_days)
    recent = []

    for trade in all_trades:
        try:
            # Parse disclosure date
            date_str = trade.get("disclosure_date", "") or trade.get("transaction_date", "")
            if not date_str:
                continue
            trade_date = _parse_date(date_str)
            if trade_date and trade_date < cutoff:
                continue

            recent.append({
                "source": "house",
                "politician": trade.get("representative", "Unknown"),
                "ticker": trade.get("ticker", "").strip().upper(),
                "asset": trade.get("asset_description", ""),
                "trade_type": trade.get("type", "").lower(),
                "amount": trade.get("amount", ""),
                "owner": trade.get("owner", "self"),
                "date": date_str,
                "link": trade.get("ptr_link", ""),
            })
        except Exception:
            continue

    log.info(f"House: found {len(recent)} trades in last {lookback_days} days")
    return recent


def fetch_senate_trades(lookback_days: int = 7) -> list[dict]:
    """Fetch recent Senate stock trades from SenateStockWatcher."""
    log.info("Fetching Senate stock trade data...")
    try:
        resp = requests.get(
            config.SENATE_TRADES_URL,
            headers={"User-Agent": "investment-bot/2.0 (research purposes)"},
            timeout=30,
        )
        resp.raise_for_status()
        all_trades = resp.json()
    except Exception as e:
        log.error(f"Failed to fetch Senate trades: {e}")
        return []

    cutoff = datetime.now() - timedelta(days=lookback_days)
    recent = []

    for trade in all_trades:
        try:
            date_str = trade.get("disclosure_date", "") or trade.get("transaction_date", "")
            if not date_str:
                continue
            trade_date = _parse_date(date_str)
            if trade_date and trade_date < cutoff:
                continue

            recent.append({
                "source": "senate",
                "politician": trade.get("senator", "Unknown"),
                "ticker": trade.get("ticker", "").strip().upper(),
                "asset": trade.get("asset_description", ""),
                "trade_type": trade.get("type", "").lower(),
                "amount": trade.get("amount", ""),
                "owner": trade.get("owner", "self"),
                "date": date_str,
                "link": trade.get("ptr_link", ""),
            })
        except Exception:
            continue

    log.info(f"Senate: found {len(recent)} trades in last {lookback_days} days")
    return recent


def _parse_date(date_str: str):
    """Try multiple date formats."""
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y", "%B %d, %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def _parse_amount(amount_str: str) -> int:
    """Convert amount range string to approximate dollar value."""
    if not amount_str:
        return 0
    # Extract the first number from the range
    nums = re.findall(r"[\d,]+", amount_str.replace(",", ""))
    if not nums:
        return 0
    try:
        return int(nums[0])
    except ValueError:
        return 0


def score_trade(trade: dict) -> int:
    """
    Score a congressional trade from 0-10.
    Higher = stronger investment signal.

    Scoring factors:
    - Trade direction (buy/sell)
    - Trade size
    - Politician signal strength
    - Ownership type (spouse/trust = more sophisticated)
    - Sector + ticker relevance
    """
    score = 0
    politician = trade.get("politician", "").lower()
    ticker = trade.get("ticker", "").upper()
    trade_type = trade.get("trade_type", "").lower()
    amount_str = trade.get("amount", "")
    owner = trade.get("owner", "").lower()

    # --- Direction signal ---
    if "purchase" in trade_type:
        score += 3  # Buying = conviction
    elif "sale_partial" in trade_type:
        score += 2  # Partial sale = trimming position (still useful)
    elif "sale_full" in trade_type or "sale" in trade_type:
        score += 2  # Full exit = also a signal (short?)
    elif "exchange" in trade_type:
        score += 1

    # --- Amount size ---
    amount = _parse_amount(amount_str)
    if amount >= 1_000_000:
        score += 4
    elif amount >= 250_000:
        score += 3
    elif amount >= 100_000:
        score += 2
    elif amount >= 50_000:
        score += 1

    # --- High-signal politician bonus ---
    if any(hs in politician for hs in HIGH_SIGNAL_POLITICIANS):
        score += 2

    # --- Spouse/trust = often more sophisticated trading ---
    if any(o in owner for o in ["spouse", "joint", "trust", "dependent"]):
        score += 1

    # --- Known high-upside tickers ---
    if ticker in ["NVDA", "PLTR", "IONQ", "AXON", "CRWV", "RGTI", "ONDS"]:
        score += 1

    return min(score, 10)


def is_watched_politician(politician: str) -> bool:
    """Check if politician/owner matches our watch list."""
    politician_lower = politician.lower()
    return any(name in politician_lower for name in config.WATCH_POLITICIANS)


def filter_and_score_trades(trades: list[dict], score_threshold: int = None) -> list[dict]:
    """
    Filter trades to watched politicians, score them, return high-score ones.
    """
    if score_threshold is None:
        score_threshold = config.CONGRESS_SCORE_THRESHOLD

    scored = []
    for trade in trades:
        politician = trade.get("politician", "")
        owner = trade.get("owner", "")
        combined = f"{politician} {owner}".lower()

        # Check if any watched name appears
        if not any(name in combined for name in config.WATCH_POLITICIANS):
            continue

        score = score_trade(trade)
        trade["score"] = score

        if score >= score_threshold:
            scored.append(trade)

    # Sort by score descending
    scored.sort(key=lambda t: t["score"], reverse=True)
    return scored


def get_all_recent_trades(lookback_days: int = None, score_threshold: int = None) -> list[dict]:
    """Main entry point: fetch, filter, and score all recent trades."""
    if lookback_days is None:
        lookback_days = config.CONGRESS_LOOKBACK_DAYS

    house = fetch_house_trades(lookback_days)
    senate = fetch_senate_trades(lookback_days)
    all_trades = house + senate

    if not all_trades:
        log.warning("No congressional trades fetched.")
        return []

    scored = filter_and_score_trades(all_trades, score_threshold)
    log.info(f"Found {len(scored)} high-signal trades (score >= {score_threshold or config.CONGRESS_SCORE_THRESHOLD})")
    return scored


def analyse_trade_with_claude(trade: dict) -> str:
    """
    Ask Claude to interpret a congressional trade:
    - What does it likely mean?
    - Which sectors / stocks could benefit?
    - What upcoming policy or event might this be front-running?
    """
    if not config.CLAUDE_API_KEY:
        return "Claude analysis not available (API key not set)."

    client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)
    direction = "BUY" if "purchase" in trade.get("trade_type", "").lower() else "SELL"

    try:
        msg = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=400,
            messages=[
                {
                    "role": "user",
                    "content": f"""
A US politician just made a significant stock trade:

POLITICIAN: {trade['politician']}
TRADE: {direction} {trade['ticker']} ({trade.get('asset', 'unknown asset')})
AMOUNT: {trade.get('amount', 'unknown')}
OWNER: {trade.get('owner', 'self')}
DATE: {trade['date']}
SIGNAL SCORE: {trade.get('score', '?')}/10

Answer in exactly this format:
WHAT IT MEANS: [One sentence — what is this politician likely anticipating?]
SECTOR PLAY: [What sector or theme does this trade signal? e.g. defense boom, AI spending, pharma M&A]
FRONT-RUNNING: [What upcoming policy, bill, contract, or event could this be based on insider knowledge of?]
RELATED STOCKS: [2-3 other tickers that could benefit from the same signal]
SHOULD YOU ACT: [Yes — buy {trade['ticker']} / Yes — buy related stocks / Watch and wait / No signal]

Be direct. No preamble.
""",
                }
            ],
        )
        return msg.content[0].text
    except Exception as e:
        log.error(f"Claude trade analysis failed: {e}")
        return "Analysis unavailable."


def analyse_daily_trades_with_claude(trades: list[dict]) -> str:
    """
    Ask Claude to identify patterns across multiple trades in the same day.
    Useful for the 6pm daily summary.
    """
    if not trades or not config.CLAUDE_API_KEY:
        return ""

    client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)

    # Summarise trades as text for the prompt
    trade_lines = []
    for t in trades[:10]:  # Limit to top 10 to stay within tokens
        direction = "BUY" if "purchase" in t.get("trade_type", "").lower() else "SELL"
        trade_lines.append(
            f"- {t['politician']}: {direction} {t['ticker']} ({t.get('amount', '?')}) | Score {t.get('score', '?')}/10"
        )

    trades_text = "\n".join(trade_lines)

    try:
        msg = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": f"""
Here are today's congressional stock trades (high-signal only):

{trades_text}

Analyse these as a group:
PATTERN: [What theme or sector are politicians clustering around today?]
STRONGEST SIGNAL: [The single most convincing trade and why]
WHAT TO BUY: [Top 1-2 tickers an investor should research based on these signals]
WHAT TO WATCH: [Any upcoming event (bill vote, earnings, contract award) that might explain these trades]
CONFIDENCE: HIGH / MEDIUM / LOW in these signals overall

Be direct. One paragraph max per field.
""",
                }
            ],
        )
        return msg.content[0].text
    except Exception as e:
        log.error(f"Claude daily summary analysis failed: {e}")
        return ""


def format_trade_alert(trade: dict, claude_analysis: str = "") -> str:
    """Format a single trade into a Telegram-ready message, including Claude's read."""
    score = trade.get("score", 0)
    direction = "BUY" if "purchase" in trade.get("trade_type", "").lower() else "SELL"
    stars = "⭐" * min(score // 2, 5)
    emoji = "🟢" if direction == "BUY" else "🔴"

    base = (
        f"{emoji} CONGRESS TRADE SIGNAL {stars}\n"
        f"Score: {score}/10\n\n"
        f"WHO: {trade['politician']}\n"
        f"TICKER: {trade['ticker']} — {trade.get('asset', '')[:60]}\n"
        f"ACTION: {direction} | {trade.get('amount', 'unknown amount')}\n"
        f"OWNER: {trade.get('owner', 'Self')}\n"
        f"DATE: {trade['date']}\n"
    )

    if claude_analysis:
        base += f"\nCLAUDE ANALYSIS:\n{claude_analysis}\n"

    base += f"\n{trade.get('link', '')}"
    return base


def format_daily_summary(trades: list[dict], claude_analysis: str = "") -> str:
    """Format top trades into a daily summary Telegram message."""
    if not trades:
        return "Congressional Trading Summary: No high-signal trades in the last 24 hours."

    top = trades[:5]
    lines = ["🏛 DAILY CONGRESS SUMMARY\n"]
    lines.append("Top signals from the last 24 hours:\n")

    for i, t in enumerate(top, 1):
        direction = "BUY" if "purchase" in t.get("trade_type", "").lower() else "SELL"
        lines.append(
            f"{i}. {t['politician']} — {direction} {t['ticker']} "
            f"({t.get('amount', '?')}) | Score: {t['score']}/10"
        )

    if claude_analysis:
        lines.append(f"\nCLAUDE PATTERN ANALYSIS:\n{claude_analysis}")

    lines.append(f"\nTotal high-signal trades today: {len(trades)}")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--all", action="store_true", help="Show all trades without score filter")
    args = parser.parse_args()

    threshold = 0 if args.all else config.CONGRESS_SCORE_THRESHOLD
    trades = get_all_recent_trades(lookback_days=args.days, score_threshold=threshold)

    if trades:
        print(f"\nFound {len(trades)} trade(s):\n")
        for t in trades:
            print(format_trade_alert(t))
            print("-" * 60)
    else:
        print("No qualifying trades found.")
