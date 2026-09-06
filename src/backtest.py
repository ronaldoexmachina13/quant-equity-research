import pandas as pd
import matplotlib.pyplot as plt

from src.factors import load_prices, calculate_momentum
from src.portfolio import build_portfolio


def calculate_monthly_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Month-end simple returns for each ticker."""
    monthly_prices = prices.resample("ME").last()
    return monthly_prices.pct_change()


def run_backtest(weights: pd.DataFrame, returns: pd.DataFrame) -> pd.Series:
    """
    Simulate strategy returns: weight[t] applied to return[t] (same index),
    valid because momentum's skip-month already lags the signal appropriately.
    """
    common_dates = weights.index.intersection(returns.index)
    w = weights.loc[common_dates]
    r = returns.loc[common_dates]
    return (w * r).sum(axis=1)


def calculate_benchmark_returns(returns: pd.DataFrame) -> pd.Series:
    """Equal-weight return across all tickers — our passive comparison."""
    return returns.mean(axis=1)


def calculate_cumulative(returns: pd.Series) -> pd.Series:
    return (1 + returns).cumprod() - 1


if __name__ == "__main__":
    prices = load_prices()
    momentum = calculate_momentum(prices)
    weights = build_portfolio(momentum, top_n=5)
    monthly_returns = calculate_monthly_returns(prices)

    # Only evaluate dates where the portfolio is actually populated
    valid_dates = weights[weights.sum(axis=1) > 0].index

    strategy_returns = run_backtest(weights, monthly_returns).loc[valid_dates]
    benchmark_returns = calculate_benchmark_returns(monthly_returns).loc[valid_dates]

    strategy_cum = calculate_cumulative(strategy_returns)
    benchmark_cum = calculate_cumulative(benchmark_returns)

    print(f"Backtest period: {valid_dates.min().date()} to {valid_dates.max().date()}")
    print(f"Strategy total return:  {strategy_cum.iloc[-1]:.1%}")
    print(f"Benchmark total return: {benchmark_cum.iloc[-1]:.1%}")

    plt.figure(figsize=(10, 5))
    plt.plot(strategy_cum.index, strategy_cum.values, label="Momentum Strategy")
    plt.plot(benchmark_cum.index, benchmark_cum.values, label="Equal-Weight Benchmark")
    plt.title("Cumulative Return: Momentum Strategy vs Benchmark")
    plt.ylabel("Cumulative Return")
    plt.legend()
    plt.tight_layout()
    plt.savefig("results/backtest_equity_curve.png")
    print("\nChart saved to results/backtest_equity_curve.png")