"""
Central configuration for the quant-equity-research project.

Single source of truth for the stock universe and backtest date range,
so they don't have to be kept in sync by hand across data_loader.py,
run_data_pipeline.py, and fundamentals.py.
"""

# 17 large, liquid, sector-diverse US companies. Chosen for size and
# liquidity, not for known historical performance -- see README for the
# reasoning, and for the known coverage gaps in this universe (V, HD, DIS).
UNIVERSE = [
    "AAPL", "MSFT", "JPM", "JNJ", "XOM",
    "PG", "KO", "WMT", "HD", "UNH",
    "CAT", "V", "DIS", "NEE", "LIN",
    "LMT", "RTX"
]

# Backtest date range for price history.
START_DATE = "2020-01-01"
END_DATE = "2024-12-31"