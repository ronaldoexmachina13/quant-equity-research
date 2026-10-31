"""
SPY as a reference-only second benchmark (roadmap item, no hypothesis tested).

The official benchmark of this project stays the equal-weight basket of the
17 study stocks. SPY (the S&P 500 ETF) is added only so that a reader can see
how the strategies compare with the market index most people think of. It does
not change any strategy, any holding or any published figure.

Method: the same conventions as the rest of the project. Adjusted close prices
from yfinance (which include dividends), month-end prices with resample("ME"),
monthly returns with pct_change, a flat 2% risk-free rate for the Sharpe ratio.
Returns are shown in the same two periods as everything else: in sample
(January 2021 to December 2024) and out of sample (January 2025 to August 2026).

Output goes to two NEW files and nothing is overwritten:
  results/spy_reference_monthly_returns.csv
  results/spy_reference_summary.csv
If either already exists the script stops.

Run on the PC (it downloads from Yahoo Finance):
  python run_spy_reference.py
"""
import os

import pandas as pd

from config import (START_DATE, END_DATE, IN_SAMPLE_START, IN_SAMPLE_END,
                    OUT_OF_SAMPLE_START, OUT_OF_SAMPLE_END)
from src.data_loader import get_price_history
from src.backtest import calculate_monthly_returns
from src.risk import (total_return, annualized_return, annualized_volatility,
                      sharpe_ratio, max_drawdown)

RETURNS_PATH = "results/spy_reference_monthly_returns.csv"
SUMMARY_PATH = "results/spy_reference_summary.csv"


def main():
    for path in (RETURNS_PATH, SUMMARY_PATH):
        if os.path.exists(path):
            raise SystemExit(f"{path} already exists. This script never overwrites results. Stopping.")

    prices = get_price_history("SPY", START_DATE, END_DATE)
    if isinstance(prices.columns, pd.MultiIndex):
        prices.columns = prices.columns.get_level_values(0)
    prices = prices.iloc[:, 0]

    returns = calculate_monthly_returns(prices.to_frame("SPY"))["SPY"]
    in_sample = returns[IN_SAMPLE_START:IN_SAMPLE_END]
    out_sample = returns[OUT_OF_SAMPLE_START:OUT_OF_SAMPLE_END]

    # Same month counts as the strategies, and no gaps.
    if len(in_sample) != 48 or len(out_sample) != 20:
        raise SystemExit(f"Unexpected month counts: {len(in_sample)} in sample, {len(out_sample)} out of sample. Stopping.")
    if in_sample.isna().any() or out_sample.isna().any():
        raise SystemExit("Missing monthly returns. Stopping.")

    rows = []
    for period, series in (("In sample", in_sample), ("Out of sample", out_sample)):
        rows.append({
            "period": period,
            "months": len(series),
            "total_return": total_return(series),
            "annualized_return": annualized_return(series),
            "annualized_volatility": annualized_volatility(series),
            "sharpe_ratio": sharpe_ratio(series),
            "max_drawdown": max_drawdown(series),
        })
    summary = pd.DataFrame(rows)

    # Full precision, rounded once at display time (same rule as the other CSVs).
    pd.concat([in_sample, out_sample]).rename("SPY").to_csv(RETURNS_PATH, index_label="date")
    summary.to_csv(SUMMARY_PATH, index=False)

    print(summary.to_string(index=False))
    print(f"\nWrote {RETURNS_PATH} (68 rows) and {SUMMARY_PATH} (2 rows).")


if __name__ == "__main__":
    main()
