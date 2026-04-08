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


def format_trade_alert(trade: dict) -> str:
    """Format a single trade into a Telegram-ready message."""
    score = trade.get("score", 0)
    direction = "BUY" if "purchase" in trade.get("trade_type", "").lower() else "SELL"
    stars = "⭐" * min(score // 2, 5)

    # Direction emoji
    if direction == "BUY":
        emoji = "🟢"
    else:
        emoji = "🔴"

    return (
        f"{emoji} CONGRESS TRADE SIGNAL {stars}\n"
        f"Score: {score}/10\n\n"
        f"WHO: {trade['politician']}\n"
        f"TICKER: {trade['ticker']} — {trade.get('asset', '')[:60]}\n"
        f"ACTION: {direction} | {trade.get('amount', 'unknown amount')}\n"
        f"OWNER: {trade.get('owner', 'Self')}\n"
        f"DATE: {trade['date']}\n\n"
        f"WHY THIS MATTERS: {_trade_context(trade)}\n\n"
        f"{trade.get('link', '')}"
    )


def _trade_context(trade: dict) -> str:
    """One-line context for why this trade matters."""
    score = trade.get("score", 0)
    politician = trade.get("politician", "")
    ticker = trade.get("ticker", "")
    trade_type = trade.get("trade_type", "")

    if score >= 9:
        return f"VERY HIGH SIGNAL — {politician} is a historically well-timed trader."
    if score >= 7:
        return f"Strong signal — {politician} made a significant move on {ticker}. Research immediately."
    return f"{politician} traded {ticker}. Monitor for follow-up trades by other politicians."


def format_daily_summary(trades: list[dict]) -> str:
    """Format top trades into a daily summary Telegram message."""
    if not trades:
        return "Congressional Trading Summary: No high-signal trades in the last 24 hours."

    top = trades[:5]  # Top 5 by score
    lines = ["🏛 DAILY CONGRESS SUMMARY\n"]
    lines.append(f"Top signals from the last 24 hours:\n")

    for i, t in enumerate(top, 1):
        direction = "BUY" if "purchase" in t.get("trade_type", "").lower() else "SELL"
        lines.append(
            f"{i}. {t['politician']} — {direction} {t['ticker']} "
            f"({t.get('amount', '?')}) | Score: {t['score']}/10"
        )

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
