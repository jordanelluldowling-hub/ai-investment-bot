"""
Congressional Trading Tracker — v2

Fetches stock trades by US politicians and their family members from:
1. HouseStockWatcher (aggregates House of Representatives STOCK Act filings)
2. SenateStockWatcher (aggregates Senate STOCK Act filings)

Scores each trade 1-10. Alerts on:
- Any politician with score >= CONGRESS_SCORE_THRESHOLD (default 7)
- High-signal politicians with score >= 5

Trade deduplication via data/seen_trades.json prevents re-alerting the same
trade on every hourly run.

Usage:
    python congress_tracker.py               # Print recent high-score trades
    python congress_tracker.py --days 14     # Look back 14 days
    python congress_tracker.py --all         # Show all trades (no score filter)
    python congress_tracker.py --test-api    # Test API connectivity and print raw data
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

import anthropic
import requests

import config

log = logging.getLogger(__name__)

SEEN_TRADES_FILE = Path("data/seen_trades.json")

# --- High-signal politicians (historically well-timed trades) ---
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
    "gottheimer", "josh gottheimer",
    "schiff", "adam schiff",
}


def _trade_uid(trade: dict) -> str:
    """Stable unique ID for a trade — used for deduplication."""
    key = (
        f"{trade.get('politician', '')}"
        f"{trade.get('ticker', '')}"
        f"{trade.get('date', '')}"
        f"{trade.get('trade_type', '')}"
        f"{trade.get('amount', '')}"
    )
    return hashlib.md5(key.encode()).hexdigest()


def load_seen_trades() -> set:
    if SEEN_TRADES_FILE.exists():
        try:
            with open(SEEN_TRADES_FILE) as f:
                return set(json.load(f))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def save_seen_trades(seen: set) -> None:
    SEEN_TRADES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SEEN_TRADES_FILE, "w") as f:
        json.dump(list(seen), f)


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
            # Prefer disclosure_date for recency (when we'd learn about it)
            date_str = trade.get("disclosure_date", "") or trade.get("transaction_date", "")
            if not date_str:
                continue
            trade_date = _parse_date(date_str)
            if trade_date and trade_date < cutoff:
                continue

            ticker = trade.get("ticker", "").strip().upper()
            if not ticker or ticker in {"N/A", "--", ""}:
                continue

            recent.append({
                "source": "house",
                "politician": trade.get("representative", "Unknown").strip(),
                "ticker": ticker,
                "asset": trade.get("asset_description", ""),
                "trade_type": trade.get("type", "").lower(),
                "amount": trade.get("amount", ""),
                "owner": trade.get("owner", "self"),
                "date": date_str,
                "link": trade.get("ptr_link", ""),
            })
        except Exception:
            continue

    log.info(f"House: {len(recent)} trades in last {lookback_days} days")
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

            ticker = trade.get("ticker", "").strip().upper()
            if not ticker or ticker in {"N/A", "--", ""}:
                continue

            # Senate data may use different name fields
            politician = (
                trade.get("senator", "")
                or f"{trade.get('first_name', '')} {trade.get('last_name', '')}".strip()
                or "Unknown"
            )

            recent.append({
                "source": "senate",
                "politician": politician.strip(),
                "ticker": ticker,
                "asset": trade.get("asset_description", ""),
                "trade_type": trade.get("type", "").lower(),
                "amount": trade.get("amount", ""),
                "owner": trade.get("owner", "self"),
                "date": date_str,
                "link": trade.get("ptr_link", ""),
            })
        except Exception:
            continue

    log.info(f"Senate: {len(recent)} trades in last {lookback_days} days")
    return recent


def _parse_date(date_str: str):
    """Try multiple date formats used by the APIs."""
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y", "%B %d, %Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(date_str.strip()[:10], fmt[:10])
        except ValueError:
            continue
    return None


def _parse_amount(amount_str: str) -> int:
    """Convert amount range string like '$1,000,001 - $5,000,000' to lower bound."""
    if not amount_str:
        return 0
    nums = re.findall(r"[\d]+", amount_str.replace(",", ""))
    if not nums:
        return 0
    try:
        return int(nums[0])
    except ValueError:
        return 0


def score_trade(trade: dict) -> int:
    """
    Score a congressional trade 0-10.

    Factors:
    - Direction: buy = +3, partial sell = +2, full sell = +2
    - Amount: $1M+ = +4, $250K+ = +3, $100K+ = +2, $50K+ = +1
    - High-signal politician bonus: +2
    - Spouse/trust/joint ownership: +1
    - In our portfolio tickers: +1
    """
    score = 0
    politician = trade.get("politician", "").lower()
    ticker = trade.get("ticker", "").upper()
    trade_type = trade.get("trade_type", "").lower()
    amount_str = trade.get("amount", "")
    owner = trade.get("owner", "").lower()

    # Direction
    if "purchase" in trade_type:
        score += 3
    elif "sale_partial" in trade_type:
        score += 2
    elif "sale" in trade_type or "sell" in trade_type:
        score += 2
    elif "exchange" in trade_type:
        score += 1

    # Amount
    amount = _parse_amount(amount_str)
    if amount >= 1_000_000:
        score += 4
    elif amount >= 250_000:
        score += 3
    elif amount >= 100_000:
        score += 2
    elif amount >= 50_000:
        score += 1

    # High-signal politician bonus
    if any(hs in politician for hs in HIGH_SIGNAL_POLITICIANS):
        score += 2

    # Spouse/trust = often more deliberate trading
    if any(o in owner for o in ["spouse", "joint", "trust", "dependent"]):
        score += 1

    # In our portfolio
    if ticker in config.YOUR_TICKERS:
        score += 1

    return min(score, 10)


def filter_and_score_trades(trades: list[dict], score_threshold: int = None) -> list[dict]:
    """
    Score all trades. Alert on:
    - Any trade with score >= score_threshold (default CONGRESS_SCORE_THRESHOLD)
    - High-signal politicians at score >= 5 (lower bar, their trades are more valuable)

    NOTE: The old version required trades to match the watch list. Removed —
    too restrictive. We now alert on any politician making a significant move.
    """
    if score_threshold is None:
        score_threshold = config.CONGRESS_SCORE_THRESHOLD

    scored = []
    for trade in trades:
        score = score_trade(trade)
        trade["score"] = score

        politician = trade.get("politician", "").lower()
        is_high_signal = any(hs in politician for hs in HIGH_SIGNAL_POLITICIANS)
        effective_threshold = 5 if is_high_signal else score_threshold

        if score >= effective_threshold:
            scored.append(trade)

    scored.sort(key=lambda t: t["score"], reverse=True)
    return scored


def get_all_recent_trades(
    lookback_days: int = None,
    score_threshold: int = None,
    deduplicate: bool = True,
) -> list[dict]:
    """
    Fetch, score, deduplicate, and return high-signal trades.

    Args:
        lookback_days: how far back to look (default: CONGRESS_LOOKBACK_DAYS)
        score_threshold: minimum score to include
        deduplicate: if True, skip trades already seen in previous runs

    Returns:
        List of scored trade dicts, sorted by score descending
    """
    if lookback_days is None:
        lookback_days = config.CONGRESS_LOOKBACK_DAYS

    house = fetch_house_trades(lookback_days)
    senate = fetch_senate_trades(lookback_days)
    all_trades = house + senate

    if not all_trades:
        log.warning("No congressional trade data fetched from either API.")
        return []

    log.info(f"Total raw trades fetched: {len(all_trades)}")
    scored = filter_and_score_trades(all_trades, score_threshold)

    if not deduplicate:
        return scored

    # Filter out trades we've already alerted on
    seen = load_seen_trades()
    new_trades = [t for t in scored if _trade_uid(t) not in seen]

    log.info(f"After deduplication: {len(new_trades)} new trades (was {len(scored)})")
    return new_trades


def mark_trades_seen(trades: list[dict]) -> None:
    """Mark a list of trades as seen so they won't re-alert on the next hourly run."""
    seen = load_seen_trades()
    for trade in trades:
        seen.add(_trade_uid(trade))
    save_seen_trades(seen)


def analyse_trade_with_claude(trade: dict) -> str:
    """
    Ask Claude to interpret what a congressional trade means for investors.
    Returns structured analysis, or empty string if API not available.
    """
    if not config.CLAUDE_API_KEY:
        return ""

    direction = "BUY" if "purchase" in trade.get("trade_type", "").lower() else "SELL"
    client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)

    try:
        msg = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=350,
            messages=[{
                "role": "user",
                "content": f"""A US politician just disclosed a stock trade:

WHO: {trade['politician']}
ACTION: {direction} {trade['ticker']} — {trade.get('asset', '')}
AMOUNT: {trade.get('amount', 'unknown')}
OWNER: {trade.get('owner', 'Self')}
DATE FILED: {trade['date']}

Analyse this in exactly this format:
WHAT IT MEANS: [one sentence — what is this politician signalling with this trade?]
SECTOR PLAY: [what sector/theme/legislation might be driving this?]
FRONT-RUNNING RISK: [HIGH/MEDIUM/LOW — is this potentially based on non-public info?]
RELATED TICKERS: [2-3 other stocks that benefit from the same theme, with symbols]
SHOULD YOU FOLLOW: [YES/MAYBE/NO — one sentence reasoning]

Be direct. No preamble.""",
            }],
        )
        return msg.content[0].text
    except Exception as e:
        log.error(f"Claude trade analysis failed: {e}")
        return ""


def analyse_daily_trades_with_claude(trades: list[dict]) -> str:
    """
    Ask Claude to identify patterns across today's congressional trades.
    Returns summary analysis, or empty string if API not available.
    """
    if not trades or not config.CLAUDE_API_KEY:
        return ""

    client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)
    trades_text = "\n".join(
        f"- {t['politician']}: {'BUY' if 'purchase' in t.get('trade_type','').lower() else 'SELL'} "
        f"{t['ticker']} ({t.get('amount', '?')}) — score {t.get('score', 0)}/10"
        for t in trades[:10]
    )

    try:
        msg = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": f"""Congressional stock trades from the past week:
{trades_text}

Identify patterns across these trades in exactly this format:
PATTERN: [what theme/sector are politicians buying or selling?]
STRONGEST SIGNAL: [the single most interesting trade and why]
WHAT TO BUY: [1-2 specific tickers to research based on these trades]
WHAT TO WATCH: [1-2 upcoming legislative events that might explain these trades]
CONFIDENCE: [HIGH/MEDIUM/LOW — overall how significant are these signals?]

Be direct. No preamble.""",
            }],
        )
        return msg.content[0].text
    except Exception as e:
        log.error(f"Claude daily analysis failed: {e}")
        return ""


def format_trade_alert(trade: dict, claude_analysis: str = "") -> str:
    """Format a single trade alert for Telegram."""
    score = trade.get("score", 0)
    direction = "BUY" if "purchase" in trade.get("trade_type", "").lower() else "SELL"
    stars = "⭐" * min(score // 2, 5)
    emoji = "🟢" if direction == "BUY" else "🔴"
    timestamp = datetime.now().strftime("%d %b %Y %H:%M")

    msg = (
        f"{emoji} CONGRESS TRADE SIGNAL {stars}\n"
        f"Score: {score}/10 | {timestamp}\n\n"
        f"WHO: {trade['politician']}\n"
        f"TICKER: {trade['ticker']} — {trade.get('asset', '')[:60]}\n"
        f"ACTION: {direction} | {trade.get('amount', 'unknown amount')}\n"
        f"OWNER: {trade.get('owner', 'Self').title()}\n"
        f"DATE FILED: {trade['date']}\n"
    )

    if claude_analysis:
        msg += f"\nANALYSIS:\n{claude_analysis}\n"
    else:
        msg += f"\n{_trade_context(trade)}\n"

    if trade.get("link"):
        msg += f"\n{trade['link']}"

    return msg


def _trade_context(trade: dict) -> str:
    """Fallback one-liner when Claude analysis isn't available."""
    score = trade.get("score", 0)
    politician = trade.get("politician", "")
    ticker = trade.get("ticker", "")

    if score >= 9:
        return f"VERY HIGH SIGNAL — {politician} made a major move on {ticker}. Research immediately."
    if score >= 7:
        return f"Strong signal — {politician} made a significant trade on {ticker}."
    return f"{politician} traded {ticker}. Monitor for follow-up activity."


def format_daily_summary(trades: list[dict], claude_analysis: str = "") -> str:
    """Format a daily/weekly congress summary for Telegram."""
    if not trades:
        return (
            "🏛 CONGRESSIONAL TRADING SUMMARY\n\n"
            "No new high-signal trades filed in the last 7 days.\n"
            "Congress may be in recess or no significant disclosures filed."
        )

    top = trades[:5]
    lines = ["🏛 CONGRESSIONAL TRADING SUMMARY\n"]

    for i, t in enumerate(top, 1):
        direction = "BUY" if "purchase" in t.get("trade_type", "").lower() else "SELL"
        lines.append(
            f"{i}. {t['politician']} — {direction} ${t['ticker']} "
            f"({t.get('amount', '?')}) | Score: {t['score']}/10"
        )

    if claude_analysis:
        lines.append(f"\nAI PATTERN ANALYSIS:\n{claude_analysis}")

    lines.append(f"\nTotal high-signal trades: {len(trades)}")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--all", action="store_true", help="No score filter")
    parser.add_argument("--test-api", action="store_true", help="Test API connectivity")
    args = parser.parse_args()

    if args.test_api:
        print("Testing HouseStockWatcher API...")
        try:
            resp = requests.get(
                config.HOUSE_TRADES_URL,
                headers={"User-Agent": "investment-bot/2.0"},
                timeout=30,
            )
            data = resp.json()
            print(f"House API: {resp.status_code} — {len(data)} total records")
            if data:
                print(f"Sample record keys: {list(data[0].keys())}")
                print(f"Sample record: {data[0]}")
        except Exception as e:
            print(f"House API failed: {e}")

        print("\nTesting SenateStockWatcher API...")
        try:
            resp = requests.get(
                config.SENATE_TRADES_URL,
                headers={"User-Agent": "investment-bot/2.0"},
                timeout=30,
            )
            data = resp.json()
            print(f"Senate API: {resp.status_code} — {len(data)} total records")
            if data:
                print(f"Sample record keys: {list(data[0].keys())}")
                print(f"Sample record: {data[0]}")
        except Exception as e:
            print(f"Senate API failed: {e}")

    else:
        threshold = 0 if args.all else config.CONGRESS_SCORE_THRESHOLD
        trades = get_all_recent_trades(
            lookback_days=args.days,
            score_threshold=threshold,
            deduplicate=False,
        )

        if trades:
            print(f"\nFound {len(trades)} trade(s) in last {args.days} days:\n")
            for t in trades:
                print(format_trade_alert(t))
                print("-" * 60)
        else:
            print(f"No qualifying trades found in last {args.days} days.")
            print("Run with --all to see all trades regardless of score.")
            print("Run with --test-api to verify API connectivity.")
