import pandas as pd
from src.database import get_connection


def load_prices() -> pd.DataFrame:
    """
    Load all stored adjusted close prices from the database,
    reshaped into wide format (Date index, one column per ticker) —
    this is the format most convenient for return calculations.

    Returns
    -------
    pd.DataFrame
        Wide-format prices: Date index, tickers as columns.
    """
    conn = get_connection()
    long_df = pd.read_sql_query("SELECT date, ticker, adj_close FROM prices", conn)
    conn.close()

    long_df["date"] = pd.to_datetime(long_df["date"])
    wide_df = long_df.pivot(index="date", columns="ticker", values="adj_close")
    wide_df = wide_df.sort_index()
    return wide_df


def calculate_momentum(prices: pd.DataFrame, lookback_months: int = 12, skip_months: int = 1) -> pd.DataFrame:
    """
    Calculate 12-1 style momentum scores for each ticker at each date.

    momentum = price[t - skip_months] / price[t - lookback_months] - 1

    Parameters
    ----------
    prices : pd.DataFrame
        Wide-format adjusted close prices (Date index, tickers as columns).
    lookback_months : int
        How many months back the lookback window starts (default 12).
    skip_months : int
        How many recent months to exclude, to avoid short-term reversal (default 1).

    Returns
    -------
    pd.DataFrame
        Momentum scores, same shape as input, with NaN where insufficient history exists.
    """
    # Resample to month-end prices — momentum is conventionally measured
    # on monthly, not daily, price snapshots.
    monthly_prices = prices.resample("ME").last()

    end_price = monthly_prices.shift(skip_months)
    start_price = monthly_prices.shift(lookback_months)

    momentum = (end_price / start_price) - 1
    return momentum


def calculate_value_score(prices: pd.DataFrame, book_value: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate a Value factor score from Price-to-Book ratio.

    Low P/B is attractive for Value (a cheap stock relative to its book
    equity) -- the opposite ranking direction from momentum, where high
    score wins. To reuse build_portfolio()'s existing top-N selection
    logic unchanged, we return the NEGATIVE of P/B as the score: the
    stock with the lowest P/B has the highest (least negative) score,
    and is correctly selected as a top-N pick.

    Parameters
    ----------
    prices : pd.DataFrame
        Wide-format adjusted close prices (Date index, tickers as columns).
    book_value : pd.DataFrame
        Wide-format book value per share (Date index, tickers as columns),
        as returned by database.load_book_value().

    Returns
    -------
    pd.DataFrame
        Value scores (negative P/B), same shape/index convention as
        calculate_momentum()'s output.
    """
    monthly_prices = prices.resample("ME").last()
    pb_ratio = monthly_prices / book_value
    value_score = -pb_ratio
    return value_score


if __name__ == "__main__":
    prices = load_prices()
    print(f"Loaded prices: {prices.shape[0]} dates x {prices.shape[1]} tickers")
    print(f"Date range: {prices.index.min().date()} to {prices.index.max().date()}\n")

    momentum = calculate_momentum(prices)
    print("Momentum scores — most recent 5 months, all tickers:")
    print(momentum.tail(5).round(3))