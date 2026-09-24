import pandas as pd

from config import IN_SAMPLE_END

from src.factors import load_prices, calculate_momentum, calculate_value_score, calculate_combined_score
from src.database import load_book_value
from src.portfolio import build_portfolio
from src.backtest import calculate_monthly_returns, run_backtest, calculate_benchmark_returns, calculate_turnover, apply_transaction_costs
from src.risk import summarize_risk

COST_BPS = 10  # one-way, in basis points -- see README for the reasoning


def compute_all_scores(prices: pd.DataFrame, book_value: pd.DataFrame) -> dict[str, pd.DataFrame]:
    momentum = calculate_momentum(prices)
    value = calculate_value_score(prices, book_value)
    combined = calculate_combined_score(momentum, value)
    return {"Momentum": momentum, "Value": value, "Combined": combined}


if __name__ == "__main__":
    prices = load_prices()
    book_value = load_book_value()
    monthly_returns = calculate_monthly_returns(prices)

    scores = compute_all_scores(prices, book_value)

    strategy_weights = {}
    strategy_returns_gross = {}
    for name, score_df in scores.items():
        w = build_portfolio(score_df, top_n=5)
        valid_dates = w[w.sum(axis=1) > 0].index
        strategy_weights[name] = w.loc[valid_dates]
        strategy_returns_gross[name] = run_backtest(w, monthly_returns).loc[valid_dates]

    # Same fairness rule used throughout this project: compare every
    # strategy over the same common dates.
    common_dates = strategy_returns_gross["Momentum"].index
    for r in strategy_returns_gross.values():
        common_dates = common_dates.intersection(r.index)

    # Keep only in-sample months, so newer data added for the
    # out-of-sample test cannot change these results.
    common_dates = common_dates[common_dates <= IN_SAMPLE_END]

    benchmark_returns = calculate_benchmark_returns(monthly_returns).loc[common_dates]

    print(f"Transaction cost assumption: {COST_BPS}bps one-way "
          f"(applied to both the buy and sell leg of each month's turnover)\n")

    results = []
    for name, gross in strategy_returns_gross.items():
        gross = gross.loc[common_dates]
        weights = strategy_weights[name].loc[common_dates]
        turnover = calculate_turnover(weights)
        net = apply_transaction_costs(gross, turnover, cost_bps=COST_BPS)

        gross_stats = summarize_risk(gross, f"{name} (gross)")
        net_stats = summarize_risk(net, f"{name} (net)")

        avg_turnover = turnover.mean()

        results.append({
            "strategy": name,
            "avg_monthly_turnover": avg_turnover,
            "gross_total_return": gross_stats["total_return"],
            "net_total_return": net_stats["total_return"],
            "gross_annualized_return": gross_stats["annualized_return"],
            "net_annualized_return": net_stats["annualized_return"],
            "gross_sharpe": gross_stats["sharpe_ratio"],
            "net_sharpe": net_stats["sharpe_ratio"],
        })

        print(f"{name}:")
        print(f"  Avg monthly turnover: {avg_turnover:.1%}")
        print(f"  Total return:  {gross_stats['total_return']:.1%} (gross) -> {net_stats['total_return']:.1%} (net)")
        print(f"  Sharpe ratio:  {gross_stats['sharpe_ratio']:.2f} (gross) -> {net_stats['sharpe_ratio']:.2f} (net)")
        print()

    benchmark_stats = summarize_risk(benchmark_returns, "Benchmark")
    print(f"Benchmark (for reference, costs not modeled -- see note below): "
          f"Sharpe {benchmark_stats['sharpe_ratio']:.2f}, total return {benchmark_stats['total_return']:.1%}")
    print("Note: the benchmark's own monthly rebalancing back to equal weight isn't cost-modeled here,")
    print("since it wasn't part of this project's original scope (see README) -- its turnover from price")
    print("drift alone each month is real but structurally much smaller than the active strategies' full")
    print("stock-swapping turnover, so this is a reasonable, disclosed simplification, not an oversight.")

    results_df = pd.DataFrame(results)
    results_df.to_csv("results/transaction_cost_impact.csv", index=False)
    print("\nSaved to results/transaction_cost_impact.csv")