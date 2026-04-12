"""
Moonshot Detector — Phase 3

Uses Claude extended thinking (claude-opus-4-6) to deeply analyze small/mid cap
stocks showing unusual social momentum for 5-50x return potential.

How it works:
  1. Pulls top Reddit + StockTwits momentum tickers not in your portfolio
  2. Feeds the top 5 candidates to claude-opus-4-6 with extended thinking enabled
  3. Claude uses its full reasoning capability to evaluate 5-50x potential
  4. Only fires an alert if MOONSHOT SCORE >= 65/100

Run: weekly Sunday 6pm UTC via GitHub Actions

Usage:
    python moonshot_detector.py          # Scan and print results
    python moonshot_detector.py --send   # Scan and send alerts to Telegram
"""

import argparse
import logging
from datetime import datetime

import anthropic

import config
from sentiment_tracker import fetch_reddit_mentions, fetch_stocktwits_trending
from tracker import record_alert

log = logging.getLogger(__name__)

MOONSHOT_SCORE_THRESHOLD = 65

_MOONSHOT_PROMPT = """I need a thorough analysis of a stock showing unusual social momentum.

TICKER: {ticker}
REDDIT MENTIONS: {reddit_count} (recent scan across r/wallstreetbets, r/stocks, r/investing)
ON STOCKTWITS TRENDING: {on_stocktwits}

MY EXISTING PORTFOLIO (do NOT recommend these — I already own them):
{portfolio_tickers}

Using your full reasoning, evaluate whether {ticker} could be a genuine 5-50x
return opportunity over the next 1-3 years.

Think through:
1. What does this company actually do? Core product/service and competitive moat?
2. Is this social momentum organic (real institutional + retail interest) or manufactured (pump)?
3. What specific catalysts could drive explosive growth in the next 12-24 months?
4. What is the realistic total addressable market?
5. Key risks: what would prevent this from playing out?
6. What's the most likely failure scenario?
7. What single event would need to happen to make this a 10x?

Answer in exactly this format:
COMPANY: [full name — one sentence on what they do]
MOONSHOT SCORE: [0-100, where 80+ = exceptional, 65-79 = strong, below 65 = not worth acting on]
BULL CASE: [2 sentences — specific, realistic path to 5-50x]
BEAR CASE: [1 sentence — most likely failure scenario]
CATALYST: [the single most important upcoming event or trigger to watch]
UPSIDE: [realistic return range, e.g. 3-10x over 2 years]
TIME HORIZON: [months / 1-2 years / 2-3 years]
VERDICT: [BUY SMALL POSITION / ADD TO WATCHLIST / AVOID]"""


def run_moonshot_scan(send_fn=None) -> list[dict]:
    """
    Scan top Reddit/StockTwits momentum stocks not in portfolio.
    Uses claude-opus-4-6 with extended thinking for deep analysis.
    Only alerts on stocks scoring >= MOONSHOT_SCORE_THRESHOLD.

    Args:
        send_fn: function to send Telegram messages

    Returns:
        List of high-score moonshot dicts
    """
    log.info("Running moonshot scan with extended thinking...")

    # Fetch social momentum data
    reddit_counts = fetch_reddit_mentions()
    stocktwits_trending = fetch_stocktwits_trending()
    st_ticker_set = {t["ticker"] for t in stocktwits_trending}

    # Filter to non-portfolio tickers only, ranked by Reddit mentions
    portfolio_set = set(config.YOUR_TICKERS)
    candidates = [
        (ticker, count)
        for ticker, count in reddit_counts.most_common(30)
        if ticker not in portfolio_set and len(ticker) >= 3
    ][:5]  # Analyse top 5 candidates

    # Also include StockTwits trending tickers not in portfolio or already in candidates
    candidate_tickers = {t for t, _ in candidates}
    for item in stocktwits_trending[:10]:
        t = item["ticker"]
        if t not in portfolio_set and t not in candidate_tickers and len(t) >= 3:
            candidates.append((t, reddit_counts.get(t, 0)))
            candidate_tickers.add(t)
            if len(candidates) >= 7:
                break

    if not candidates:
        log.info("No moonshot candidates found — no social momentum outside portfolio.")
        return []

    log.info(f"Analysing {len(candidates)} moonshot candidates: {[t for t, _ in candidates]}")

    if not config.CLAUDE_API_KEY:
        log.warning("CLAUDE_API_KEY not set — skipping moonshot analysis.")
        return []

    client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)
    results: list[dict] = []

    for ticker, reddit_count in candidates:
        log.info(f"Extended thinking analysis: {ticker} ({reddit_count} Reddit mentions)")

        try:
            response = client.messages.create(
                model=config.CLAUDE_DEEP_MODEL,
                max_tokens=config.MAX_MOONSHOT_TOKENS,
                thinking={
                    "type": "enabled",
                    "budget_tokens": config.MOONSHOT_THINKING_BUDGET,
                },
                messages=[{
                    "role": "user",
                    "content": _MOONSHOT_PROMPT.format(
                        ticker=ticker,
                        reddit_count=reddit_count,
                        on_stocktwits="YES" if ticker in st_ticker_set else "NO",
                        portfolio_tickers=", ".join(config.YOUR_TICKERS),
                    ),
                }],
            )

            # Extract the text response block (skip thinking blocks)
            text = ""
            for block in response.content:
                if block.type == "text":
                    text = block.text
                    break

            if not text:
                log.warning(f"No text response for {ticker}")
                continue

            # Parse score
            score = 50
            for line in text.splitlines():
                if line.strip().startswith("MOONSHOT SCORE:"):
                    try:
                        raw = line.split(":", 1)[1].strip().split()[0]
                        score = int(raw.rstrip("/"))
                    except (ValueError, IndexError):
                        pass
                    break

            log.info(f"{ticker}: moonshot score {score}/100")

            if score < MOONSHOT_SCORE_THRESHOLD:
                log.info(f"{ticker} below threshold ({score} < {MOONSHOT_SCORE_THRESHOLD}) — skipped")
                continue

            result = {
                "ticker": ticker,
                "score": score,
                "reddit_count": reddit_count,
                "on_stocktwits": ticker in st_ticker_set,
                "analysis": text,
            }
            results.append(result)

            record_alert(
                alert_type="moonshot",
                headline=f"{ticker} — moonshot analysis (score {score}/100)",
                analysis=text,
                tickers=[ticker],
                score=score // 10,
                confidence="high" if score >= 80 else "medium",
            )

            if send_fn:
                timestamp = datetime.now().strftime("%d %b %Y")
                stars = "⭐" * min(score // 20, 5)
                alert = (
                    f"🌙 MOONSHOT ALERT {stars}\n"
                    f"Score: {score}/100 | {timestamp}\n\n"
                    f"TICKER: {ticker}\n"
                    f"Reddit mentions: {reddit_count} | StockTwits: {'YES' if ticker in st_ticker_set else 'NO'}\n\n"
                    f"{text}\n\n"
                    f"NOTE: Extended thinking analysis via Claude Opus.\n"
                    f"Always research thoroughly before investing."
                )
                send_fn(alert)
                log.info(f"Moonshot alert sent: {ticker} (score {score}/100)")

        except Exception as e:
            log.error(f"Moonshot analysis failed for {ticker}: {e}")
            continue

    log.info(f"Moonshot scan complete. {len(results)} candidates scored >= {MOONSHOT_SCORE_THRESHOLD}.")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="Moonshot Detector — extended thinking analysis")
    parser.add_argument("--send", action="store_true", help="Send alerts to Telegram")
    args = parser.parse_args()

    from bot import send_telegram
    send_fn = send_telegram if args.send else None

    results = run_moonshot_scan(send_fn=send_fn)

    print(f"\nMoonshot scan complete. {len(results)} high-score candidates:\n")
    for r in results:
        print(f"  {r['ticker']} — Score: {r['score']}/100 | Reddit: {r['reddit_count']}")
        # Print first 3 lines of analysis
        for line in r["analysis"].splitlines()[:4]:
            if line.strip():
                print(f"    {line}")
        print()
