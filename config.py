"""
Investment Bot Configuration — v2
All secrets come from environment variables (set as GitHub Secrets or in .env locally).
Edit PORTFOLIO, RSS_FEEDS, and TRIGGER_KEYWORDS to customise your setup.
"""

import os

# --- API Keys (from environment variables — set in GitHub Secrets) ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")

# --- Your Full 16-Stock Portfolio ---
PORTFOLIO = """
My current investment portfolio (16 holdings):

TIER 1 — Core (highest conviction):
- NVIDIA (NVDA) — AI chips, dominates GPU market
- Bitcoin (BTC) — Crypto reserve asset
- Rheinmetall (RHM) — European defense, massive NATO spend coming

TIER 2 — Growth (strong upside):
- Palantir (PLTR) — AI data platform, government + enterprise
- IonQ (IONQ) — Quantum computing, early mover advantage
- Axon Enterprise (AXON) — Law enforcement tech, body cameras, Taser
- Cellebrite (CLBT) — Mobile forensics, digital intelligence platforms

TIER 3 — Speculative (high risk, high reward):
- Oddity Tech (ODD) — Beauty tech, AI-powered D2C brand
- CoreWeave (CRWV) — GPU cloud computing, NVIDIA-backed
- Rigetti Computing (RGTI) — Quantum hardware, superconducting qubits
- BYD (BYDDY) — Chinese EV giant, overtaking Tesla in China
- Ondas Holdings (ONDS) — Drone tech, railroad + defense applications

CRYPTO TIER:
- Ethereum (ETH) — Smart contracts platform, DeFi backbone
- Solana (SOL) — Fast L1, NFT + DeFi ecosystem

DEFENSIVE:
- S&P 500 ETF (VUSA) — Broad market, core holding
- Barrick Gold (GOLD) — Gold mining, inflation hedge
"""

# --- Congressional Trading RSS Feeds ---
CONGRESS_RSS_FEEDS = [
    "https://housestockwatcher.com/rss_feed",
    "https://senatestockwatcher.com/rss_feed",
]

# --- Congressional Data API Endpoints ---
HOUSE_TRADES_URL = "https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json"
SENATE_TRADES_URL = "https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json"

# --- Politicians to Watch (40+ including spouses & family) ---
WATCH_POLITICIANS = [
    # High-signal traders (historically well-timed trades)
    "pelosi", "nancy pelosi", "paul pelosi",
    "tuberville", "tommy tuberville",
    "crenshaw", "dan crenshaw",
    "loeffler", "kelly loeffler",
    "ossoff", "jon ossoff",
    "warnock", "raphael warnock",
    "kelly", "mark kelly",
    "manchin", "joe manchin",
    "mccaul", "michael mccaul",
    "gottheimer", "josh gottheimer",
    "suozzi", "thomas suozzi",
    "slotkin", "elissa slotkin",
    "spanberger", "abigail spanberger",
    "warren", "elizabeth warren",
    "hawley", "josh hawley",
    "paul", "rand paul",
    "kennedy", "john kennedy",
    "scott", "rick scott",
    "burr", "richard burr",
    "perdue", "david perdue",
    "collins", "susan collins",
    "capito", "shelley capito",
    "mcconnell", "mitch mcconnell",
    "gaetz", "matt gaetz",
    "green", "marjorie taylor greene",
    "boebert", "lauren boebert",
    "schiff", "adam schiff",
    "meeks", "gregory meeks",
    "lieu", "ted lieu",
    # Spouses & family members (strong signal — less scrutiny, more freedom)
    "elaine chao",        # McConnell wife — former Transport Secretary, logistics sector
    "richard blum",       # Feinstein husband — real estate & private equity (CB Richard Ellis)
    "jared kushner",      # Trump son-in-law — Middle East sovereign fund, fintech
    "alisha kramer",      # Ossoff wife — pharma/healthcare focus
    "kelley paul",        # Rand Paul wife — biotech investor
    "hunter biden",       # Biden family — energy sector connections
    "jeff sprecher",      # Kelly Loeffler husband — NYSE founder (ICE)
    # Catch-all ownership types (catches any congress member)
    "spouse", "dependent", "joint",
]

# --- Congress Trade Score Threshold ---
# Only alert on trades scoring >= 7 out of 10
CONGRESS_SCORE_THRESHOLD = 7

# --- News Source Quality Tiers ---
# Tier 1 = most reliable, fact-checked institutional sources
# Tier 2 = good but sometimes opinion/community driven
# Tier 3 = useful for early signals but higher noise ratio
#
# Effect on alerts:
#   Tier 1 article + MEDIUM confidence → sends portfolio alert
#   Tier 2 article + HIGH confidence only → sends portfolio alert
#   Tier 3 article → goes to batch queue for overnight review (not immediate)
SOURCE_QUALITY = {
    "feeds.reuters.com": 1,
    "feeds.bbci.co.uk": 1,
    "feeds.a.dj.com": 1,          # Wall Street Journal
    "feeds.marketwatch.com": 2,
    "oilprice.com": 2,
    "stockanalysis.com": 2,
    "nasdaq.com": 2,
    "finance.yahoo.com": 2,
    "www.benzinga.com": 2,
    "www.coindesk.com": 2,
    "cointelegraph.com": 2,
    "seekingalpha.com": 2,
    "www.investing.com": 2,
    "feeds.feedburner.com/zerohedge": 3,  # ZeroHedge — often sensationalist
}

def get_source_tier(feed_url: str) -> int:
    """Return quality tier (1/2/3) for a feed URL. Default 2."""
    for domain, tier in SOURCE_QUALITY.items():
        if domain in feed_url:
            return tier
    return 2


# --- RSS News Feeds (15 sources) ---
RSS_FEEDS = [
    # Major financial news
    "https://feeds.reuters.com/reuters/businessNews",
    "https://feeds.bbci.co.uk/news/business/rss.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://feeds.marketwatch.com/marketwatch/marketpulse/",
    "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml",
    # Commodities & macro
    "https://oilprice.com/rss/main",
    "https://feeds.feedburner.com/zerohedge/feed",
    # Small cap & growth
    "https://stockanalysis.com/rss/news.xml",
    "https://www.benzinga.com/feed",
    "https://finance.yahoo.com/news/rssindex",
    # Crypto
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    # IPO & deals
    "https://www.nasdaq.com/feed/rssoutbound?category=IPOs",
    # Investing commentary
    "https://seekingalpha.com/market_currents.xml",
    "https://www.investing.com/rss/news_25.rss",
]

# --- Keywords That Trigger News Analysis ---
TRIGGER_KEYWORDS = [
    # Your specific holdings (tickers + company names)
    "NVIDIA", "NVDA", "GPU", "H100", "Blackwell",
    "Palantir", "PLTR", "government AI", "defense AI",
    "IonQ", "IONQ", "quantum advantage",
    "Axon", "AXON", "Taser", "body camera", "police tech",
    "Cellebrite", "CLBT", "mobile forensics",
    "Oddity Tech", "ODD",
    "CoreWeave", "CRWV", "GPU cloud",
    "Rigetti", "RGTI",
    "Rheinmetall", "RHM",
    "Ondas", "ONDS", "railroad drone",
    "BYD", "BYDDY",
    "Barrick", "GOLD",
    "Shell",
    # Crypto
    "bitcoin", "Bitcoin", "BTC",
    "ethereum", "Ethereum", "ETH",
    "solana", "Solana", "SOL",
    "crypto", "cryptocurrency",
    "crypto regulation", "crypto ETF", "stablecoin", "blockchain",
    # Energy & commodities
    "oil", "gas", "gold", "silver", "copper", "lithium", "coal",
    "OPEC", "energy crisis", "pipeline", "Strait of Hormuz",
    "commodity", "crude", "LNG", "uranium",
    "oil price", "natural gas",
    # Geopolitical
    "Middle East", "Israel", "Iran", "Ukraine", "Russia", "China",
    "Taiwan", "North Korea", "conflict", "war", "sanctions",
    "ceasefire", "invasion", "military", "NATO", "nuclear",
    # Macro & economy
    "interest rate", "Federal Reserve", "Fed", "rate cut", "rate hike",
    "inflation", "recession", "GDP", "unemployment", "debt ceiling",
    "economic crisis", "bank collapse", "currency crisis", "IMF",
    "dollar", "central bank", "CPI", "jobs report",
    # Markets & deals
    "IPO", "goes public", "S-1 filing", "SPAC",
    "merger", "acquisition", "takeover", "billion deal",
    "buyout", "bankruptcy", "short squeeze",
    "market crash", "stock surge",
    "earnings beat", "earnings miss", "guidance raised",
    # Tech & AI
    "SpaceX", "Elon Musk", "Nvidia", "semiconductor", "AI boom",
    "artificial intelligence", "AI chip", "chip shortage", "data center",
    "quantum computing", "quantum breakthrough",
    "Apple", "Microsoft", "Google", "Meta",
    "OpenAI", "robotics", "cybersecurity breach",
    "AI spending",
    # EV & green energy
    "Tesla", "electric vehicle", "battery",
    "solar", "wind energy", "hydrogen", "green energy", "climate deal",
    # Defense & aerospace
    "defense spending", "Lockheed", "arms deal",
    "military contract", "drone", "space race",
    "DoD contract",
    # Pharma & biotech
    "drug approval", "FDA", "FDA approval", "FDA breakthrough",
    "cancer", "vaccine", "biotech",
    "clinical trial", "pandemic", "outbreak",
    # Small cap specific
    "government contract", "patent approved", "partnership announced",
    # Commodities & supply chain
    "wheat", "food crisis", "drought", "supply chain",
    "shipping", "port strike",
]

# --- Bot Behaviour ---
CHECK_INTERVAL_MINUTES = 30
MAX_ITEMS_PER_FEED = 10

# Only send portfolio alerts for HIGH urgency events (reduces noise significantly)
MIN_URGENCY = "high"

# Only send opportunity alerts with HIGH or MEDIUM confidence
CONFIDENCE_THRESHOLD = 65  # percent

# Claude model (standard — used for all regular analysis)
CLAUDE_MODEL = "claude-sonnet-4-6"

# Claude model for deep extended thinking (moonshot analysis)
# Extended thinking uses more compute but finds better opportunities
CLAUDE_DEEP_MODEL = "claude-opus-4-6"

# Max tokens per analysis response
MAX_RESPONSE_TOKENS = 600

# Max tokens for weekly picks (more detail needed)
MAX_WEEKLY_TOKENS = 1000

# Max tokens for deep moonshot analysis (includes thinking tokens)
MAX_MOONSHOT_TOKENS = 12000
MOONSHOT_THINKING_BUDGET = 8000  # tokens Claude uses to "think" before answering

# Number of days back to scan congressional trades
CONGRESS_LOOKBACK_DAYS = 7

# Portfolio tickers (for matching opportunities to holdings)
YOUR_TICKERS = [
    "NVDA", "BTC", "RHM", "PLTR", "IONQ", "AXON",
    "CLBT", "ODD", "CRWV", "RGTI", "BYDDY", "ONDS",
    "ETH", "SOL", "VUSA", "GOLD",
]

# --- Sentiment Monitoring ---
# Reddit RSS feeds for trending ticker mentions (no API key needed)
REDDIT_FEEDS = [
    "https://www.reddit.com/r/wallstreetbets/new.json?limit=25&sort=new",
    "https://www.reddit.com/r/stocks/new.json?limit=25&sort=new",
    "https://www.reddit.com/r/investing/new.json?limit=25&sort=new",
    "https://www.reddit.com/r/smallstreetbets/new.json?limit=25&sort=new",
    "https://www.reddit.com/r/pennystocks/new.json?limit=25&sort=new",
    "https://www.reddit.com/r/Superstonk/new.json?limit=25&sort=new",
]

# StockTwits trending API (free, no auth required)
STOCKTWITS_TRENDING_URL = "https://api.stocktwits.com/api/2/streams/trending.json"

# Minimum Reddit mentions in 1 hour to trigger a sentiment alert
REDDIT_MENTION_THRESHOLD = 5

# Batch processing
BATCH_PENDING_FILE = "data/batch_pending.json"
BATCH_STATE_FILE = "data/batch_state.json"
