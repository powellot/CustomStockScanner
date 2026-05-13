"""
US Stock Scanner
Uses: Relative Volume, % from Daily High, News Events, Price, Float
Output: Rich terminal table, 1 minute updates
"""

# -*- coding: utf-8 -*-

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
    "bear":             "bold #ff4d6d",
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
    "float_max": 50_000_000,

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
    "NVDA", "AMD", "TSLA", "HOOD", "PLTR", "AAPL", "AMZN", "MSFT", "META", "NFLX",
    "GME", "AMC", "BB", "NIO", "LI", "XPEV", "BYND", "F", "GE", "BA", 
    "SNDL", "ZNGA", "CLOV", "WORK", "UPST", "ROKU", "TWTR", "UBER", "LYFT", "SNAP",
    "SHOP", "SQ", "PYPL", "INTC", "CSCO", "QCOM", "ADBE", "CRM", "ORCL", "IBM",
    "INTU", "NOW", "ZM", "DOCU", "CRWD", "OKTA", "DDOG", "NET", "FSLY", "ZS",
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
# Price Fetching
# --------------------------------

def fetch_quote(ticker: str) -> Optional[dict]:
    # Fetch current price and daily high. Returns None on failure.
    try:
        stock = yf.Ticker(ticker)
        fi = stock.fast_info

        price = fi.last_price
        day_high = fi.day_high
        day_low = fi.day_low
        volume = fi.three_month_average_volume # Use 3 month average volume as a proxy for current volume to avoid excessive calls.
        # Prefer today's volume if available
        try:
            volume = fi.last_volume
        except Exception:
            pass

        if not price or price <= 0:
            return None
        if not day_high or day_high <= 0:
            return None
        
        return {
            "price": round(price, 2),
            "day_high": round(day_high, 2),
            "day_low": round(day_low, 2) if day_low else 0,
            "volume": round(volume, 2) if volume else 0,
        }
    except Exception:
        return None
    
# --------------------------------
# CORE SCANNER LOGIC
# --------------------------------
def scan_ticker(ticker: str, config: dict) -> Optional[dict]:
    # Scan a single ticker against the criteria. Returns result dict or None if it doesn't pass.
    quote = fetch_quote(ticker)
    if not quote:
        return None

    price =     quote["price"]
    day_high =  quote["day_high"]
    day_low =   quote["day_low"]
    volume =    quote["volume"]

    # Price filter
    if price < config["price_min"] or price > config["price_max"]:
        return None

    # RVOL filter
    avg_volume = fetch_avg_volume(ticker)
    rvol = (volume / avg_volume) if avg_volume > 0 else 0
    if rvol < config["rvol_min"]:
        return None

    # % from daily high filter
    pct_from_high = ((day_high - price) / day_high) * 100 if day_high > 0 else 0
    if pct_from_high > config["pct_high_threshold"]:
        return None

    # Float filter
    float_shares = fetch_float(ticker)
    if float_shares is not None and float_shares > config["float_max"]:
        return None

    # News filter
    news_headlines = fetch_news(ticker) if config["require_news"] else []
    if config["require_news"] and not news_headlines:
        return None
    
    # Day range %
    day_range_pct = ((day_high - day_low) / day_low * 100) if day_low else 0

    return {
        "ticker":           ticker,
        "price":            price,
        "day_high":         day_high,
        "pct_from_high":    round(pct_from_high, 2),
        "volume":           volume,
        "avg_volume":       int(avg_volume),
        "rvol":             round(rvol, 2),
        "float":            float_shares,
        "day_range_pct":    round(day_range_pct, 2),
        "news":             news_headlines,
        "has_news":         len(news_headlines) > 0,
        "top_headline":     news_headlines[0][:60] + "..." if news_headlines else "--",
    }   

def run_scan(universe: list[str], config: dict) -> list[dict]:
    # Run the scanner across the universe and return a list of results. Parallel-ish.
    results = []
    for ticker in universe:
        result = scan_ticker(ticker, config)
        if result:
            results.append(result)
    # Sort results by RVOL desc, then % from high asc
    results.sort(key = lambda x: (-x["rvol"], x["pct_from_high"]))
    return results[:config["top_n"]] # Return top N results

# --------------------------------
# Table Rendering
# --------------------------------

# Formting helpers for table display

def format_float(val: Optional[float]) -> str:
    if val is None:
        return "--"
    elif val >= 1_000_000:
        return f"{val / 1_000_000:.1f}M"
    elif val >= 1_000:
        return f"{val / 1_000:.0f}K"
    return str(int(val))

def format_volume(val: int) -> str:
    if val >= 1_000_000:
        return f"{val / 1_000_000:.2f}M"
    elif val >= 1_000:
        return f"{val / 1_000:.0f}K"
    return str(val)

def color_rvol(rvol: float) -> str:
    if rvol >= 5:   return "#ff4500"    # blazing
    if rvol >= 3:   return "#ffcc00"    # hot
    if rvol >= 2:   return "#00ff88"    # good
    return "#a8b2c1"                    # neutral

def color_pct(pct: float) -> str:
    if pct >= -1:   return "#00ff88"
    if pct >= -3:   return "#7fffb2"
    if pct >= -5:   return "#ffcc00"
    return "#ff4d6d"

def build_table(results: list[dict], scan_time: str, config: dict) -> Table:
    table = Table(
        title = None,
        box = box.SIMPLE_HEAD,
        border_style = "#1e2d40",
        header_style = "bold #1c8fa6",
        show_footer = False,
        pad_edge = True,
        expand = True,
    )

    # Define columns
    table.add_column("#", style = "dim #3a4455", width = 3, justify = "right")
    table.add_column("TICKER", style = "bold #e8f0fe", width = 7, justify = "left")
    table.add_column("PRICE", style = "#c9d6e3", width = 8, justify = "right")
    table.add_column("DAY HIGH", style = "#7c8fa6", width = 9, justify = "right")
    table.add_column("% HOD", width = 8, justify = "right")
    table.add_column("RVOL", width = 7, justify = "right")
    table.add_column("VOLUME", style = "#a8b2c1", width = 10, justify = "right")
    table.add_column("AVG VOL", style = "dim #6b7a90", width = 10, justify = "right")
    table.add_column("FLOAT", width = 10, justify = "right")
    table.add_column("DAY RNG %", width = 9, justify = "right")
    table.add_column("NEWS", width = 5, justify = "center")
    table.add_column("TOP HEADLINE", min_width = 30, justify = "left")

    # Add rows
    for i, r in enumerate(results, 1):
        rvol = r["rvol"]
        pct_hod = r["pct_from_high"]
        has_news = r["has_news"]

        rvol_str = f"[{color_rvol(rvol)}]{rvol:.2f}x[/]"
        pct_str = f"[{color_pct(pct_hod)}]{pct_hod:+.2f}%[/]"
        news_str = "[news_badge] YES [/]" if has_news else "[no_news_badge] NO [/]"
        float_str = format_float(r["float"])
        headline = r["top_headline"]
        if headline != "--":
            headline = f"[dim #8899aa]{headline}[/]"
        else:
            headline = "[dim #3a4455]--[/]"

        drng_color =  "#ffcc00" if r["day_range_pct"] >= 10 else "#6b7a90"
        drng_str = f"[{drng_color}]{r['day_range_pct']:.1f}%[/]"

        float_color = "#ff4d6d" if (r["float"] or 0) < 10_000_000 else (
                      "#ffcc00" if (r["float"] or 0) < 25_000_000 else "#6b7a90")
        float_styled = f"[{float_color}]{float_str}[/]"

        table.add_row(
            str(i),
            r["ticker"],
            f"${r['price']:.2f}",
            f"${r['day_high']:.2f}",
            pct_str,
            rvol_str,
            format_volume(r["volume"]),
            format_volume(r["avg_volume"]),
            float_styled,
            drng_str,
            news_str,
            headline,
        )
    
    return table

def build_layout(results: list[dict], scan_time: str, config: dict, status: str) -> str:
    return results # Rendered inline

# --------------------------------
# Header Panel + Stats Bar
# --------------------------------

def header_panel(scan_time: str, scan_count: int, candidates: int) -> Panel:
    now = datetime.datetime.now().strftime("%H:%M:%S ET")
    title_text = Text()
    title_text.append("US STOCK SCANNER", style = "bold #00c9ff")
    title_text.append(f"    |    Last Scan: {scan_time}", style = "dim #a8b2c1")

    meta_text = Text()
    meta_text.append(f"Scan #: {scan_count}\n", style = "#6b7a90")
    meta_text.append(f"Found: ", style = "#6b7a90")
    meta_text.append(f"{candidates}", style = "bold #00ff88" if candidates > 0 else "dim #6b7a90")
    meta_text.append(f" candidates", style = "#6b7a90")

    content = Text()
    content.append(title_text)
    content.append("\n")
    content.append(meta_text)

    return Panel(
        content,
        border_style = "#0d3a5c",
        style = "on #060d16",
        padding=(0, 2),
    )

def filter_panel(config: dict) -> Panel:
    lines = Text()
    lines.append("ACTIVE FILTERS\n", style = "bold #7c8fa6")
    lines.append(f"  Price:        ", style = "dim #6b7a90")
    lines.append(f"${config['price_min']} - ${config['price_max']}\n", style = "#c9d6e3")
    lines.append(f"  Min. RVOL:    ", style = "dim #6b7a90")
    lines.append(f"{config['rvol_min']}x\n", style = "#ffcc00")
    lines.append(f"  Max Float:    ", style = "dim #6b7a90")
    lines.append(format_float(config['float_max']) + "\n", style="#ff4d6d")
    lines.append(f"  % from HOD:   ", style = "dim #6b7a90")
    lines.append(f"≥ {config['pct_high_threshold']}%\n", style = "#00ff88")
    lines.append(f"  Req. News:    ", style = "dim #6b7a90")
    lines.append("Yes\n" if config["require_news"] else "No\n", style = "#a8b2c1")
    lines.append(f"  Universe:     ", style = "dim #6b7a90")
    lines.append(f"{len(UNIVERSE)} tickers", style = "#a8b2c1")

    return Panel(lines, border_style = "#1e2d40", style = "on #060d16", padding = (0, 1))

def legend_panel() -> Panel:
    lines = Text()
    lines.append("RVOL COLOR\n", style = "bold #7c8fa6")
    lines.append("  ■ ", style = "#ff4500"); lines.append("5x+  Blazing\n", style = "dim")
    lines.append("  ■ ", style = "#ffcc00"); lines.append("3x+  Hot\n",     style = "dim")
    lines.append("  ■ ", style = "#00ff88"); lines.append("2x+  Active\n",  style = "dim")
    lines.append("  ■ ", style = "#a8b2c1"); lines.append("1.5x Mild\n",    style = "dim")
    lines.append("\nFLOAT COLOR\n", style = "bold #7c8fa6")
    lines.append("  ■ ", style = "#ff4d6d"); lines.append("<10M  Low\n",    style = "dim")
    lines.append("  ■ ", style = "#ffcc00"); lines.append("<25M  Medium\n", style = "dim")
    lines.append("  ■ ", style = "#6b7a90"); lines.append("25M+  Large\n",  style = "dim")

    return Panel(lines, border_style = "#1e2d40", style = "on #060d16", padding = (0, 1))

# --------------------------------
# Main Loop
# --------------------------------

def main():
    config = DEF_CONFIG.copy()
    num_scan = 0
    results = []
    status_msg = "Initializing scanner..."
    scan_time = "--"

    console.clear()

    # Parse command line args
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--price-min" and i + 1 < len(args):
            config["price_min"] = float(args[i + 1])
            i += 2
            continue
        if a == "--price-max" and i + 1 < len(args):
            config["price_max"] = float(args[i + 1])
            i += 2
            continue
        if a == "--rvol-min" and i + 1 < len(args):
            config["rvol_min"] = float(args[i + 1])
            i += 2
            continue
        if a == "--float-max" and i + 1 < len(args):
            config["float_max"] = int(float(args[i + 1]) * 1_000_000) # Accept float input in millions
            i += 2
            continue
        if a == "--pct-high" and i + 1 < len(args):
            config["pct_high_threshold"] = float(args[i + 1])
            i += 2
            continue
        if a == "--interval" and i + 1 < len(args):
            config["update_interval"] = int(args[i + 1])
            i += 2
            continue
        if a == "--require-news":
            config["require_news"] = True
            i += 1
            continue
        if a == "--top" and i + 1 < len(args):
            config["top_n"] = int(args[i + 1])
            i += 2
            continue
        i += 1

    def do_scan():
        nonlocal results, scan_time, status_msg, num_scan
        status_msg = f"[bold #ffcc00]Scanning {len(UNIVERSE)} tickers...[/]"
        num_scan += 1
        results = run_scan(UNIVERSE, config)
        scan_time = datetime.datetime.now().strftime("%H:%M:%S")
        status_msg = f"[bold #00ff88]Scan complete. Next scan in {config['update_interval']} seconds.[/]"

    with Live(console = console, refresh_per_second = 4, screen = True) as live:
        while True:
            # Run scan
            do_scan()
            # Build and render table
            table = build_table(results, scan_time, config)

            top_panel = Columns([filter_panel(config), legend_panel(),], expand = False, equal = False, padding = (0, 2))

            status_text = Text.from_markup(status_msg)

            from rich.console import Group
            display = Group(
                header_panel(scan_time, num_scan, len(results)),
                Rule(style = "#1e2d40"),
                top_panel,
                Rule(style = "#1e2d40"),
                table,
                Rule(style = "#1e2d40"),
                Align.center(status_text),
                Align.center(Text.from_markup("[dim #6b7a90]Data provided by Yahoo Finance | Ctrl+C to exit[/]")),
            )

            live.update(display)

            # Wait for next scan
            for _ in range(config["update_interval"] * 4):
                time.sleep(0.25)
                # Keep the live display responsive during the wait
                live.update(display)
            

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[dim]Scanner stopped by user.[/dim]")
