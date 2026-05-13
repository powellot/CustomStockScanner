"""
US Stock Scanner
Uses: Relative Volume, % from Daily High, News Events, Price, Float
Output: Rich terminal table, 1 minute updates
"""

# ------------------------------------
# Imports
# ------------------------------------

import sys
import time
import datetime
import threading
import warnings
from typing import Optional

warnings.filterwarnings("ignore")

import yfinance as yf
import pandas as pd
import requests

# Console Imports
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich.style import Style
from rich.columns import Columns
from rich import box
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.rule import Rule
from rich.theme import Theme

# --------------------------------
# Console Theme
# --------------------------------

current_theme = Theme({
    "header":           "bold white on #0d1117",
    "bull":             "bold #00ff88",
    "bear":             "bold ff4d6d",
    "neutral":          "bold #a8b2c1",
    "hot":              "bold #ffcc00",
    "dim_text":         "dim #6b7a90",
    "label":            "bold #7c8fa6",
    "news_badge":       "bold white on #1a6cf7",
    "no_news_badge":    "dim #3a4455",
    "title":            "bold #00c9ff",
    "border":         "#1e2d40",
    "stat_box":         "on #0d1a26",
})

console = Console(theme = current_theme, highlight = False)

# --------------------------------
# Configuration
# --------------------------------

DEF_CONFIG = {
    # Price range (USD)
    "price_min": 1.00,
    "price_max": 50.00,

    # RVOL threshold (e.g. 2.0 means 200% of average volume)
    "rvol_min": 1.5,

    # Float max (Number of shares available for trading)
    "float_max": 50000000,

    # % from daily high threshold (e.g. 5.0 means within 5% of daily high)
    "pct_high_threshold": 8.0, # Consider changing this to be % gain from open.

    # News filter (True/False)
    "require_news": True, # Strict news filter

    # Scanner update interval (seconds)
    "update_interval": 60,

    # Number of top results to display
    "top_n": 25,
}

# --------------------------------
# Watchlist / Universe
# Scan top % gainers + user-defined watchlist.
# --------------------------------

WATCHLIST = [
    # Common low-float mover tickers
    "NVDA", "AMD", "TSLA", "MARA", "RIOT", "CLSK",
    "UPST", "SOFI", "HOOD", "PLTR", "RKLB", "JOBY",
    "SMCI", "AI", "SOUN", "BBAR", "IONQ", "ARRY",
    "NKLA", "BLNK", "CHPT", "SPWR", "NOVA", "RUN",
    "HIMS", "OPEN", "OPRA", "TDUP", "BIGC", "LMND",
    "CLOV", "BBIG", "NKLA", "SENS", "RSSS", "MVIS",
    "WKHS", "RIDE", "SOLO", "GOEV", "FSR", "PTRA",
    "ZEV", "FFIE", "MULN", "IDEX", "SEEL", "BCRX",
]
 
UNIVERSE = list(set(WATCHLIST))

# --------------------------------
# News Fetching (Yahoo Finance)
# --------------------------------

NEWS_CACHE: dict[str, tuple[list, float]] = {} # {ticker: (headline, timestamp)}
NEWS_CACHE_DURATION = 5 * 60 # 5 minutes

def fetch_news(ticker: str) -> list[str]:
    # Return today's headlines for a ticker. Uses caching to avoid excessive calls.
    now = time.time()
    if ticker in NEWS_CACHE:
        headlines, timestamp = NEWS_CACHE[ticker]
        if now - timestamp < NEWS_CACHE_DURATION:
            return headlines

    try:
        stock = yf.Ticker(ticker)
        news_items = stock.news or []
        today = datetime.date.today()
        headlines = []
        for item in news_items[:5]: # Limit to top 5 news items
            # providerPublishTime is a UNIX timestamp
            publish_time = item.get("providerPublishTime", 0)
            publish_date = datetime.date.fromtimestamp(publish_time)
            if publish_date == today:
                title = item.get("title", "")
                if title:
                    headlines.append(title)
        NEWS_CACHE[ticker] = (headlines, now)
        return headlines
    except Exception:
        return []        
    
# --------------------------------
# Volume Baseline (RVOL denominator)
# --------------------------------

VOLUME_CACHE: dict[str, tuple[float, float]] = {} # {ticker: (avg_volume, timestamp)}
VOLUME_CACHE_DURATION = 60 * 60 # 1 hour

def fetch_avg_volume(ticker: str, days: int = 20) -> float:
    # Fetch average daily volume over the past 'days' days. Uses caching.
    now = time.time()
    if ticker in VOLUME_CACHE:
        avg_volume, timestamp = VOLUME_CACHE[ticker]
        if now - timestamp < VOLUME_CACHE_DURATION:
            return avg_volume

    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=f"{days + 5}d")
        if hist.empty or len(hist) < 3:
            return 0.0
        avg_volume = float(hist["Volume"].tail(days).mean())
        VOLUME_CACHE[ticker] = (avg_volume, now)
        return avg_volume
    except Exception:
        return 0.0
    
# --------------------------------
# Float Fetching
# --------------------------------

FLOAT_CACHE: dict[str, tuple[Optional[float], float]] = {} # {ticker: (float, timestamp)}
FLOAT_CACHE_DURATION = 6 * 60 * 60 # 6 hours

def fetch_float(ticker: str) -> Optional[float]:
    # Fetch float (number of shares available for trading). Uses caching. Yahoo finance "fast_info".
    now = time.time()
    if ticker in FLOAT_CACHE:
        val, timestamp = FLOAT_CACHE[ticker]
        if now - timestamp < FLOAT_CACHE_DURATION:
            return val
        
    try:
        stock = yf.Ticker(ticker)
        fi = stock.fast_info #fast_info.shares is total shares; use info for float
        info = stock.info
        float_shares = info.get("floatShares") or info.get("sharesOutstanding")
        result = float(float_shares) if float_shares else None
        FLOAT_CACHE[ticker] = (result, now)
        return result
    except Exception:
        FLOAT_CACHE[ticker] = (None, now)
        return None
    
# --------------------------------
# Main Loop
# --------------------------------

def main():
    num_scan = 0
    results = []
    status_msg = "Initializing scanner..."

    console.clear()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[dim]Scanner stopped by user.[/dim]")
