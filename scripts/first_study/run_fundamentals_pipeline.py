import sys
import time

import pandas as pd
import requests

from config import UNIVERSE
from src.database import create_tables, save_book_value
from src.factors import load_prices
from src.fundamentals import get_book_value_per_share, forward_fill_book_value
from src.output_guard import refuse_if_table_has_rows
from src.universe import download_with_retries


def sec_says_missing(exc: Exception) -> bool:
    """True only when the SEC answered 404 or does not list the ticker; any other failure is an error to retry."""
    if isinstance(exc, KeyError):
        return True
    response = getattr(exc, "response", None)
    return isinstance(exc, requests.HTTPError) and response is not None and response.status_code == 404


def build_book_value_table(tickers: list[str], target_dates: pd.DatetimeIndex,
                           fetch_book_value=get_book_value_per_share, sleep=time.sleep) -> pd.DataFrame:
    """
    Fetch and forward-fill book value per share for every ticker in the
    universe, onto a shared set of target dates (the same month-end dates
    used for prices), and assemble into one wide-format DataFrame.

    Parameters
    ----------
    tickers : list[str]
        Tickers to fetch (normally config.UNIVERSE).
    target_dates : pd.DatetimeIndex
        Month-end dates to align book value onto; must match the dates
        factors.calculate_value_score() will later use, so book value and
        prices line up exactly.

    Returns
    -------
    pd.DataFrame
        Wide-format book value per share: Date index, tickers as columns.
        A ticker with no usable filings (e.g. V) ends up as an all-NaN
        column rather than being dropped, so save_book_value() and later
        code can see it was attempted and legitimately has no data.
        If a download fails for any other reason the function raises, so a
        network failure is never stored as missing data.
    """
    columns = {}
    failed = {}

    for ticker in tickers:
        print(f"Fetching {ticker}...")
        # Three outcomes, as in the 500-stock pipeline: "ok", "empty" (the SEC confirms it has no
        # data for this ticker) and "error" (a network or server failure, which is never read as "no data").
        status, bv, attempts, message = download_with_retries(
            lambda ticker=ticker: fetch_book_value(ticker),
            is_missing=sec_says_missing,
            missing_confirmations=1,
            sleep=sleep,
        )
        if status == "error":
            print(f"  {ticker}: FAILED after {attempts} attempts: {message}")
            failed[ticker] = message
            continue
        if status == "empty":
            print(f"  {ticker}: the SEC has no data for this ticker ({message})")
            columns[ticker] = pd.Series(index=target_dates, dtype="float64")
            continue
        filled = forward_fill_book_value(bv, target_dates)
        filled = filled.set_index("date")["book_value_per_share"]
        columns[ticker] = filled
        print(f"  {ticker}: {filled.notna().sum()} of {len(target_dates)} target dates covered")

    if failed:
        # Stop before anything is saved: a failed download must not be stored as "no book value".
        raise RuntimeError(f"Book value download failed for {sorted(failed)}. Nothing was saved. Run again later.")

    bv_df = pd.DataFrame(columns)
    bv_df.index.name = "date"
    return bv_df


if __name__ == "__main__":
    refuse_if_table_has_rows("book_value", sys.argv)
    create_tables()

    prices = load_prices()
    monthly_dates = prices.resample("ME").last().index

    print(f"Fetching book value per share for {len(UNIVERSE)} tickers, "
          f"aligned to {len(monthly_dates)} month-end dates "
          f"({monthly_dates.min().date()} to {monthly_dates.max().date()})...\n")

    book_value = build_book_value_table(UNIVERSE, monthly_dates)
    save_book_value(book_value)

    print("\nFundamentals pipeline complete.")
