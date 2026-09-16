import pandas as pd

from config import UNIVERSE
from src.database import create_tables, save_book_value
from src.factors import load_prices
from src.fundamentals import get_book_value_per_share, forward_fill_book_value


def build_book_value_table(tickers: list[str], target_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Fetch and forward-fill book value per share for every ticker in the
    universe, onto a shared set of target dates (the same month-end dates
    used for prices), and assemble into one wide-format DataFrame.

    Parameters
    ----------
    tickers : list[str]
        Tickers to fetch (normally config.UNIVERSE).
    target_dates : pd.DatetimeIndex
        Month-end dates to align book value onto — must match the dates
        factors.calculate_value_score() will later use, so book value and
        prices line up exactly.

    Returns
    -------
    pd.DataFrame
        Wide-format book value per share: Date index, tickers as columns.
        A ticker with no usable filings (e.g. V) ends up as an all-NaN
        column rather than being dropped, so save_book_value() and later
        code can see it was attempted and legitimately has no data.
    """
    columns = {}

    for ticker in tickers:
        print(f"Fetching {ticker}...")
        try:
            bv = get_book_value_per_share(ticker)
            filled = forward_fill_book_value(bv, target_dates)
            filled = filled.set_index("date")["book_value_per_share"]
            columns[ticker] = filled
            usable = filled.notna().sum()
            print(f"  {ticker}: {usable} of {len(target_dates)} target dates covered")
        except Exception as e:
            print(f"  {ticker}: FAILED — {e}")
            columns[ticker] = pd.Series(index=target_dates, dtype="float64")

    bv_df = pd.DataFrame(columns)
    bv_df.index.name = "date"
    return bv_df


if __name__ == "__main__":
    create_tables()

    prices = load_prices()
    monthly_dates = prices.resample("ME").last().index

    print(f"Fetching book value per share for {len(UNIVERSE)} tickers, "
          f"aligned to {len(monthly_dates)} month-end dates "
          f"({monthly_dates.min().date()} to {monthly_dates.max().date()})...\n")

    book_value = build_book_value_table(UNIVERSE, monthly_dates)
    save_book_value(book_value)

    print("\nFundamentals pipeline complete.")
