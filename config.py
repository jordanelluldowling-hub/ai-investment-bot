"""
Investment Bot Configuration
Edit this file to customise your portfolio, feeds, and keywords.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# --- API Keys (loaded from .env file) ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")

# --- Your Portfolio ---
# Edit this to reflect your actual holdings and entry prices
PORTFOLIO = """
My current investment portfolio:
- Shell (SHEL) - Oil/Energy stock
- Barrick Gold (GOLD) - Gold mining stock
- Rheinmetall (RHM) - Defense/Aerospace stock
- Bitcoin (BTC) - Cryptocurrency
- BYD (BYDDY) - Electric vehicles stock
- S&P 500 ETF (e.g. VUSA or similar) - Broad market exposure
"""

# --- RSS News Feeds To Monitor ---
RSS_FEEDS = [
    "https://feeds.reuters.com/reuters/businessNews",
    "https://feeds.bbci.co.uk/news/business/rss.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://oilprice.com/rss/main",
    "https://feeds.feedburner.com/zerohedge/feed",
]

# --- Keywords That Trigger Analysis ---
# Any news headline containing one of these will be sent to Claude for analysis
TRIGGER_KEYWORDS = [
    "oil",
    "gold",
    "Middle East",
    "OPEC",
    "Israel",
    "Iran",
    "Ukraine",
    "Russia",
    "defense spending",
    "NATO",
    "BYD",
    "electric vehicle",
    "bitcoin",
    "crypto",
    "interest rate",
    "Federal Reserve",
    "Fed",
    "inflation",
    "recession",
    "conflict",
    "war",
    "sanctions",
    "Shell",
    "Rheinmetall",
    "Barrick",
    "Strait of Hormuz",
]

# --- Bot Behaviour ---
# How often to check for news (in minutes)
CHECK_INTERVAL_MINUTES = 30

# Max news items to check per feed per run (keeps API costs low)
MAX_ITEMS_PER_FEED = 10

# Minimum urgency level to send alert ("low", "medium", "high")
# Set to "low" to receive all alerts, "high" for only critical ones
MIN_URGENCY = "low"

# Claude model to use
CLAUDE_MODEL = "claude-sonnet-4-6"

# Max tokens in Claude's response (keeps cost low, ~500 = ~$0.001 per analysis)
MAX_RESPONSE_TOKENS = 500
