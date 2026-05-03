"""
Batch Processor — Phase 3

Queues low-priority articles (Tier 3 sources like ZeroHedge) for overnight
Claude Batch API processing at 90% cost reduction vs real-time API calls.

Flow:
  hourly news run  → add_to_batch_queue(article)   # queues to data/batch_pending.json
  midnight cron    → submit_batch()                 # sends to Batch API, saves batch_id
  2am cron         → retrieve_batch_results()       # polls + processes overnight signals
  morning briefing → batch signals already in tracker, appear in summary

Usage:
    python batch_processor.py --submit    # Submit queued articles to Batch API
    python batch_processor.py --retrieve  # Retrieve and process batch results
"""

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

import anthropic

import config
from tracker import record_alert

log = logging.getLogger(__name__)

_BATCH_PROMPT = """Article: {title}
Details: {summary}

You are a strict investment analyst. Does this article represent a genuine
trading opportunity for a retail investor right now?

Answer in exactly this format:
SIGNAL: YES / NO
CONFIDENCE: HIGH / MEDIUM / LOW
TICKERS: [comma-separated ticker symbols, or NONE]
REASON: [one sentence — the specific opportunity or why it's not worth acting on]"""


def add_to_batch_queue(article: dict) -> None:
    """
    Queue an article for overnight batch processing.
    Called during hourly news runs for Tier 3 source articles.
    """
    queue_file = Path(config.BATCH_PENDING_FILE)
    queue_file.parent.mkdir(parents=True, exist_ok=True)

    queue: list[dict] = []
    if queue_file.exists():
        try:
            with open(queue_file) as f:
                queue = json.load(f)
        except (json.JSONDecodeError, OSError):
            queue = []

    existing_ids = {a.get("id") for a in queue}
    if article.get("id") not in existing_ids:
        queue.append({
            "id": article["id"],
            "title": article["title"],
            "summary": article.get("summary", ""),
            "link": article.get("link", ""),
            "queued_at": datetime.now().isoformat(),
        })
        with open(queue_file, "w") as f:
            json.dump(queue, f, indent=2)
        log.debug(f"Queued for batch: {article['title'][:60]}")


def submit_batch(send_fn=None) -> str | None:
    """
    Submit all queued articles to the Anthropic Batch API.
    Saves the batch_id to data/batch_state.json. Clears the queue.
    Returns batch_id or None if queue was empty.
    """
    queue_file = Path(config.BATCH_PENDING_FILE)
    state_file = Path(config.BATCH_STATE_FILE)

    if not queue_file.exists():
        log.info("Batch queue file not found — nothing to submit.")
        return None

    try:
        with open(queue_file) as f:
            articles = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.error(f"Failed to read batch queue: {e}")
        return None

    if not articles:
        log.info("Batch queue is empty — nothing to submit.")
        return None

    if not config.CLAUDE_API_KEY:
        log.warning("CLAUDE_API_KEY not set — cannot submit batch.")
        return None

    client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)

    requests_list = [
        {
            "custom_id": a["id"],
            "params": {
                "model": config.CLAUDE_MODEL,
                "max_tokens": 150,
                "messages": [{
                    "role": "user",
                    "content": _BATCH_PROMPT.format(
                        title=a["title"],
                        summary=a.get("summary", "")[:500],
                    ),
                }],
            },
        }
        for a in articles
    ]

    try:
        batch = client.messages.batches.create(requests=requests_list)
    except Exception as e:
        log.error(f"Batch API submission failed: {e}")
        return None

    state = {
        "batch_id": batch.id,
        "submitted_at": datetime.now().isoformat(),
        "article_count": len(articles),
        "articles": articles,  # Keep for context when processing results
    }
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)

    # Clear the queue
    with open(queue_file, "w") as f:
        json.dump([], f)

    log.info(f"Batch submitted: {batch.id} ({len(articles)} articles)")

    if send_fn:
        send_fn(
            f"📦 Batch API\n"
            f"{len(articles)} articles queued for overnight processing.\n"
            f"Batch ID: {batch.id}\n"
            f"Results available in ~1 hour."
        )

    return batch.id


def retrieve_batch_results(send_fn=None) -> list[dict]:
    """
    Poll the Batch API for results. If processing is done, parse signals
    and send any genuine investment opportunities to Telegram.
    Returns list of signal dicts found.
    """
    state_file = Path(config.BATCH_STATE_FILE)

    if not state_file.exists():
        log.info("No pending batch state file — nothing to retrieve.")
        return []

    try:
        with open(state_file) as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.error(f"Failed to read batch state: {e}")
        return []

    batch_id = state.get("batch_id")
    if not batch_id:
        log.info("No batch_id in state file.")
        return []

    if not config.CLAUDE_API_KEY:
        log.warning("CLAUDE_API_KEY not set — cannot retrieve batch.")
        return []

    client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)

    try:
        batch = client.messages.batches.retrieve(batch_id)
    except Exception as e:
        log.error(f"Batch retrieve failed: {e}")
        return []

    if batch.processing_status != "ended":
        log.info(f"Batch {batch_id} still processing (status: {batch.processing_status}). Try again later.")
        return []

    log.info(f"Batch {batch_id} complete. Parsing results...")

    # Build a lookup: custom_id → article metadata
    article_lookup = {a["id"]: a for a in state.get("articles", [])}

    signals: list[dict] = []

    try:
        for result in client.messages.batches.results(batch_id):
            if result.result.type != "succeeded":
                continue

            text = result.result.message.content[0].text
            article = article_lookup.get(result.custom_id, {})

            # Parse response
            signal_val = ""
            confidence = "medium"
            tickers: list[str] = []
            reason = ""

            for line in text.splitlines():
                line = line.strip()
                if line.startswith("SIGNAL:"):
                    signal_val = line.split(":", 1)[1].strip().upper()
                elif line.startswith("CONFIDENCE:"):
                    confidence = line.split(":", 1)[1].strip().lower()
                elif line.startswith("TICKERS:"):
                    raw = line.split(":", 1)[1].strip()
                    tickers = [
                        t.strip().upper()
                        for t in raw.split(",")
                        if t.strip() and t.strip().upper() != "NONE"
                    ]
                elif line.startswith("REASON:"):
                    reason = line.split(":", 1)[1].strip()

            if signal_val != "YES" or not tickers:
                continue

            signal = {
                "tickers": tickers,
                "reason": reason,
                "confidence": confidence,
                "headline": article.get("title", reason),
                "link": article.get("link", ""),
            }
            signals.append(signal)

            record_alert(
                alert_type="batch_opportunity",
                headline=article.get("title", reason),
                analysis=text,
                tickers=tickers,
                confidence=confidence,
            )

            if send_fn:
                send_fn(
                    f"📦 OVERNIGHT BATCH SIGNAL\n"
                    f"TICKERS: {', '.join(tickers)}\n"
                    f"CONFIDENCE: {confidence.upper()}\n\n"
                    f"{reason}\n\n"
                    f"{article.get('link', '')}"
                )
                log.info(f"Batch signal sent: {tickers}")

    except Exception as e:
        log.error(f"Error processing batch results: {e}")

    # Clear state file — batch is done
    try:
        state_file.unlink()
    except OSError:
        pass

    log.info(f"Batch processing complete. {len(signals)} signals found from {state.get('article_count', '?')} articles.")
    return signals


def get_queue_size() -> int:
    """Return number of articles currently in the batch queue."""
    queue_file = Path(config.BATCH_PENDING_FILE)
    if not queue_file.exists():
        return 0
    try:
        with open(queue_file) as f:
            return len(json.load(f))
    except (json.JSONDecodeError, OSError):
        return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="Batch Processor — Anthropic Batch API")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--submit", action="store_true", help="Submit queued articles to Batch API")
    group.add_argument("--retrieve", action="store_true", help="Retrieve and process batch results")
    group.add_argument("--status", action="store_true", help="Show queue size and pending batch status")
    args = parser.parse_args()

    if args.status:
        size = get_queue_size()
        print(f"Batch queue: {size} articles pending")
        state_file = Path(config.BATCH_STATE_FILE)
        if state_file.exists():
            with open(state_file) as f:
                state = json.load(f)
            print(f"Pending batch: {state.get('batch_id')} (submitted {state.get('submitted_at')})")
        else:
            print("No batch currently submitted.")

    elif args.submit:
        from bot import send_telegram
        batch_id = submit_batch(send_fn=send_telegram)
        if batch_id:
            print(f"Batch submitted: {batch_id}")
        else:
            print("Nothing to submit.")

    elif args.retrieve:
        from bot import send_telegram
        signals = retrieve_batch_results(send_fn=send_telegram)
        print(f"\nFound {len(signals)} signals:")
        for s in signals:
            print(f"  {', '.join(s['tickers'])} — {s['reason'][:80]}")
