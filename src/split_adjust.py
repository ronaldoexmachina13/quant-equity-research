"""
Split-consistent book value (LIMITATIONS_PLAN.md, Amendments 8 and 9).

Yahoo prices are back-adjusted for every later split, while SEC book value per
share is on the share count of its filing. Before a split the two are on
different bases and P/B comes out too low. Each filed record is divided by the
product of all splits dated after its filing date, which puts book value on
the same basis as the price. The ratio is then the actual price on the date
over the book value per share known on that date, so the split factor cancels
and no later information enters the signal.

The filing date is used and not the period end because the share count of a
filing can already be post-split: WMT's quarter ended 2024-01-31 before its
2024-02-26 split, but the filing of 2024-03-15 uses a share count dated
2024-03-13, so dividing it again would count the split twice.
"""
import pandas as pd

from src.fundamentals import forward_fill_book_value


def splits_from_history(history: pd.DataFrame) -> pd.Series:
    """Split ratios by date from a yfinance history with actions; zero means no split that day."""
    ratios = history["Stock Splits"]
    return ratios[ratios != 0].astype(float)


def split_factor_after(filed_date, splits: pd.Series) -> float:
    """Product of the ratios dated after filed_date, 1.0 if there are none. A split on the filing date does not count."""
    return float(splits[splits.index > pd.Timestamp(filed_date)].prod())


def restate_book_value(records: pd.DataFrame, splits: pd.Series) -> pd.DataFrame:
    """A copy of get_book_value_per_share() output with each record on the same share basis as the price."""
    restated = records.copy()
    factors = [split_factor_after(filed, splits) for filed in restated["filed_date"]]
    restated["book_value_per_share"] = restated["book_value_per_share"].astype(float) / factors
    return restated


def filled_book_value(records: dict, target_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Wide book value per share on target_dates, one column per ticker, using
    forward_fill_book_value() unchanged. Dates with no value are NaN.
    """
    columns = {}
    for ticker, bv in records.items():
        filled = forward_fill_book_value(bv, target_dates).set_index("date")["book_value_per_share"]
        columns[ticker] = pd.to_numeric(filled, errors="coerce")
    return pd.DataFrame(columns, index=target_dates)


def filing_in_force(records: pd.DataFrame, target_dates: pd.DatetimeIndex) -> pd.Series:
    """
    Filing date of the record forward_fill_book_value() uses at each target
    date, NaT if none. Filing dates are passed through that function in place
    of the values, so the 180-day rule stays in one place. Two periods filed
    on the same date have the same answer, however that tie is resolved.
    """
    if records.empty:
        return pd.Series(pd.NaT, index=target_dates, dtype="datetime64[ns]")
    marked = records.assign(book_value_per_share=records["filed_date"])
    filled = forward_fill_book_value(marked, target_dates).set_index("date")["book_value_per_share"]
    return pd.to_datetime(filled).reindex(target_dates)


def restate_stored_book_value(stored: pd.DataFrame, filings: pd.DataFrame, splits: dict) -> pd.DataFrame:
    """
    Stored monthly book value on the same share basis as the price (Amendment
    9): each month's value divided by the product of all splits dated after
    the filing in force that month. Months with no filing in force become NaN.

    Parameters
    ----------
    stored : wide book value per share, as returned by load_book_value().
    filings : wide filing dates, same shape, from filing_in_force().
    splits : {ticker: split ratios by date}.
    """
    restated = stored.copy()
    for ticker in stored.columns:
        factors = [split_factor_after(filed, splits[ticker]) if pd.notna(filed) else float("nan")
                   for filed in filings[ticker]]
        restated[ticker] = stored[ticker] / factors
    return restated
