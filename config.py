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
END_DATE = "2026-09-01"  # yfinance end date is exclusive, so this fetches through 31 Aug 2026

# Evaluation windows (pre-registered in OUT_OF_SAMPLE_PLAN.md).
# Every existing results file is computed on the IN-SAMPLE window only,
# so extending END_DATE to fetch newer data cannot change those results.
# The out-of-sample window is reported separately, never merged with it.
IN_SAMPLE_START = "2021-01-01"
IN_SAMPLE_END = "2024-12-31"
OUT_OF_SAMPLE_START = "2025-01-01"
OUT_OF_SAMPLE_END = "2026-08-31"
