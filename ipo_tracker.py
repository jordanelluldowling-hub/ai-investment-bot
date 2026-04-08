"""
IPO Tracker — v2

Monitors upcoming IPOs and scores them for first-day pop potential.

Sources:
- NASDAQ IPO Calendar RSS
- SEC EDGAR S-1 filings (new company registrations)

Scores each IPO 0-100 and alerts on strong ones (>= 65).

Usage:
    python ipo_tracker.py            # Check upcoming IPOs
    python ipo_tracker.py --test     # Test Telegram message
"""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

import anthropic
import feedparser
import requests

import config

log = logging.getLogger(__name__)

# --- IPO Data Sources ---
NASDAQ_IPO_RSS = "https://www.nasdaq.com/feed/rssoutbound?category=IPOs"
SEC_S1_SEARCH = "https://efts.sec.gov/LATEST/search-index?forms=S-1&dateRange=custom&startdt={}&enddt={}"

# --- Cache to avoid duplicate IPO alerts ---
IPO_CACHE_FILE = Path("seen_ipos.json")


def load_ipo_cache() -> set:
    if IPO_CACHE_FILE.exists():
        with open(IPO_CACHE_FILE) as f:
            return set(json.load(f))
    return set()


def save_ipo_cache(seen: set) -> None:
    with open(IPO_CACHE_FILE, "w") as f:
        json.dump(list(seen), f)


def ipo_id(title: str, link: str = "") -> str:
    return hashlib.md5(f"{title}{link}".encode()).hexdigest()


def fetch_ipo_news() -> list[dict]:
    """Fetch IPO news from NASDAQ RSS feed."""
    log.info("Fetching NASDAQ IPO calendar...")
    ipos = []
    seen = load_ipo_cache()

    try:
        feed = feedparser.parse(NASDAQ_IPO_RSS)
        for entry in feed.entries[:20]:
            title = entry.get("title", "")
            summary = entry.get("summary", entry.get("description", ""))
            link = entry.get("link", "")
            iid = ipo_id(title, link)

            if iid in seen:
                continue

            # Only include if it's about an actual IPO event
            lower = (title + " " + summary).lower()
            if any(kw in lower for kw in ["ipo", "goes public", "initial public offering", "s-1", "listing"]):
                ipos.append({
                    "id": iid,
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "source": "nasdaq-rss",
                })
    except Exception as e:
        log.warning(f"NASDAQ IPO RSS failed: {e}")

    return ipos


def fetch_sec_s1_filings() -> list[dict]:
    """Fetch recent S-1 filings from SEC EDGAR (companies going public)."""
    from datetime import timedelta
    today = datetime.now()
    week_ago = today - timedelta(days=7)
    url = SEC_S1_SEARCH.format(week_ago.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))
    log.info("Fetching SEC S-1 filings...")

    filings = []
    seen = load_ipo_cache()

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "investment-bot/2.0 (research purposes)"},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()

        hits = data.get("hits", {}).get("hits", [])
        for hit in hits[:10]:
            source = hit.get("_source", {})
            title = source.get("display_names", ["Unknown Company"])[0] + " S-1 Filing"
            summary = f"Company: {source.get('display_names', ['?'])[0]} | Filed: {source.get('file_date', '?')}"
            link = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={source.get('entity_id', '')}&type=S-1"
            iid = ipo_id(title)

            if iid not in seen:
                filings.append({
                    "id": iid,
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "source": "sec-edgar",
                })
    except Exception as e:
        log.warning(f"SEC EDGAR S-1 fetch failed: {e}")

    return filings


def score_ipo_with_claude(ipo: dict) -> dict:
    """
    Use Claude to analyse an IPO and predict first-day pop potential.
    Returns the IPO dict with added score and analysis fields.
    """
    if not config.CLAUDE_API_KEY:
        log.warning("CLAUDE_API_KEY not set — skipping IPO analysis")
        return {**ipo, "score": 50, "analysis": "Claude API not configured."}

    client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)

    try:
        msg = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=400,
            messages=[{"role": "user", "content": f"""
Analyse this IPO for first-day pop potential:

TITLE: {ipo['title']}
DETAILS: {ipo['summary']}

Answer in this exact format:
SCORE: [0-100, where 100 = almost certain first-day pop]
PREDICTED RETURN: [e.g. +15% to +35% on day 1]
WHY BULLISH: [one sentence — biggest reason this could pop]
WHY BEARISH: [one sentence — biggest risk]
SECTOR: [tech/biotech/fintech/defense/energy/other]
TIMING: [when to buy: at open / wait for dip / skip]
"""}],
        )
        raw = msg.content[0].text

        # Parse score
        score = 50
        for line in raw.splitlines():
            if line.startswith("SCORE:"):
                try:
                    score = int(line.split(":")[1].strip().split()[0])
                except (ValueError, IndexError):
                    pass
                break

        return {**ipo, "score": score, "analysis": raw}

    except Exception as e:
        log.error(f"Claude IPO analysis failed: {e}")
        return {**ipo, "score": 50, "analysis": "Analysis failed."}


def format_ipo_alert(ipo: dict) -> str:
    """Format IPO analysis into a Telegram message."""
    score = ipo.get("score", 0)
    stars = "⭐" * min(score // 20, 5)

    return (
        f"🚀 IPO ALERT {stars}\n"
        f"Score: {score}/100\n\n"
        f"📋 {ipo['title']}\n\n"
        f"ANALYSIS:\n{ipo.get('analysis', 'No analysis')}\n\n"
        f"{ipo.get('link', '')}"
    )


def check_ipos(send_fn=None, score_threshold: int = 65) -> list[dict]:
    """
    Main entry point: fetch IPOs, score them, alert on strong ones.

    Args:
        send_fn: function to send alert (e.g. send_telegram from bot.py)
        score_threshold: minimum score to trigger alert

    Returns:
        List of high-scoring IPO dicts
    """
    log.info("Running IPO tracker...")

    # Fetch from all sources
    ipo_news = fetch_ipo_news()
    sec_filings = fetch_sec_s1_filings()
    all_ipos = ipo_news + sec_filings

    if not all_ipos:
        log.info("No new IPOs found.")
        return []

    log.info(f"Found {len(all_ipos)} new IPO items. Analysing with Claude...")

    high_score_ipos = []
    seen = load_ipo_cache()

    for ipo in all_ipos:
        scored = score_ipo_with_claude(ipo)
        seen.add(ipo["id"])

        if scored["score"] >= score_threshold:
            high_score_ipos.append(scored)
            if send_fn:
                alert = format_ipo_alert(scored)
                send_fn(alert)
                log.info(f"IPO alert sent: {ipo['title']} (score: {scored['score']})")

    save_ipo_cache(seen)
    log.info(f"IPO tracker complete. {len(high_score_ipos)} high-score IPOs found.")
    return high_score_ipos


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    if args.test:
        print("IPO Tracker test — fetching NASDAQ IPO RSS...")
        ipos = fetch_ipo_news()
        print(f"Found {len(ipos)} IPO news items")
        for ipo in ipos[:3]:
            print(f"  - {ipo['title']}")
    else:
        results = check_ipos()
        for ipo in results:
            print(format_ipo_alert(ipo))
