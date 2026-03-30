"""
Investment Bot Configuration
Edit this file to customise your portfolio, feeds, and keywords.
"""

import os

# Try to load .env file if it exists (for local development)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# --- API Keys ---
# These are loaded from environment variables.
# On GitHub Actions: set as repository secrets.
# Locally: put in a .env file (never commit that file).
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# --- Your Portfolio ---
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
]

# --- Keywords That Trigger Analysis ---
TRIGGER_KEYWORDS = [
    # Energy & commodities
    "oil", "gas", "gold", "silver", "copper", "lithium", "coal",
    "OPEC", "energy crisis", "pipeline", "Strait of Hormuz",
    "commodity", "crude", "LNG", "uranium",
    # Geopolitical
    "Middle East", "Israel", "Iran", "Ukraine", "Russia", "China",
    "Taiwan", "North Korea", "conflict", "war", "sanctions",
    "ceasefire", "invasion", "military", "NATO", "nuclear",
    # Macro & economy
    "interest rate", "Federal Reserve", "Fed", "rate cut", "rate hike",
    "inflation", "recession", "GDP", "unemployment", "debt ceiling",
    "economic crisis", "bank collapse", "currency crisis", "IMF",
    "dollar", "central bank",
    # Markets & deals
    "IPO", "goes public", "merger", "acquisition", "takeover",
    "billion deal", "buyout", "bankruptcy", "short squeeze",
    "market crash", "stock surge",
    # Tech & AI
    "SpaceX", "Elon Musk", "Nvidia", "semiconductor", "AI boom",
    "artificial intelligence", "chip shortage", "data centre",
    "quantum computing", "Apple", "Microsoft", "Google", "Meta",
    "OpenAI", "robotics", "cybersecurity breach",
    # EV & green energy
    "BYD", "Tesla", "electric vehicle", "battery", "solar",
    "wind energy", "hydrogen", "green energy", "climate deal",
    # Defense & aerospace
    "defense spending", "Rheinmetall", "Lockheed", "arms",
    "military contract", "drone", "space race",
    # Crypto & finance
    "bitcoin", "crypto", "ethereum", "blockchain", "stablecoin",
    "crypto regulation", "SEC", "ETF approval",
    # Pharma & biotech
    "drug approval", "FDA", "cancer", "vaccine", "biotech",
    "clinical trial", "pandemic", "outbreak",
    # Commodities & supply chain
    "wheat", "food crisis", "drought", "supply chain",
    "shipping", "port strike",
    # Existing holdings
    "Shell", "Barrick",
]

# --- Bot Behaviour ---
CHECK_INTERVAL_MINUTES = 30
MAX_ITEMS_PER_FEED = 10
MIN_URGENCY = "low"
CLAUDE_MODEL = "claude-sonnet-4-6"
MAX_RESPONSE_TOKENS = 500
