"""
Alert Tracker — Phase 2

Records every alert sent by the bot to data/alerts.json.
GitHub Actions commits this file back to the repo after each run,
giving persistent storage without any external database.

Data tracked per alert:
- type (portfolio / opportunity / buy_signal / congress / ipo)
- ticker(s) mentioned
- headline that triggered it
- Claude's analysis
- signal score (if applicable)
- timestamp sent
- outcome (win/loss/pending — updated manually or in Phase 3)
"""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

DATA_DIR = Path("data")
ALERTS_FILE = DATA_DIR / "alerts.json"
STATS_FILE = DATA_DIR / "stats.json"


def _ensure_data_dir():
    DATA_DIR.mkdir(exist_ok=True)


def load_alerts() -> list[dict]:
    """Load all saved alerts from disk."""
    if ALERTS_FILE.exists():
        try:
            with open(ALERTS_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_alerts(alerts: list[dict]) -> None:
    """Write alert list to disk."""
    _ensure_data_dir()
    with open(ALERTS_FILE, "w") as f:
        json.dump(alerts, f, indent=2)


def record_alert(
    alert_type: str,
    headline: str,
    analysis: str,
    tickers: list[str] = None,
    score: int = None,
    confidence: str = None,
    politician: str = None,
) -> str:
    """
    Record a sent alert to the tracker.

    Args:
        alert_type: "portfolio" / "opportunity" / "buy_signal" / "congress" / "ipo"
        headline: the news headline or event that triggered it
        analysis: Claude's full analysis text
        tickers: list of ticker symbols mentioned (e.g. ["NVDA", "PLTR"])
        score: signal strength score if applicable (1-10 or 0-100)
        confidence: "high" / "medium" / "low"
        politician: politician name for congress alerts

    Returns:
        alert_id string
    """
    _ensure_data_dir()
    alerts = load_alerts()

    alert_id = hashlib.md5(
        f"{alert_type}{headline}{datetime.now().isoformat()}".encode()
    ).hexdigest()[:12]

    record = {
        "id": alert_id,
        "type": alert_type,
        "headline": headline[:200],  # cap length
        "analysis": analysis[:1000],  # cap length
        "tickers": tickers or [],
        "score": score,
        "confidence": confidence,
        "politician": politician,
        "sent_at": datetime.now().isoformat(),
        "outcome": "pending",   # pending / win / loss / neutral
        "return_pct": None,     # filled in Phase 3 with price tracking
        "notes": "",
    }

    alerts.append(record)
    save_alerts(alerts)
    log.info(f"Alert recorded: [{alert_type}] {headline[:60]}... (id: {alert_id})")
    return alert_id


def get_alerts_since(days: int) -> list[dict]:
    """Return alerts sent in the last N days."""
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(days=days)
    alerts = load_alerts()
    return [
        a for a in alerts
        if datetime.fromisoformat(a["sent_at"]) >= cutoff
    ]


def get_stats(days: int = 30) -> dict:
    """
    Calculate performance statistics for alerts sent in the last N days.

    Returns dict with:
    - total: total alerts sent
    - by_type: breakdown by alert type
    - wins / losses / pending: outcome counts
    - win_rate: percentage (wins / decided)
    - top_tickers: most frequently alerted tickers
    - high_score_alerts: alerts with score >= 8
    """
    alerts = get_alerts_since(days)

    by_type = {}
    wins = losses = pending = 0
    ticker_counts = {}

    for a in alerts:
        # Count by type
        atype = a.get("type", "unknown")
        by_type[atype] = by_type.get(atype, 0) + 1

        # Count outcomes
        outcome = a.get("outcome", "pending")
        if outcome == "win":
            wins += 1
        elif outcome == "loss":
            losses += 1
        else:
            pending += 1

        # Count tickers
        for ticker in a.get("tickers", []):
            ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1

    decided = wins + losses
    win_rate = round((wins / decided * 100) if decided > 0 else 0, 1)

    top_tickers = sorted(ticker_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    high_score = [a for a in alerts if (a.get("score") or 0) >= 8]

    return {
        "total": len(alerts),
        "by_type": by_type,
        "wins": wins,
        "losses": losses,
        "pending": pending,
        "win_rate": win_rate,
        "top_tickers": top_tickers,
        "high_score_alerts": len(high_score),
        "period_days": days,
    }
