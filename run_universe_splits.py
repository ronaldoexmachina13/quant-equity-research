"""
Phase 4, Stage 2: split history for the universe (LIMITATIONS_PLAN.md,
Amendments 8 and 10).

Downloads split dates from yfinance once for every ticker with a cached price
file, one file per ticker in the cache's reference/splits folder. A rerun skips
every ticker already saved and retries only the rest. A file is written only
after a non-empty price history came back, so a file with no rows means "no
splits". An empty history or a persistent failure is an error: it is listed
and leaves no file, so it is never read as "no splits".
"""
import time

import yfinance as yf

from run_value_split_check import fetch_splits
from src.universe import cache_dir, download_with_retries
from src.universe_study import cached_tickers
from src.universe_value import split_path, write_split_file

PAUSE_BETWEEN_TICKERS = 0.5  # seconds, the same as run_universe_prices.py


def main():
    yf.config.debug.hide_exceptions = False
    tickers = cached_tickers()
    pending = [t for t in tickers if not split_path(t).exists()]
    print(f"Split download: {len(tickers) - len(pending)} of {len(tickers)} tickers already saved; "
          f"downloading {len(pending)}. Cache: {cache_dir() / 'reference' / 'splits'}")

    errors = {}
    for i, ticker in enumerate(pending, start=1):
        status, ratios, attempts, message = download_with_retries(
            lambda: fetch_splits(ticker), lambda exc: False, missing_confirmations=1)
        if status == "ok":
            write_split_file(ticker, ratios)
        else:
            errors[ticker] = f"{attempts} attempts: {message}"
        print(f"  [{i}/{len(pending)}] {ticker}: " + (f"{len(ratios)} events" if status == "ok" else "ERROR"), flush=True)
        time.sleep(PAUSE_BETWEEN_TICKERS)

    if errors:
        print(f"\nPersistent errors ({len(errors)}), not counted as no splits; rerun to retry:")
        for ticker, message in errors.items():
            print(f"  {ticker}: {message}")
        raise SystemExit(1)
    print(f"\nSplit step complete: {len(tickers)} tickers saved.")


if __name__ == "__main__":
    main()
