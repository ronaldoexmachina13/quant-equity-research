"""
Out-of-sample test, as pre-registered in OUT_OF_SAMPLE_PLAN.md.

Runs the frozen strategy rules (unchanged since the in-sample study) on
January 2025 to August 2026, a period none of the strategies was built or
examined on, and reports it separately from the 2021-2024 results.

Nothing in this script changes a strategy rule. It reuses the same
signal, portfolio and backtest functions as run_strategy_comparison.py and
only restricts the evaluation window. Outputs go to new files prefixed
"oos_", so the in-sample results files are never touched.
"""
import pandas as pd

from config import OUT_OF_SAMPLE_START, OUT_OF_SAMPLE_END
from src.factors import load_prices
from src.database import load_book_value
from src.backtest import (
    calculate_monthly_returns,
    calculate_benchmark_returns,
    calculate_turnover,
    apply_transaction_costs,
)
from src.risk import summarize_risk, alpha_regression, bootstrap_sharpe_diff, sharpe_ratio
from run_strategy_comparison import compute_all_scores, backtest_strategy_with_weights

COST_BPS = 10          # same one-way cost as test_transaction_costs.py
TOP_N = 5              # frozen portfolio size
BOOTSTRAP_SEED = 42    # same seed as the in-sample significance test

# Which in-sample alpha each pre-registered finding is checked against
# (OUT_OF_SAMPLE_PLAN.md, Amendment 1: same sign required).
FINDINGS_TO_CHECK = {
    "Value": "Full period (2021-2024)",   # Value's full-period alpha
    "Combined": "2023-2024",              # Combined's 2023-2024 regime result
}


def main():
    prices = load_prices()
    book_value = load_book_value()
    monthly_returns = calculate_monthly_returns(prices)
    scores = compute_all_scores(prices, book_value)

    # Build each strategy over the WHOLE history, then cut out the
    # out-of-sample months. Building first and cutting second matters for
    # turnover: January 2025 is a rebalance from the December 2024
    # portfolio, not a fresh start from cash, so its trading cost must be
    # measured against the holdings that were actually in place.
    returns, weights = {}, {}
    for name, score_df in scores.items():
        returns[name], weights[name] = backtest_strategy_with_weights(score_df, monthly_returns, top_n=TOP_N)

    common = None
    for r in returns.values():
        common = r.index if common is None else common.intersection(r.index)
    oos_dates = common[(common >= OUT_OF_SAMPLE_START) & (common <= OUT_OF_SAMPLE_END)]

    benchmark = calculate_benchmark_returns(monthly_returns).loc[oos_dates]

    print(f"OUT-OF-SAMPLE period: {oos_dates.min().date()} to {oos_dates.max().date()} "
          f"({len(oos_dates)} months). Strategy rules unchanged from the in-sample study.\n")

    rows, monthly = [], {"Benchmark": benchmark}
    for name in ["Momentum", "Value", "Combined"]:
        gross = returns[name].loc[oos_dates]
        monthly[name] = gross

        stats = summarize_risk(gross, name, benchmark_returns=benchmark)
        reg = alpha_regression(gross, benchmark)
        diff = bootstrap_sharpe_diff(gross, benchmark, n_sims=5000, seed=BOOTSTRAP_SEED)

        turnover_all = calculate_turnover(weights[name].loc[common[common <= OUT_OF_SAMPLE_END]])
        turnover = turnover_all.loc[oos_dates]
        net = apply_transaction_costs(gross, turnover, cost_bps=COST_BPS)

        stats.update({
            "alpha_ols": reg["alpha"],
            "alpha_tstat": reg["alpha_tstat"],
            "alpha_pvalue": reg["alpha_pvalue"],
            "r_squared": reg["r_squared"],
            "sharpe_diff_vs_benchmark": diff["point_diff"],
            "sharpe_diff_ci_lower": diff["lower"],
            "sharpe_diff_ci_upper": diff["upper"],
            "sharpe_diff_significant": diff["significant"],
            "avg_monthly_turnover": turnover.mean(),
            "net_sharpe_ratio": sharpe_ratio(net),
        })
        rows.append(stats)

    rows.append(summarize_risk(benchmark, "Benchmark", benchmark_returns=benchmark))
    summary = pd.DataFrame(rows).set_index("label")
    summary.to_csv("results/oos_summary.csv")
    pd.DataFrame(monthly)[["Momentum", "Value", "Combined", "Benchmark"]].to_csv(
        "results/oos_monthly_returns.csv", index_label="date")

    shown = ["total_return", "annualized_return", "annualized_volatility", "sharpe_ratio",
             "sortino_ratio", "max_drawdown", "beta", "alpha", "alpha_tstat", "net_sharpe_ratio"]
    print(summary[shown].round(3).to_string())
    print("\nSharpe difference vs benchmark (paired bootstrap, 5,000 resamples, 90% CI):")
    for name in ["Momentum", "Value", "Combined"]:
        r = summary.loc[name]
        verdict = "significant" if r["sharpe_diff_significant"] else "not significant"
        print(f"  {name:<9} {r['sharpe_diff_vs_benchmark']:+.2f}  "
              f"[{r['sharpe_diff_ci_lower']:+.2f}, {r['sharpe_diff_ci_upper']:+.2f}]  {verdict}")

    # ---- Pre-registered reading rules (OUT_OF_SAMPLE_PLAN.md) ----
    print("\nPre-registered reading rules:")
    bench_sharpe = summary.loc["Benchmark", "sharpe_ratio"]
    for name in ["Momentum", "Value", "Combined"]:
        s = summary.loc[name, "sharpe_ratio"]
        print(f"  Benchmark Sharpe >= {name} Sharpe: {bench_sharpe:.2f} vs {s:.2f} -> "
              f"{'yes' if bench_sharpe >= s else 'no'}")

    in_sample = pd.read_csv("results/alpha_significance.csv")
    for name, period in FINDINGS_TO_CHECK.items():
        is_alpha = in_sample.query("strategy == @name and period == @period")["alpha"].iloc[0]
        oos_alpha = summary.loc[name, "alpha_ols"]  # same OLS alpha as the in-sample file
        same_sign = (is_alpha > 0) == (oos_alpha > 0) and oos_alpha != 0
        print(f"  {name}: in-sample alpha ({period}) {is_alpha:+.1%}, out-of-sample alpha {oos_alpha:+.1%} -> "
              f"{'SUPPORTED (same sign)' if same_sign else 'NOT SUPPORTED'}")
    print("  With about 20 months, direction is tested, not significance (see plan).")

    print("\nSaved results/oos_summary.csv and results/oos_monthly_returns.csv")


if __name__ == "__main__":
    main()
