"""
Transaction-cost sensitivity, as pre-registered in LIMITATIONS_PLAN.md
(Phase 1B, with Amendment 2).

Questions: at what one-way cost does each strategy's Sharpe fall to the
benchmark's, and how much does the benchmark's own rebalancing cost matter?

This is a labelled sensitivity. Everything is on the original flat 2%
risk-free basis and no strategy rule changes; only the cost assumption
varies. The headline 10 bps assumption is unchanged. No existing results
file is modified; the output goes to the new file results/cost_sensitivity.csv.

Turnover bases (Amendment 2, item 1):
- "target weights (existing)": calculate_turnover(), as in the published
  results. Counts only stocks swapped in or out.
- "drift-inclusive": calculate_turnover_with_drift(), which also counts the
  trades that bring held names back to equal weight after prices move.
- The benchmark is always charged on drift turnover, since rebalancing back
  to 1/17 after drift is the only trading it does.

Before anything is written, the existing basis at 0 and 10 bps must
reproduce transaction_cost_impact.csv and oos_summary.csv. If it does not,
the script stops.
"""
import os

import numpy as np
import pandas as pd

from config import IN_SAMPLE_END, OUT_OF_SAMPLE_START, OUT_OF_SAMPLE_END
from src.factors import load_prices
from src.database import load_book_value
from src.backtest import (
    calculate_monthly_returns,
    calculate_benchmark_returns,
    calculate_turnover,
    apply_transaction_costs,
    equal_weight_targets,
    calculate_turnover_with_drift,
    find_break_even_cost,
)
from src.risk import total_return, annualized_return, sharpe_ratio
from run_strategy_comparison import compute_all_scores, backtest_strategy_with_weights

OUTPUT_PATH = "results/cost_sensitivity.csv"

COSTS_BPS = [0, 5, 10, 25, 50]   # one-way, as registered
MAX_BPS = 50
TOP_N = 5                        # frozen portfolio size
STRATEGIES = ["Momentum", "Value", "Combined"]

EXISTING = "target weights (existing)"
DRIFT = "drift-inclusive"
BENCH_BASIS = "drift (equal-weight rebalance)"

IS_LABEL = "Full period (2021-2024)"
OOS_LABEL = "Out of sample (Jan 2025-Aug 2026)"


def build_inputs() -> dict:
    """
    Gross returns and turnover for every series, per period, rebuilt with
    the same functions and date rules as the published scripts.

    In sample, turnover is measured on the in-sample months only, so
    January 2021 is a purchase from cash (as in test_transaction_costs.py).
    Out of sample, turnover is measured over the whole history and then cut
    to the window, so January 2025 is a rebalance from the December 2024
    holdings (as in run_out_of_sample.py). The benchmark and the
    drift-inclusive basis follow the same rules.
    """
    prices = load_prices()
    book_value = load_book_value()
    monthly_returns = calculate_monthly_returns(prices)
    scores = compute_all_scores(prices, book_value)

    returns, weights = {}, {}
    for name, score_df in scores.items():
        returns[name], weights[name] = backtest_strategy_with_weights(score_df, monthly_returns, top_n=TOP_N)
    common = None
    for r in returns.values():
        common = r.index if common is None else common.intersection(r.index)

    is_dates = common[common <= IN_SAMPLE_END]
    history = common[common <= OUT_OF_SAMPLE_END]
    oos_dates = common[(common >= OUT_OF_SAMPLE_START) & (common <= OUT_OF_SAMPLE_END)]

    bench_gross = calculate_benchmark_returns(monthly_returns)
    bench_targets = equal_weight_targets(monthly_returns)

    # period label -> (dates reported, dates over which turnover is measured)
    windows = {IS_LABEL: (is_dates, is_dates), OOS_LABEL: (oos_dates, history)}

    inputs = {}
    for period, (dates, turnover_dates) in windows.items():
        series = []
        for name in STRATEGIES:
            w = weights[name].loc[turnover_dates]
            gross = returns[name].loc[dates]
            series.append((name, EXISTING, gross, calculate_turnover(w).loc[dates]))
            series.append((name, DRIFT, gross, calculate_turnover_with_drift(w, monthly_returns).loc[dates]))
        bench_turnover = calculate_turnover_with_drift(bench_targets.loc[turnover_dates], monthly_returns).loc[dates]
        series.append(("Benchmark", BENCH_BASIS, bench_gross.loc[dates], bench_turnover))
        inputs[period] = series
    return inputs


def compute_rows(inputs: dict) -> pd.DataFrame:
    """One row per period, strategy, turnover basis and cost level."""
    rows = []
    for period, series in inputs.items():
        _, _, bench_gross, bench_turnover = series[-1]
        break_evens = {
            (name, basis): find_break_even_cost(gross, turnover, bench_gross, bench_turnover, max_bps=MAX_BPS)
            for name, basis, gross, turnover in series[:-1]
        }
        for cost in COSTS_BPS:
            bench_sharpe = sharpe_ratio(apply_transaction_costs(bench_gross, bench_turnover, cost))
            for name, basis, gross, turnover in series:
                net = apply_transaction_costs(gross, turnover, cost)
                sharpe = sharpe_ratio(net)
                be = break_evens.get((name, basis))
                if be is None:
                    be_bps, be_note = np.nan, ""
                else:
                    be_bps = be["crossings_bps"][0] if be["crossings_bps"] else np.nan
                    be_note = be["note"]
                    if len(be["crossings_bps"]) > 1:
                        be_note += f" (crossings at {', '.join(f'{c:.2f}' for c in be['crossings_bps'])} bps)"
                rows.append({
                    "period": period,
                    "strategy": name,
                    "turnover_basis": basis,
                    "cost_bps": cost,
                    "avg_monthly_turnover": turnover.mean(),
                    "total_return": total_return(net),
                    "annualized_return": annualized_return(net),
                    "sharpe_ratio": sharpe,
                    "benchmark_sharpe_ratio": bench_sharpe,
                    "sharpe_diff_vs_benchmark": sharpe - bench_sharpe,
                    "break_even_bps": be_bps,
                    "break_even_note": be_note,
                })
    return pd.DataFrame(rows)


def reproduction_failures(results: pd.DataFrame) -> list[str]:
    """
    Compare the existing basis at 0 and 10 bps, and the benchmark's gross
    Sharpe, with the published files (saved at full precision, so 1e-9).
    """
    failures = []

    def value(period, strategy, basis, cost, column):
        row = results.query("period == @period and strategy == @strategy "
                            "and turnover_basis == @basis and cost_bps == @cost")
        return float(row[column].iloc[0])

    def check(label, recomputed, published, tol=1e-9):
        if abs(recomputed - published) > tol:
            failures.append(f"{label}: recomputed {recomputed!r}, published {published!r}")

    impact = pd.read_csv("results/transaction_cost_impact.csv", index_col="strategy")
    for name in STRATEGIES:
        for cost, prefix in [(0, "gross"), (10, "net")]:
            check(f"transaction_cost_impact.csv {name} {prefix}_total_return",
                  value(IS_LABEL, name, EXISTING, cost, "total_return"), impact.loc[name, f"{prefix}_total_return"])
            check(f"transaction_cost_impact.csv {name} {prefix}_annualized_return",
                  value(IS_LABEL, name, EXISTING, cost, "annualized_return"), impact.loc[name, f"{prefix}_annualized_return"])
            check(f"transaction_cost_impact.csv {name} {prefix}_sharpe",
                  value(IS_LABEL, name, EXISTING, cost, "sharpe_ratio"), impact.loc[name, f"{prefix}_sharpe"])
        check(f"transaction_cost_impact.csv {name} avg_monthly_turnover",
              value(IS_LABEL, name, EXISTING, 10, "avg_monthly_turnover"), impact.loc[name, "avg_monthly_turnover"])

    oos = pd.read_csv("results/oos_summary.csv", index_col="label")
    for name in STRATEGIES:
        check(f"oos_summary.csv {name} sharpe_ratio",
              value(OOS_LABEL, name, EXISTING, 0, "sharpe_ratio"), oos.loc[name, "sharpe_ratio"])
        check(f"oos_summary.csv {name} net_sharpe_ratio",
              value(OOS_LABEL, name, EXISTING, 10, "sharpe_ratio"), oos.loc[name, "net_sharpe_ratio"])
        check(f"oos_summary.csv {name} avg_monthly_turnover",
              value(OOS_LABEL, name, EXISTING, 10, "avg_monthly_turnover"), oos.loc[name, "avg_monthly_turnover"])

    full = pd.read_csv("results/strategy_comparison_full_period.csv", index_col="label")
    check("strategy_comparison_full_period.csv Benchmark sharpe_ratio",
          value(IS_LABEL, "Benchmark", BENCH_BASIS, 0, "sharpe_ratio"), full.loc["Benchmark", "sharpe_ratio"])
    check("oos_summary.csv Benchmark sharpe_ratio",
          value(OOS_LABEL, "Benchmark", BENCH_BASIS, 0, "sharpe_ratio"), oos.loc["Benchmark", "sharpe_ratio"])
    return failures


def print_summary(results: pd.DataFrame):
    """Sharpe grid, turnover, break-even costs and the registered reading rules."""
    for period in [IS_LABEL, OOS_LABEL]:
        sub = results[results["period"] == period]
        grid = sub.pivot_table(index=["strategy", "turnover_basis"], columns="cost_bps",
                               values="sharpe_ratio", sort=False)
        print(f"\n{period}: Sharpe ratio by one-way cost (bps), flat 2% risk-free rate")
        print(grid.round(3).to_string())

        turnover = sub[sub["cost_bps"] == 0].set_index(["strategy", "turnover_basis"])["avg_monthly_turnover"]
        print(f"\n{period}: average monthly turnover")
        print(turnover.map(lambda x: f"{x:.1%}").to_string())

        print(f"\n{period}: break-even cost (strategy Sharpe = benchmark Sharpe, both net of the same cost)")
        be = sub[(sub["cost_bps"] == 0) & (sub["strategy"] != "Benchmark")]
        for _, r in be.iterrows():
            shown = f"{r['break_even_bps']:.2f} bps" if pd.notna(r["break_even_bps"]) else "none"
            print(f"  {r['strategy']:9s} {r['turnover_basis']:26s} {shown:>11s}  ({r['break_even_note']})")

    print("\nReading rules (Amendment 2, item 6):")
    print("  (a) The headline 10 bps assumption on the existing basis is unchanged; costs are a sensitivity.")
    print("  (b) Both turnover bases are reported above.")
    print("  (c) The drift-inclusive basis is the like-for-like comparison with the benchmark.")
    print("  (d) Expectation check, drift-inclusive vs existing basis:")
    zero = results[(results["cost_bps"] == 0) & (results["strategy"] != "Benchmark")]
    for period in [IS_LABEL, OOS_LABEL]:
        for name in STRATEGIES:
            pair = zero[(zero["period"] == period) & (zero["strategy"] == name)].set_index("turnover_basis")
            higher = pair.loc[DRIFT, "avg_monthly_turnover"] > pair.loc[EXISTING, "avg_monthly_turnover"]
            be_existing, be_drift = pair.loc[EXISTING, "break_even_bps"], pair.loc[DRIFT, "break_even_bps"]
            if pd.notna(be_existing) and pd.notna(be_drift):
                be_text = f"break-even {be_existing:.2f} -> {be_drift:.2f} bps ({'lower' if be_drift < be_existing else 'NOT lower'})"
            else:
                be_text = f"break-even: {pair.loc[EXISTING, 'break_even_note']} | {pair.loc[DRIFT, 'break_even_note']}"
            print(f"      {period:34s} {name:9s} drift turnover higher: {'yes' if higher else 'NO'}; {be_text}")


def main():
    inputs = build_inputs()
    for period, series in inputs.items():
        dates = series[0][2].index
        print(f"{period:34s} {dates.min().date()} to {dates.max().date()} ({len(dates)} months)")

    results = compute_rows(inputs)

    failures = reproduction_failures(results)
    if failures:
        print("\nREPRODUCTION CHECK FAILED. Nothing was written. Mismatches:")
        for f in failures:
            print("  " + f)
        raise SystemExit(1)
    print("\nReproduction check passed: the existing basis at 0 and 10 bps matches "
          "transaction_cost_impact.csv and oos_summary.csv, and the benchmark's gross Sharpe matches.")

    if os.path.exists(OUTPUT_PATH):
        raise SystemExit(f"{OUTPUT_PATH} already exists. Not overwriting it; move it aside to rerun.")
    results.to_csv(OUTPUT_PATH, index=False)

    print_summary(results)
    print(f"\nSaved {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
