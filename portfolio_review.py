"""
Portfolio Review Tool
Ask Claude to analyse your portfolio on demand using preset prompts.

Usage:
    python portfolio_review.py morning     # Morning market briefing
    python portfolio_review.py weekly      # Weekly portfolio review
    python portfolio_review.py monthly     # Monthly strategy session
    python portfolio_review.py macro       # Macro economic summary
    python portfolio_review.py news "HEADLINE TEXT"   # Analyse a specific headline
    python portfolio_review.py stock "COMPANY NAME"   # Deep dive on a stock
"""

import sys
import anthropic
import config


def ask_claude(prompt: str) -> str:
    client = anthropic.Anthropic(api_key=config.CLAUDE_API_KEY)
    message = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


PROMPTS = {
    "morning": f"""
Give me a concise morning briefing covering:
1. What are the 3 biggest market-moving events to watch today?
2. How might each affect these specific holdings: {config.PORTFOLIO}
3. Any action I should consider today?
4. One sentence on overall market mood (risk-on or risk-off?).

Keep it under 10 bullet points total. Be direct.
""",

    "weekly": f"""
Give me a weekly portfolio review framework covering:
1. What worked this week and why (for a portfolio like: {config.PORTFOLIO})
2. What risks emerged this week I should monitor?
3. What should I watch next week?
4. Any positions I should reconsider?

Be direct and specific to the holdings listed.
""",

    "monthly": f"""
It's the start of a new month. Here is my portfolio:
{config.PORTFOLIO}

I have €500 to invest this month.

Based on current general market conditions:
1. What is the current macro environment (rates, inflation, geopolitics)?
2. Which of my existing holdings should I add to this month and why?
3. Should I open any new position? If so, what and why?
4. What is the biggest risk to my portfolio right now?
5. Give me a specific €500 allocation recommendation with reasoning.
""",

    "macro": """
Give me a macro economic summary covering:
1. What is the Federal Reserve doing with interest rates and why it matters?
2. Is the US dollar strengthening or weakening? What does that mean for commodities and crypto?
3. What is inflation doing globally?
4. Are we heading toward recession or growth? Key signals.
5. How should a portfolio with oil, gold, defense, crypto, and EV exposure be positioned right now?

Use plain English. No jargon.
""",
}


def analyse_news(headline: str) -> str:
    return f"""
This news just broke: {headline}

My Portfolio:
{config.PORTFOLIO}

Tell me:
1. IMMEDIATE IMPACT (next 24 hours) on my specific holdings
2. MEDIUM TERM IMPACT (1-3 months)
3. ACTION: Should I do anything right now? What specifically?
4. COUNTER ARGUMENT: What could make this news have the opposite effect to what you expect?
5. CONFIDENCE: How confident are you in this analysis? (low/medium/high) and why.

Be direct. No preamble.
"""


def analyse_stock(company: str) -> str:
    return f"""
Analyse {company} for me covering:
1. What they actually do (in 2 sentences, plain English)
2. Top 3 reasons the stock could go up
3. Top 3 reasons the stock could go down
4. What the current investor sentiment seems to be
5. How does it fit (or not) alongside this portfolio: {config.PORTFOLIO}
6. What price move or event would change your view on it?

Be specific and direct.
"""


def main():
    if not config.CLAUDE_API_KEY:
        print("Error: CLAUDE_API_KEY not set. Copy .env.example to .env and add your key.")
        sys.exit(1)

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    mode = sys.argv[1].lower()

    if mode in PROMPTS:
        prompt = PROMPTS[mode]
    elif mode == "news" and len(sys.argv) >= 3:
        prompt = analyse_news(" ".join(sys.argv[2:]))
    elif mode == "stock" and len(sys.argv) >= 3:
        prompt = analyse_stock(" ".join(sys.argv[2:]))
    else:
        print(__doc__)
        sys.exit(1)

    print(f"\nAsking Claude ({config.CLAUDE_MODEL})...\n")
    print("=" * 60)
    result = ask_claude(prompt)
    print(result)
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
