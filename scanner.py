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
    "header": "bold white on #0d1117",
    "bull": "bold #00ff88",
    "bear": "bold ff4d6d",
    "neutral":       "bold #a8b2c1",
    "hot":           "bold #ffcc00",
    "dim_text":      "dim #6b7a90",
    "label":         "bold #7c8fa6",
    "news_badge":    "bold white on #1a6cf7",
    "no_news_badge": "dim #3a4455",
    "title":         "bold #00c9ff",
    "border":        "#1e2d40",
    "stat_box":      "on #0d1a26",
})

console = Console(theme = current_theme, highlight = False)

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
