import pandas as pd
import matplotlib.pyplot as plt

from src.factors import load_prices, calculate_momentum
from src.portfolio import build_portfolio
from src.risk import summarize_risk


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
    strategy_stats = summarize_risk(strategy_returns, "Momentum Strategy")
    benchmark_stats = summarize_risk(benchmark_returns, "Equal-Weight Benchmark")

    print("\n--- Risk-Adjusted Comparison ---")
    for stats in [strategy_stats, benchmark_stats]:
        print(f"\n{stats['label']}:")
        print(f"  Annualized Return:     {stats['annualized_return']:.1%}")
        print(f"  Annualized Volatility: {stats['annualized_volatility']:.1%}")
        print(f"  Sharpe Ratio:          {stats['sharpe_ratio']:.2f}")
        print(f"  Max Drawdown:          {stats['max_drawdown']:.1%}")
    