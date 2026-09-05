import pandas as pd
from src.database import get_connection
from src.factors import load_prices, calculate_momentum


def build_portfolio(momentum: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    """
    Construct an equal-weighted portfolio by selecting the top N stocks
    by momentum score at each date.

    Parameters
    ----------
    momentum : pd.DataFrame
        Momentum scores, wide format (Date index, tickers as columns).
    top_n : int
        Number of top-ranked stocks to hold (default 5).

    Returns
    -------
    pd.DataFrame
        Portfolio weights, same shape as momentum input.
        Selected stocks get weight 1/top_n; all others get 0.
        Dates with insufficient valid scores get all-zero weights.
    """
    weights = pd.DataFrame(0.0, index=momentum.index, columns=momentum.columns)

    for date in momentum.index:
        scores = momentum.loc[date].dropna()

        if len(scores) < top_n:
            continue  # not enough valid scores yet (e.g. early history)

        top_tickers = scores.sort_values(ascending=False).head(top_n).index
        weights.loc[date, top_tickers] = 1.0 / top_n

    return weights


if __name__ == "__main__":
    prices = load_prices()
    momentum = calculate_momentum(prices)
    weights = build_portfolio(momentum, top_n=5)

    print("Portfolio weights — most recent 3 months:")
    print(weights.tail(3).round(3))

    print("\nHoldings for most recent month:")
    latest = weights.iloc[-1]
    held = latest[latest > 0]
    print(held)