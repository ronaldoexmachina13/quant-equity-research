"""
Phase 3, step 2 of 4: price availability from yfinance.

Downloads daily prices 2011-01-01 to 2026-09-01 (end exclusive) for every
ticker in the reconstructed membership with a member month-end from 2011-01
to 2026-08, one ticker at a time, and caches each result. Only the dates
are used: the script records whether a price exists on the last trading
day of each month. No return is computed and no price is stored in the
database.

Error handling (Amendment 6, item 5): YFPricesMissingError or
YFTzMissingError on two separate attempts is a confirmed empty result.
Anything else, including a YFPricesMissingError that carries a Yahoo HTTP
status code (a server or rate-limit reply, not "no data"), is an error:
retried up to three times, then listed as an error and never counted as
missing. A rerun skips every ticker already cached or confirmed empty and
retries only the errors.
"""
import gzip
import sqlite3
import time

import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFPricesMissingError, YFTzMissingError

from src.universe import (
    FEASIBILITY_DB_PATH, PRICE_START, PRICE_END, FIRST_PRICE_MONTH, EVALUATION_END,
    cache_dir, month_range, tickers_in_window, trading_calendar, months_with_price,
    download_with_retries, write_bytes_atomic, write_json, create_feasibility_tables,
)

PAUSE_BETWEEN_TICKERS = 0.5  # seconds, to stay well inside Yahoo's informal rate limits


class UnexpectedEmptyResult(Exception):
    """yfinance returned an empty frame without raising: treated as an error, not as missing."""


def is_yfinance_missing(exc: Exception) -> bool:
    return isinstance(exc, (YFPricesMissingError, YFTzMissingError)) and "status_code" not in str(exc)


def fetch_prices(ticker: str) -> pd.DataFrame:
    data = yf.Ticker(ticker).history(start=PRICE_START, end=PRICE_END, auto_adjust=False, actions=False)
    if data is None or data.empty:
        raise UnexpectedEmptyResult(f"{ticker}: empty frame without an exception")
    data.index = pd.DatetimeIndex(data.index).tz_localize(None).normalize()
    data.index.name = "Date"
    return data


def cache_paths(ticker: str):
    folder = cache_dir() / "prices"
    return folder / f"{ticker}.csv.gz", folder / f"{ticker}.empty.json"


def download_all(tickers: list[str]) -> dict:
    """Download every ticker that is not cached yet. Returns {ticker: (status, attempts, message)} for this run."""
    yf.config.debug.hide_exceptions = False
    run_status = {}
    pending = [t for t in tickers if not any(p.exists() for p in cache_paths(t))]
    print(f"{len(tickers) - len(pending)} of {len(tickers)} tickers already cached; downloading {len(pending)}.")

    for i, ticker in enumerate(pending, start=1):
        data_path, empty_path = cache_paths(ticker)
        status, data, attempts, message = download_with_retries(
            lambda: fetch_prices(ticker), is_yfinance_missing, missing_confirmations=2)
        if status == "ok":
            write_bytes_atomic(data_path, gzip.compress(data.to_csv().encode("utf-8")))
        elif status == "empty":
            write_json(empty_path, {"ticker": ticker, "attempts": attempts, "message": message})
        run_status[ticker] = (status, attempts, message)
        print(f"  [{i}/{len(pending)}] {ticker}: {status}" + (f" ({message})" if status != "ok" else ""))
        time.sleep(PAUSE_BETWEEN_TICKERS)
    return run_status


def load_cached_dates(tickers: list[str]) -> dict:
    """Dates with a non-missing adjusted close, for every ticker with a cached download."""
    price_dates = {}
    for ticker in tickers:
        data_path, _ = cache_paths(ticker)
        if data_path.exists():
            data = pd.read_csv(data_path, index_col="Date", parse_dates=True)
            price_dates[ticker] = data.index[data["Adj Close"].notna()]
    return price_dates


def save_status(conn, tickers: list[str], run_status: dict):
    """Status per ticker: ok or empty from the cache, error from this run (never cached)."""
    conn.execute("DELETE FROM download_status WHERE source = 'yfinance'")
    rows = []
    for ticker in tickers:
        data_path, empty_path = cache_paths(ticker)
        if data_path.exists():
            rows.append(("yfinance", ticker, "ok", None, None))
        elif empty_path.exists():
            rows.append(("yfinance", ticker, "empty", None, empty_path.read_text(encoding="utf-8")))
        else:
            status, attempts, message = run_status.get(ticker, ("error", None, "not attempted in this run"))
            rows.append(("yfinance", ticker, "error", attempts, message))
    conn.executemany("INSERT INTO download_status VALUES (?, ?, ?, ?, ?)", rows)


def save_month_end_presence(conn, price_dates: dict, months: list[str]):
    calendar = trading_calendar(price_dates, months)
    missing = calendar[calendar.isna()]
    if not missing.empty:
        raise SystemExit(f"No date reaches the half-of-tickers rule in months {list(missing.index)}; stopping.")

    conn.execute("DELETE FROM trading_calendar")
    conn.executemany("INSERT INTO trading_calendar VALUES (?, ?)",
                     [(m, d.strftime("%Y-%m-%d")) for m, d in calendar.items()])
    conn.execute("DELETE FROM price_month_end")
    rows = [(t, m) for t, dates in price_dates.items() for m in months_with_price(dates, calendar)]
    conn.executemany("INSERT INTO price_month_end VALUES (?, ?)", rows)
    print(f"Trading calendar: {len(calendar)} months, from {len(price_dates)} tickers with data.")
    print(f"price_month_end: {len(rows)} ticker-months with a month-end price.")


if __name__ == "__main__":
    conn = sqlite3.connect(FEASIBILITY_DB_PATH)
    create_feasibility_tables(conn)
    intervals = pd.read_sql_query("SELECT * FROM index_membership", conn)
    if intervals.empty:
        raise SystemExit("index_membership is empty; run run_universe_membership.py first.")

    months = month_range(FIRST_PRICE_MONTH, EVALUATION_END)
    tickers = tickers_in_window(intervals, months)
    print(f"Price download list: {len(tickers)} tickers, {PRICE_START} to {PRICE_END} (end exclusive). "
          f"Cache: {cache_dir() / 'prices'}")

    run_status = download_all(tickers)
    save_status(conn, tickers, run_status)
    save_month_end_presence(conn, load_cached_dates(tickers), months)
    conn.commit()

    counts = pd.read_sql_query(
        "SELECT status, COUNT(*) AS tickers FROM download_status WHERE source = 'yfinance' GROUP BY status", conn)
    print("\nDownload status:\n" + counts.to_string(index=False))
    errors = pd.read_sql_query(
        "SELECT key AS ticker, attempts, message FROM download_status "
        "WHERE source = 'yfinance' AND status = 'error' ORDER BY key", conn)
    if not errors.empty:
        print("\nPersistent errors (not counted as missing; rerun to retry):\n" + errors.to_string(index=False))
    conn.close()
    print("\nPrice step complete.")
