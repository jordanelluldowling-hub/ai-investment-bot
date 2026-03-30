import os

CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

PORTFOLIO = """
My current investment portfolio:
- Shell (SHEL) - Oil/Energy stock
- Barrick Gold (GOLD) - Gold mining stock
- Rheinmetall (RHM) - Defense/Aerospace stock
- Bitcoin (BTC) - Cryptocurrency
- BYD (BYDDY) - Electric vehicles stock
- S&P 500 ETF - Broad market exposure
"""

RSS_FEEDS = [
    "https://feeds.reuters.com/reuters/businessNews",
    "https://feeds.bbci.co.uk/news/business/rss.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://oilprice.com/rss/main",
]

TRIGGER_KEYWORDS = [
    "oil", "gas", "gold", "silver", "copper", "lithium", "coal",
    "OPEC", "energy crisis", "pipeline", "Strait of Hormuz",
    "commodity", "crude", "LNG", "uranium",
    "Middle East", "Israel", "Iran", "Ukraine", "Russia", "China",
    "Taiwan", "North Korea", "conflict", "war", "sanctions",
    "ceasefire", "invasion", "military", "NATO", "nuclear",
    "interest rate", "Federal Reserve", "Fed", "rate cut", "rate hike",
    "inflation", "recession", "GDP", "unemployment", "debt ceiling",
    "economic crisis", "bank collapse", "currency crisis", "IMF",
    "dollar", "central bank",
    "IPO", "goes public", "merger", "acquisition", "takeover",
    "billion deal", "buyout", "bankruptcy", "short squeeze",
    "market crash", "stock surge",
    "SpaceX", "Elon Musk", "Nvidia", "semiconductor", "AI boom",
    "artificial intelligence", "chip shortage", "data centre",
    "quantum computing", "Apple", "Microsoft", "Google", "Meta",
    "OpenAI", "robotics", "cybersecurity",
    "BYD", "Tesla", "electric vehicle", "battery", "solar",
    "wind energy", "hydrogen", "green energy", "climate deal",
    "defense spending", "Rheinmetall", "Lockheed", "arms",
    "military contract", "drone", "space race",
    "bitcoin", "crypto", "ethereum", "blockchain", "stablecoin",
    "crypto regulation", "SEC", "ETF approval",
    "drug approval", "FDA", "cancer", "vaccine", "biotech",
    "clinical trial", "pandemic", "outbreak",
    "wheat", "food crisis", "drought", "supply chain",
    "shipping", "port strike",
    "Shell", "Barrick",
]

CHECK_INTERVAL_MINUTES = 30
MAX_ITEMS_PER_FEED = 10
MIN_URGENCY = "low"
CLAUDE_MODEL = "claude-sonnet-4-6"
MAX_RESPONSE_TOKENS = 500
