"""
Performance Reporter — Phase 2

Reads alert history from tracker.py and sends weekly/monthly
performance summaries to Telegram.

This is the data that builds credibility for selling subscriptions:
"Our alerts: 73% accuracy | 4.2x avg return | 82% win rate"

Usage:
    python performance.py              # Print stats to console
    python performance.py --send       # Send weekly report to Telegram
    python performance.py --days 7     # Stats for last 7 days
"""

import argparse
import logging
import os
from datetime import datetime

import requests

import config
from tracker import get_stats, get_alerts_since, load_alerts

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def send_telegram(message: str) -> bool:
    """Send message to Telegram."""
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        print(message)
        return True
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": message},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        log.error(f"Telegram send failed: {e}")
        return False


def format_weekly_report() -> str:
    """Format a weekly performance summary for Telegram."""
    stats_7 = get_stats(days=7)
    stats_30 = get_stats(days=30)
    recent = get_alerts_since(days=7)
    timestamp = datetime.now().strftime("%d %b %Y")

    # --- Build type breakdown ---
    type_lines = []
    type_labels = {
        "portfolio": "Portfolio alerts",
        "opportunity": "Opportunity alerts",
        "buy_signal": "Buy signals",
        "congress": "Congress trades",
        "ipo": "IPO alerts",
    }
    for atype, label in type_labels.items():
        count = stats_7["by_type"].get(atype, 0)
        if count > 0:
            type_lines.append(f"  {label}: {count}")

    type_summary = "\n".join(type_lines) if type_lines else "  No alerts this week"

    # --- Top tickers ---
    top_tickers = stats_7["top_tickers"]
    tickers_str = (
        ", ".join(f"{t[0]} ({t[1]}x)" for t in top_tickers)
        if top_tickers else "None yet"
    )

    # --- Win rate (only meaningful once outcomes are tracked) ---
    if stats_30["wins"] + stats_30["losses"] > 0:
        perf_line = (
            f"30-day win rate: {stats_30['win_rate']}% "
            f"({stats_30['wins']}W / {stats_30['losses']}L)"
        )
    else:
        perf_line = "Win rate: tracking started — outcomes pending"

    # --- High score alerts ---
    high_score = stats_7["high_score_alerts"]

    report = (
        f"📊 WEEKLY PERFORMANCE REPORT\n"
        f"{timestamp}\n\n"
        f"THIS WEEK:\n"
        f"  Total alerts sent: {stats_7['total']}\n"
        f"{type_summary}\n"
        f"  High-score signals (8+): {high_score}\n\n"
        f"MOST ALERTED TICKERS:\n"
        f"  {tickers_str}\n\n"
        f"PERFORMANCE (30 days):\n"
        f"  {perf_line}\n"
        f"  Total tracked: {stats_30['total']} alerts\n\n"
        f"HOW TO IMPROVE:\n"
        f"  As outcomes are confirmed, win rate accuracy\n"
        f"  will build — this data is your future pitch\n"
        f"  to paid subscribers.\n"
    )

    # --- Add recent highlights ---
    buy_signals = [a for a in recent if a["type"] == "buy_signal" and (a.get("score") or 0) >= 8]
    congress_signals = [a for a in recent if a["type"] == "congress" and (a.get("score") or 0) >= 8]

    highlights = []
    for a in (buy_signals + congress_signals)[:3]:
        score = a.get("score", "?")
        tickers = ", ".join(a["tickers"]) if a.get("tickers") else "?"
        highlights.append(f"  • {a['type'].upper()} | {tickers} | score {score}")

    if highlights:
        report += "\nTOP SIGNALS THIS WEEK:\n" + "\n".join(highlights)

    return report


def format_monthly_report() -> str:
    """Format a monthly performance summary."""
    stats = get_stats(days=30)
    timestamp = datetime.now().strftime("%B %Y")

    type_lines = []
    for atype, count in stats["by_type"].items():
        type_lines.append(f"  {atype.replace('_', ' ').title()}: {count}")

    top_tickers = ", ".join(f"{t[0]}" for t in stats["top_tickers"]) or "None"

    return (
        f"📈 MONTHLY REPORT — {timestamp}\n\n"
        f"ALERTS SENT: {stats['total']}\n"
        + "\n".join(type_lines) + "\n\n"
        f"WIN RATE: {stats['win_rate']}% "
        f"({stats['wins']}W / {stats['losses']}L / {stats['pending']} pending)\n\n"
        f"MOST ACTIVE TICKERS: {top_tickers}\n"
        f"HIGH CONVICTION SIGNALS: {stats['high_score_alerts']}\n"
    )


def send_weekly_performance_report() -> None:
    """Called by GitHub Actions every Sunday."""
    log.info("Generating weekly performance report...")
    report = format_weekly_report()
    send_telegram(report)
    log.info("Weekly performance report sent.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="Send to Telegram")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--monthly", action="store_true")
    args = parser.parse_args()

    if args.monthly:
        report = format_monthly_report()
    else:
        report = format_weekly_report()

    if args.send:
        send_telegram(report)
    else:
        print(report)
        total = get_stats(args.days)["total"]
        print(f"\nTotal alerts in last {args.days} days: {total}")
        all_alerts = load_alerts()
        print(f"Total alerts ever tracked: {len(all_alerts)}")
