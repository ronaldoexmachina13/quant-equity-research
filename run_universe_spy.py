"""
Phase 4, Stage 4: SPY reference download (LIMITATIONS_PLAN.md, Amendment 8,
Additions, and Amendment 13, decision 7).

Downloads SPY daily prices once from yfinance, 2011-01-01 to 2026-09-01 (end
exclusive), with the same fetch and retry rules as the Phase 3 price step
(Amendment 6, item 5), and saves them to the cache's reference folder:
  <cache>/reference/SPY.csv.gz
The file is opened with mode "x": if it already exists the script stops, so
the reference series is downloaded once and never replaced. An empty result
or a persistent error leaves no file.

This script only downloads. It computes no return and writes nothing to
results/. run_universe_portfolios.py reads the cached file and checks it
against results/spy_reference_monthly_returns.csv over 2021 to 2026.

Run on the PC (it downloads from Yahoo Finance):
  python run_universe_spy.py
"""
import gzip

import yfinance as yf

from run_universe_prices import fetch_prices, is_yfinance_missing
from src.universe import PRICE_START, PRICE_END, download_with_retries
from src.universe_portfolio import spy_cache_path

TICKER = "SPY"


def main():
    path = spy_cache_path()
    if path.exists():
        raise SystemExit(f"{path} already exists. The SPY reference is downloaded once and never replaced. Stopping.")

    yf.config.debug.hide_exceptions = False
    print(f"Downloading {TICKER} {PRICE_START} to {PRICE_END} (end exclusive) to {path}")
    status, data, attempts, message = download_with_retries(
        lambda: fetch_prices(TICKER), is_yfinance_missing, missing_confirmations=2)
    if status != "ok":
        raise SystemExit(f"{TICKER}: {status} after {attempts} attempt(s): {message}. No file was written.")

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "xb") as f:  # "x": fail rather than overwrite
        f.write(gzip.compress(data.to_csv().encode("utf-8")))
    print(f"Wrote {path}: {len(data)} trading days, {data.index.min():%Y-%m-%d} to {data.index.max():%Y-%m-%d}, "
          f"{int(data['Adj Close'].isna().sum())} days with no adjusted close.")


if __name__ == "__main__":
    main()
