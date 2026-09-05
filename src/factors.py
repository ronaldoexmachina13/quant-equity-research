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


if __name__ == "__main__":
    prices = load_prices()
    print(f"Loaded prices: {prices.shape[0]} dates x {prices.shape[1]} tickers")
    print(f"Date range: {prices.index.min().date()} to {prices.index.max().date()}\n")

    momentum = calculate_momentum(prices)
    print("Momentum scores — most recent 5 months, all tickers:")
    print(momentum.tail(5).round(3))