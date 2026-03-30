# AI Investment Bot

Monitors RSS news feeds 24/7, analyses headlines with Claude AI, and sends investment alerts to your Telegram.

```
News breaks → Bot detects it → Claude analyses impact → Alert sent to Telegram → You decide what to do
```

## Features

- Monitors Reuters, BBC Business, Oil Price and more
- Keyword filtering — only relevant headlines trigger analysis
- Claude AI gives you specific buy/sell/hold advice for your portfolio
- Duplicate detection — never see the same article twice
- On-demand portfolio review tool (morning briefing, weekly review, stock deep-dive)
- Urgency levels — filter alerts by HIGH / MEDIUM / LOW

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set up your API keys

```bash
cp .env.example .env
```

Edit `.env` and add:

| Key | Where to get it | Cost |
|---|---|---|
| `CLAUDE_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | ~$0.001 per analysis |
| `TELEGRAM_TOKEN` | Message `@BotFather` on Telegram, type `/newbot` | Free |
| `TELEGRAM_CHAT_ID` | Message `@userinfobot` on Telegram | Free |

### 3. Customise your portfolio

Edit `config.py` — update `PORTFOLIO` with your actual holdings.

### 4. Test it works

```bash
python bot.py --test
```

You should receive a message in your Telegram.

### 5. Run the bot

```bash
# Run continuously (checks every 30 minutes)
python bot.py

# Run one check and exit
python bot.py --once
```

---

## On-Demand Portfolio Analysis

Use `portfolio_review.py` to ask Claude about your portfolio any time:

```bash
# Morning briefing — what to watch today
python portfolio_review.py morning

# Weekly review
python portfolio_review.py weekly

# Monthly strategy + where to put your €500
python portfolio_review.py monthly

# Macro economic summary (rates, dollar, inflation)
python portfolio_review.py macro

# Analyse a specific headline
python portfolio_review.py news "Iran closes Strait of Hormuz"

# Deep dive on a stock
python portfolio_review.py stock "Rheinmetall"
```

---

## Running 24/7 for Free (No Server Needed)

### Option A — Replit (Easiest)
1. Go to [replit.com](https://replit.com) and create a free account
2. Create a new Python project
3. Upload all files from this repo
4. Add your API keys in Replit's "Secrets" tab (not in the code)
5. Click Run — it stays on 24/7

### Option B — GitHub Actions (Free, no signup needed)
Run the bot on a schedule using GitHub's free CI runners. Create `.github/workflows/news-check.yml`:

```yaml
name: News Check
on:
  schedule:
    - cron: '*/30 * * * *'  # Every 30 minutes
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python bot.py --once
        env:
          CLAUDE_API_KEY: ${{ secrets.CLAUDE_API_KEY }}
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
```

Add your keys in GitHub → Settings → Secrets.

---

## No Coding Yet? Start Here

See [alerts/google-alerts-setup.md](alerts/google-alerts-setup.md) for a zero-code setup using Google Alerts + Claude manually. Takes 10 minutes.

---

## Project Structure

```
ai-investment-bot/
├── bot.py                  # Main bot — monitors feeds, sends alerts
├── portfolio_review.py     # On-demand analysis tool
├── config.py               # Your portfolio, feeds, keywords
├── requirements.txt        # Python dependencies
├── .env.example            # API key template (copy to .env)
└── alerts/
    └── google-alerts-setup.md   # Manual (no-code) setup guide
```

## Estimated Costs

| Usage | Cost |
|---|---|
| 10 analyses per day | ~$0.01/day |
| 50 analyses per day | ~$0.05/day |
| Monthly (active) | ~$1–3/month |

Claude API pricing: [anthropic.com/pricing](https://www.anthropic.com/pricing)
