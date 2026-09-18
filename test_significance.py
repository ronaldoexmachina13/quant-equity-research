import pandas as pd

from src.factors import load_prices, calculate_momentum, calculate_value_score, calculate_combined_score
from src.database import load_book_value
from src.portfolio import build_portfolio
from src.backtest import calculate_monthly_returns, run_backtest, calculate_benchmark_returns
from src.risk import bootstrap_sharpe_diff, sharpe_ratio


def compute_all_scores(prices: pd.DataFrame, book_value: pd.DataFrame) -> dict[str, pd.DataFrame]:
    momentum = calculate_momentum(prices)
    value = calculate_value_score(prices, book_value)
    combined = calculate_combined_score(momentum, value)
    return {"Momentum": momentum, "Value": value, "Combined": combined}


def backtest_strategy(score_df: pd.DataFrame, monthly_returns: pd.DataFrame, top_n: int = 5) -> pd.Series:
    weights = build_portfolio(score_df, top_n=top_n)
    valid_dates = weights[weights.sum(axis=1) > 0].index
    return run_backtest(weights, monthly_returns).loc[valid_dates]


if __name__ == "__main__":
    prices = load_prices()
    book_value = load_book_value()
    monthly_returns = calculate_monthly_returns(prices)

    scores = compute_all_scores(prices, book_value)
    strategy_returns = {}
    for name, score_df in scores.items():
        strategy_returns[name] = backtest_strategy(score_df, monthly_returns, top_n=5)

    # Same fairness rule as run_strategy_comparison.py: restrict every
    # strategy and the benchmark to the dates common to all three.
    common_dates = strategy_returns["Momentum"].index
    for r in strategy_returns.values():
        common_dates = common_dates.intersection(r.index)

    benchmark_returns = calculate_benchmark_returns(monthly_returns).loc[common_dates]
    strategy_returns = {name: r.loc[common_dates] for name, r in strategy_returns.items()}

    periods = {
        "Full period (2021-2024)": (common_dates.min(), common_dates.max()),
        "2021-2022": ("2021-01-01", "2022-12-31"),
        "2023-2024": ("2023-01-01", "2024-12-31"),
    }

    results = []
    for period_name, (start, end) in periods.items():
        bench_slice = benchmark_returns.loc[start:end]
        bench_sharpe = sharpe_ratio(bench_slice)
        for strat_name, r in strategy_returns.items():
            strat_slice = r.loc[start:end]
            strat_sharpe = sharpe_ratio(strat_slice)
            res = bootstrap_sharpe_diff(strat_slice, bench_slice, n_sims=5000, seed=42)

            results.append({
                "period": period_name,
                "strategy": strat_name,
                "strategy_sharpe": round(strat_sharpe, 3),
                "benchmark_sharpe": round(bench_sharpe, 3),
                "sharpe_diff": round(res["point_diff"], 3),
                "ci_90_lower": round(res["lower"], 3),
                "ci_90_upper": round(res["upper"], 3),
                "significant_at_90pct": res["significant"],
            })

            sig_label = "SIGNIFICANT" if res["significant"] else "not significant"
            print(f"{period_name:26s} | {strat_name:10s} vs Benchmark | "
                  f"Sharpe {strat_sharpe:.2f} vs {bench_sharpe:.2f} | "
                  f"diff {res['point_diff']:+.2f}, 90% CI [{res['lower']:+.2f}, {res['upper']:+.2f}] | {sig_label}")

    results_df = pd.DataFrame(results)
    results_df.to_csv("results/significance_test.csv", index=False)
    print("\nSaved to results/significance_test.csv")