"""
Sentiment Tracker — Phase 3

Monitors Reddit and StockTwits for sudden spikes in ticker mentions.
A spike = early signal before mainstream news picks it up.

Sources:
- StockTwits trending API (free, no auth)
- Reddit r/wallstreetbets, r/stocks, r/investing, r/smallstreetbets (RSS)

Signal logic:
- StockTwits trending ticker that's in your portfolio → SENTIMENT ALERT
- Reddit mentions spike (5+ mentions in last hour) → SENTIMENT ALERT
- Sentiment alert on a ticker that also has congress/buy_signal → CONVERGENCE

Usage:
    python sentiment_tracker.py          # Check and print results
    python sentiment_tracker.py --send   # Send alerts to Telegram
"""

import json
import logging
import re
import time
from collections import Counter
from datetime import datetime, timedelta

import requests

import config
from tracker import record_alert

log = logging.getLogger(__name__)

# Words that look like tickers but aren't — same list as bot.py
_NON_TICKERS = {
    "AT", "BE", "BY", "DO", "GO", "IF", "IN", "IS", "IT", "ME",
    "MY", "NO", "OF", "ON", "OR", "SO", "TO", "UP", "US", "WE",
    "AND", "BUT", "FOR", "NOT", "THE", "WHO", "WHY", "CEO", "CFO",
    "IPO", "ETF", "USA", "GDP", "CPI", "FDA", "SEC", "OTC",
    "GAS", "EPS", "RSI", "ATH", "DCA", "BUY", "SELL", "HIGH",
    "LOW", "HOLD", "NEWS", "RATE", "TOP", "KEY", "NEW", "NOW",
    "GET", "SET", "YES", "NAV", "TAX", "ESG", "OIL", "LNG",
    "WSB", "DD", "YOLO", "IMO", "EOD", "EOW", "AH", "PM",
}


def fetch_stocktwits_trending() -> list[dict]:
    """
    Fetch trending tickers from StockTwits public API.
    Returns list of {ticker, sentiment, watchers_count, message_count}
    No API key required.
    """
    try:
        resp = requests.get(
            config.STOCKTWITS_TRENDING_URL,
            headers={"User-Agent": "investment-bot/2.0"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        symbols = data.get("response", {}).get("messages", [])

        trending = []
        for msg in symbols[:30]:
            symbol_info = msg.get("symbols", [{}])[0] if msg.get("symbols") else {}
            ticker = symbol_info.get("symbol", "")
            if ticker and ticker not in _NON_TICKERS:
                trending.append({
                    "ticker": ticker.upper(),
                    "company": symbol_info.get("title", ""),
                    "sentiment": msg.get("entities", {}).get("sentiment", {}).get("basic", ""),
                    "source": "stocktwits",
                })

        log.info(f"StockTwits: {len(trending)} trending tickers")
        return trending

    except Exception as e:
        log.warning(f"StockTwits fetch failed: {e}")
        return []


def fetch_reddit_mentions(limit_per_feed: int = 25) -> Counter:
    """
    Fetch recent posts from Reddit finance subs and count ticker mentions.
    Returns Counter of {ticker: mention_count}.
    Uses JSON API (no auth needed for public subreddits).
    """
    ticker_counts: Counter = Counter()
    headers = {"User-Agent": "investment-bot/2.0 (research purposes)"}

    for feed_url in config.REDDIT_FEEDS:
        try:
            resp = requests.get(feed_url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            posts = data.get("data", {}).get("children", [])

            for post in posts[:limit_per_feed]:
                post_data = post.get("data", {})
                title = post_data.get("title", "")
                selftext = post_data.get("selftext", "")
                text = f"{title} {selftext}"

                # Extract ticker mentions ($NVDA or standalone NVDA in context)
                dollar_tickers = re.findall(r'\$([A-Z]{2,5})\b', text)
                plain_tickers = re.findall(r'\b([A-Z]{2,5})\b', text)

                for t in dollar_tickers:
                    if t not in _NON_TICKERS:
                        ticker_counts[t] += 2  # $ prefix = stronger signal

                for t in plain_tickers:
                    if t not in _NON_TICKERS and len(t) >= 3:
                        ticker_counts[t] += 1

            time.sleep(0.5)  # Respect Reddit rate limits

        except Exception as e:
            log.warning(f"Reddit fetch failed for {feed_url}: {e}")
            continue

    log.info(f"Reddit: {len(ticker_counts)} unique tickers mentioned")
    return ticker_counts


def get_portfolio_overlap(tickers: list[str]) -> list[str]:
    """Return which tickers are in your portfolio."""
    return [t for t in tickers if t.upper() in config.YOUR_TICKERS]


def format_sentiment_alert(ticker: str, source: str, details: dict) -> str:
    """Format a sentiment spike alert for Telegram."""
    timestamp = datetime.now().strftime("%d %b %Y %H:%M")
    in_portfolio = ticker.upper() in config.YOUR_TICKERS

    portfolio_note = "IN YOUR PORTFOLIO" if in_portfolio else "NOT in portfolio — potential new play"
    sentiment = details.get("sentiment", "").upper() or "UNKNOWN"
    count = details.get("count", "")
    count_str = f"{count} mentions" if count else ""

    return (
        f"📡 SENTIMENT SPIKE — {ticker}\n"
        f"{timestamp}\n\n"
        f"SOURCE: {source.upper()}\n"
        f"TICKER: {ticker} — {portfolio_note}\n"
        f"SENTIMENT: {sentiment}\n"
        f"{count_str}\n\n"
        f"WHAT THIS MEANS: Sudden spike in social mentions is often\n"
        f"an early signal before institutional coverage picks it up.\n\n"
        f"ACTION: Research {ticker} now — check why it's trending,\n"
        f"look for underlying catalyst (news, earnings, contract).\n"
        f"Cross-reference with your other alerts."
    )


def check_sentiment(send_fn=None) -> list[dict]:
    """
    Main entry point: check StockTwits + Reddit for sentiment spikes.
    Alerts on:
    - Any portfolio ticker trending on StockTwits
    - Any ticker with 5+ Reddit mentions that's in your portfolio
    - Any strongly trending ticker (high count) as a potential new play

    Args:
        send_fn: function to send Telegram messages

    Returns:
        List of sentiment signal dicts
    """
    log.info("Checking social sentiment...")
    signals = []

    # --- StockTwits ---
    trending = fetch_stocktwits_trending()
    trending_tickers = {t["ticker"] for t in trending}
    portfolio_trending = get_portfolio_overlap(list(trending_tickers))

    for ticker in portfolio_trending:
        detail = next((t for t in trending if t["ticker"] == ticker), {})
        signal = {
            "ticker": ticker,
            "source": "stocktwits",
            "sentiment": detail.get("sentiment", ""),
            "count": None,
            "in_portfolio": True,
        }
        signals.append(signal)

        if send_fn:
            alert = format_sentiment_alert(ticker, "StockTwits", detail)
            send_fn(alert)
            record_alert(
                alert_type="sentiment",
                headline=f"{ticker} trending on StockTwits",
                analysis=alert,
                tickers=[ticker],
                confidence="medium",
            )
            log.info(f"Sentiment alert sent: {ticker} trending on StockTwits")

    # --- Reddit ---
    mention_counts = fetch_reddit_mentions()
    threshold = config.REDDIT_MENTION_THRESHOLD

    # Check portfolio tickers first
    for ticker in config.YOUR_TICKERS:
        count = mention_counts.get(ticker, 0)
        if count >= threshold:
            signal = {
                "ticker": ticker,
                "source": "reddit",
                "sentiment": "bullish" if count > threshold * 2 else "neutral",
                "count": count,
                "in_portfolio": True,
            }
            signals.append(signal)

            if send_fn:
                alert = format_sentiment_alert(ticker, "Reddit", {"count": count, "sentiment": signal["sentiment"]})
                send_fn(alert)
                record_alert(
                    alert_type="sentiment",
                    headline=f"{ticker} — {count} Reddit mentions",
                    analysis=alert,
                    tickers=[ticker],
                    confidence="medium",
                )
                log.info(f"Sentiment alert sent: {ticker} — {count} Reddit mentions")

    # Also flag any non-portfolio ticker with very high mentions (potential new play)
    top_non_portfolio = [
        (t, c) for t, c in mention_counts.most_common(10)
        if t not in config.YOUR_TICKERS and c >= threshold * 3
    ]
    for ticker, count in top_non_portfolio[:3]:
        signal = {
            "ticker": ticker,
            "source": "reddit",
            "sentiment": "high_momentum",
            "count": count,
            "in_portfolio": False,
        }
        signals.append(signal)

        if send_fn:
            alert = format_sentiment_alert(ticker, "Reddit", {"count": count, "sentiment": "HIGH MOMENTUM"})
            send_fn(alert)
            log.info(f"Momentum alert: {ticker} — {count} Reddit mentions (not in portfolio)")

    log.info(f"Sentiment check complete. {len(signals)} signals found.")
    return signals


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()

    from bot import send_telegram
    send_fn = send_telegram if args.send else None

    signals = check_sentiment(send_fn=send_fn)
    print(f"\nFound {len(signals)} sentiment signals:")
    for s in signals:
        print(f"  {s['ticker']} via {s['source']} — {s.get('count', '?')} mentions | sentiment: {s.get('sentiment')}")
