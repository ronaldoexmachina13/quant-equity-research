"""
Robustness grid, as pre-registered in LIMITATIONS_PLAN.md ("Phase 2
detailed design: robustness grid", with Amendment 5).

Question: does the conclusion "no active strategy beats the benchmark on a
risk-adjusted basis by a margin distinguishable from chance" survive
reasonable changes to portfolio size, rebalancing frequency and the
momentum lookback?

Grid (every cell is run and reported, in grid order; none is chosen,
ranked or promoted):
- Momentum and Combined: lookback 12-1, 9-1, 6-1 x top 3, 5, 8, 10 x
  monthly, quarterly = 24 cells each. Value: top N x rebalancing = 8 cells.
- Base case (the published headline, unchanged): top 5, monthly, 12-1.

Simulation:
- Monthly cells use the existing code path: build_portfolio() for the
  targets, run_backtest() for returns, calculate_benchmark_returns() for the
  benchmark.
- Quarterly cells refresh the selection in January, April, July and October
  and carry positions, drifting with prices, in between
  (hold_between_refreshes()). The benchmark in a quarterly cell is equal
  weight across all 17 names, refreshed on the same schedule.
- Every cell is simulated once, continuously, from January 2021 (a purchase
  from cash) to August 2026, then sliced into in sample (Jan 2021-Dec 2024)
  and out of sample (Jan 2025-Aug 2026). January 2025 therefore rebalances
  from the December 2024 holdings, and the quarterly schedule is unbroken.
- Net figures: 10 bps one-way on drift-inclusive turnover
  (calculate_turnover_with_drift()), for strategies and benchmark alike.
  Flat 2% risk-free rate.

The out-of-sample rows are a second look at data already seen. The
pre-registered out-of-sample test remains the official one, and its
published figures stand. No per-cell significance test is run.
"""
import os

import numpy as np
import pandas as pd

from config import IN_SAMPLE_END, OUT_OF_SAMPLE_START, OUT_OF_SAMPLE_END
from src.factors import load_prices, calculate_momentum, calculate_value_score, calculate_combined_score
from src.database import load_book_value
from src.portfolio import build_portfolio
from src.backtest import (
    calculate_monthly_returns,
    run_backtest,
    calculate_benchmark_returns,
    apply_transaction_costs,
    equal_weight_targets,
    calculate_turnover_with_drift,
    hold_between_refreshes,
)
from src.risk import annualized_return, annualized_volatility, sharpe_ratio, sortino_ratio, max_drawdown

GRID_PATH = "results/robustness_grid.csv"
SUMMARY_PATH = "results/robustness_grid_summary.csv"

STRATEGIES = ["Momentum", "Value", "Combined"]
LOOKBACKS = [12, 9, 6]
TOP_NS = [3, 5, 8, 10]
REBALANCES = ["monthly", "quarterly"]
COST_BPS = 10
SIM_START = "2021-01-01"   # first trading month for every cell (Jan 2021)
STABLE_SHARE = 0.75        # reading rule 3

IS_LABEL = "In sample (2021-2024)"
OOS_LABEL = "Out of sample (Jan 2025-Aug 2026)"
OOS_NOTE = "second look at data already seen; the pre-registered out-of-sample test remains the official one"
EXPECTED_MONTHS = {IS_LABEL: 48, OOS_LABEL: 20}
EXPECTED_CELLS = 56


def build_scores(prices: pd.DataFrame, book_value: pd.DataFrame) -> dict:
    """Score frames keyed by (strategy, lookback); Value's lookback is None."""
    value = calculate_value_score(prices, book_value)
    scores = {("Value", None): value}
    for lookback in LOOKBACKS:
        momentum = calculate_momentum(prices, lookback_months=lookback, skip_months=1)
        scores[("Momentum", lookback)] = momentum
        scores[("Combined", lookback)] = calculate_combined_score(momentum, value)
    return scores


def grid_cells() -> list[dict]:
    """The 56 cells, in fixed grid order (not ordered by any result)."""
    cells = []
    for strategy in STRATEGIES:
        lookbacks = [None] if strategy == "Value" else LOOKBACKS
        for lookback in lookbacks:
            for top_n in TOP_NS:
                for rebalance in REBALANCES:
                    cells.append({
                        "strategy": strategy,
                        "lookback": lookback,
                        "top_n": top_n,
                        "rebalance": rebalance,
                        "is_base_case": top_n == 5 and rebalance == "monthly" and lookback in (12, None),
                    })
    return cells


def simulate(targets: pd.DataFrame, monthly_returns: pd.DataFrame, rebalance: str) -> tuple[pd.DataFrame, pd.Series]:
    """
    Held weights and gross returns over the simulation dates. Monthly holds
    the targets themselves (the existing path); quarterly carries positions
    between refreshes.
    """
    held = targets if rebalance == "monthly" else hold_between_refreshes(targets, monthly_returns)
    return held, run_backtest(held, monthly_returns)


def build_benchmarks(monthly_returns: pd.DataFrame, sim_dates: pd.DatetimeIndex) -> dict:
    """Gross returns and drift turnover of the like-for-like benchmark, per frequency."""
    targets = equal_weight_targets(monthly_returns).loc[sim_dates]
    benchmarks = {}
    gross = calculate_benchmark_returns(monthly_returns).loc[sim_dates]
    benchmarks["monthly"] = (gross, calculate_turnover_with_drift(targets, monthly_returns))
    held, gross_q = simulate(targets, monthly_returns, "quarterly")
    benchmarks["quarterly"] = (gross_q, calculate_turnover_with_drift(held, monthly_returns))
    return benchmarks


def series_stats(gross: pd.Series, turnover: pd.Series) -> dict:
    """Gross and net (10 bps on drift-inclusive turnover) statistics for one period slice."""
    net = apply_transaction_costs(gross, turnover, cost_bps=COST_BPS)
    return {
        "gross": gross,
        "gross_sharpe": sharpe_ratio(gross),
        "net_sharpe": sharpe_ratio(net),
        "avg_turnover": turnover.mean(),
        "gross_annualized_return": annualized_return(gross),
        "net_annualized_return": annualized_return(net),
        "net_volatility": annualized_volatility(net),
        "net_max_drawdown": max_drawdown(net),
    }


def run_grid(scores: dict, monthly_returns: pd.DataFrame, sim_dates: pd.DatetimeIndex, periods: dict):
    """
    Returns (grid rows, failures). A cell without a full portfolio in every
    simulated month is recorded as a failure rather than silently shortened.
    """
    benchmarks = build_benchmarks(monthly_returns, sim_dates)
    rows, failures, gross_by_cell = [], [], {}
    for cell in grid_cells():
        targets = build_portfolio(scores[(cell["strategy"], cell["lookback"])].loc[sim_dates], top_n=cell["top_n"])
        empty = targets.index[targets.sum(axis=1) <= 0]
        if len(empty) > 0:
            failures.append(f"{cell}: no full portfolio in {len(empty)} month(s), e.g. {empty[0].date()}")
            continue
        held, gross = simulate(targets, monthly_returns, cell["rebalance"])
        turnover = calculate_turnover_with_drift(held, monthly_returns)
        bench_gross, bench_turnover = benchmarks[cell["rebalance"]]

        for period, dates in periods.items():
            s = series_stats(gross.loc[dates], turnover.loc[dates])
            b = series_stats(bench_gross.loc[dates], bench_turnover.loc[dates])
            gross_by_cell[(period, cell["strategy"], cell["lookback"], cell["top_n"], cell["rebalance"])] = (s["gross"], b["gross"])
            rows.append({
                "period": period,
                "period_note": OOS_NOTE if period == OOS_LABEL else "",
                "strategy": cell["strategy"],
                "top_n": cell["top_n"],
                "rebalance": cell["rebalance"],
                "lookback": f"{cell['lookback']}-1" if cell["lookback"] else "n/a",
                "is_base_case": cell["is_base_case"],
                "n_months": len(dates),
                "strategy_gross_sharpe": s["gross_sharpe"],
                "strategy_net_sharpe": s["net_sharpe"],
                "strategy_avg_turnover": s["avg_turnover"],
                "strategy_gross_annualized_return": s["gross_annualized_return"],
                "strategy_net_annualized_return": s["net_annualized_return"],
                "strategy_net_volatility": s["net_volatility"],
                "strategy_net_max_drawdown": s["net_max_drawdown"],
                "benchmark_gross_sharpe": b["gross_sharpe"],
                "benchmark_net_sharpe": b["net_sharpe"],
                "benchmark_avg_turnover": b["avg_turnover"],
                "benchmark_net_annualized_return": b["net_annualized_return"],
                "benchmark_net_volatility": b["net_volatility"],
                "benchmark_net_max_drawdown": b["net_max_drawdown"],
                "gross_sharpe_diff": s["gross_sharpe"] - b["gross_sharpe"],
                "net_sharpe_diff": s["net_sharpe"] - b["net_sharpe"],
                "cost_bps": COST_BPS,
                "turnover_basis": "drift-inclusive",
                "risk_free": "flat 2%",
            })
    return pd.DataFrame(rows), failures, gross_by_cell


def reproduction_failures(grid: pd.DataFrame, gross_by_cell: dict) -> list[str]:
    """Registered gates (design section and Amendment 5, item 1)."""
    failures = []

    def check(label, recomputed, published, tol=1e-9):
        if abs(recomputed - published) > tol:
            failures.append(f"{label}: recomputed {recomputed!r}, published {published!r}")

    def cell_row(period, strategy, top_n, rebalance, lookback):
        lb = f"{lookback}-1" if lookback else "n/a"
        return grid.query("period == @period and strategy == @strategy and top_n == @top_n "
                          "and rebalance == @rebalance and lookback == @lb").iloc[0]

    def base_lookback(strategy):
        return None if strategy == "Value" else 12

    # Gate: exactly 56 cells per period, over 48 and 20 months.
    for period, n in EXPECTED_MONTHS.items():
        sub = grid[grid["period"] == period]
        if len(sub) != EXPECTED_CELLS:
            failures.append(f"{period}: {len(sub)} cells, expected {EXPECTED_CELLS}")
        if not (sub["n_months"] == n).all():
            failures.append(f"{period}: not every cell covers {n} months")
    if failures:
        return failures

    # Gate: base cell gross Sharpe, strategies and monthly benchmark.
    published = {IS_LABEL: pd.read_csv("results/strategy_comparison_full_period.csv", index_col="label"),
                 OOS_LABEL: pd.read_csv("results/oos_summary.csv", index_col="label")}
    for period, table in published.items():
        for strategy in STRATEGIES:
            row = cell_row(period, strategy, 5, "monthly", base_lookback(strategy))
            check(f"{period} base {strategy} gross Sharpe", row["strategy_gross_sharpe"], table.loc[strategy, "sharpe_ratio"])
        check(f"{period} monthly benchmark gross Sharpe", row["benchmark_gross_sharpe"], table.loc["Benchmark", "sharpe_ratio"])

    # Gate: monthly top 8 at 12-1 reproduces strategy_comparison_concentration.csv.
    conc = pd.read_csv("results/strategy_comparison_concentration.csv", index_col="label")
    measures = {"annualized_return": annualized_return, "annualized_volatility": annualized_volatility,
                "sharpe_ratio": sharpe_ratio, "sortino_ratio": sortino_ratio, "max_drawdown": max_drawdown}
    for strategy in STRATEGIES:
        gross, bench = gross_by_cell[(IS_LABEL, strategy, base_lookback(strategy), 8, "monthly")]
        for column, fn in measures.items():
            check(f"concentration {strategy} (top-8) {column}", fn(gross), conc.loc[f"{strategy} (top-8)", column])
    for column, fn in measures.items():
        check(f"concentration Benchmark (top-8 dates) {column}", fn(bench), conc.loc["Benchmark (top-8 dates)", column])

    # Gate (Amendment 5): base cell net Sharpe at 10 bps, drift-inclusive basis, vs cost_sensitivity.csv.
    costs = pd.read_csv("results/cost_sensitivity.csv")
    cost_periods = {IS_LABEL: "Full period (2021-2024)", OOS_LABEL: "Out of sample (Jan 2025-Aug 2026)"}
    for period, cost_period in cost_periods.items():
        c10 = costs[(costs["period"] == cost_period) & (costs["cost_bps"] == COST_BPS)]
        for strategy in STRATEGIES:
            row = cell_row(period, strategy, 5, "monthly", base_lookback(strategy))
            published_net = c10[(c10["strategy"] == strategy) & (c10["turnover_basis"] == "drift-inclusive")]["sharpe_ratio"].iloc[0]
            check(f"{period} base {strategy} net Sharpe vs cost_sensitivity.csv", row["strategy_net_sharpe"], published_net)
        published_bench = c10[c10["strategy"] == "Benchmark"]["sharpe_ratio"].iloc[0]
        check(f"{period} monthly benchmark net Sharpe vs cost_sensitivity.csv", row["benchmark_net_sharpe"], published_bench)
    return failures


def eligible_names(scores: dict, strategy: str, dates: pd.DatetimeIndex) -> tuple[int, int]:
    """Smallest and largest number of names with a valid score in any month, over the strategy's score frames."""
    counts = [frame.loc[dates].notna().sum(axis=1) for (name, _), frame in scores.items() if name == strategy]
    all_counts = pd.concat(counts)
    return int(all_counts.min()), int(all_counts.max())


def build_summary(grid: pd.DataFrame, scores: dict, periods: dict) -> pd.DataFrame:
    """
    One row per period and strategy (reading rule 3 and Amendment 5, item 2).
    A difference of exactly zero counts as not positive; the base cell is
    included and always matches itself; a zero base-case difference makes
    stability undefined.
    """
    rows = []
    for period, dates in periods.items():
        for strategy in STRATEGIES:
            sub = grid[(grid["period"] == period) & (grid["strategy"] == strategy)]
            diffs = sub["net_sharpe_diff"]
            base = sub[sub["is_base_case"]]["net_sharpe_diff"].iloc[0]
            positive = diffs > 0
            differs = positive != (base > 0)
            share_differs = float(differs.mean())
            if base == 0:
                stability = "undefined"
            else:
                stability = "stable" if 1 - share_differs >= STABLE_SHARE else "fragile"
            low, high = eligible_names(scores, strategy, dates)
            rows.append({
                "period": period,
                "strategy": strategy,
                "n_cells": len(sub),
                "share_positive_net_diff": float(positive.mean()),
                "median_net_diff": float(diffs.median()),
                "min_net_diff": float(diffs.min()),
                "max_net_diff": float(diffs.max()),
                "base_case_net_diff": float(base),
                "share_sign_differs_from_base": share_differs,
                "stability": stability,
                "eligible_names_min": low,
                "eligible_names_max": high,
            })
    summary = pd.DataFrame(rows)
    medians = summary.pivot(index="strategy", columns="period", values="median_net_diff")
    consistent = {s: bool((medians.loc[s, IS_LABEL] > 0) == (medians.loc[s, OOS_LABEL] > 0)) for s in STRATEGIES}
    summary["consistent_across_periods"] = summary["strategy"].map(consistent)
    return summary


def print_expectations(grid: pd.DataFrame):
    """
    Reading rule 5, checked factually. Momentum is printed separately from
    Value and Combined (Amendment 5, item 3). Values are listed in grid
    order (top N ascending; monthly then quarterly), not by result.
    """
    print("\nExpectation 5a: the difference moves towards zero as the portfolio size grows.")
    print("  Applies to Momentum (Amendment 5, item 3). Net Sharpe difference at top 3, 5, 8, 10:")
    for period in EXPECTED_MONTHS:
        for lookback in ["12-1", "9-1", "6-1"]:
            for rebalance in REBALANCES:
                sub = grid[(grid["period"] == period) & (grid["strategy"] == "Momentum")
                           & (grid["lookback"] == lookback) & (grid["rebalance"] == rebalance)]
                d = sub.set_index("top_n").loc[TOP_NS, "net_sharpe_diff"]
                closer = abs(d.loc[10]) < abs(d.loc[3])
                monotonic = bool((np.diff(np.abs(d.values)) < 0).all())
                print(f"    {period:34s} {lookback:4s} {rebalance:9s} "
                      f"{'  '.join(f'{v:+.3f}' for v in d.values)}   |top 10| < |top 3|: {'yes' if closer else 'no'}; "
                      f"shrinks at every step: {'yes' if monotonic else 'no'}")
    print("  Value and Combined (not expected to converge: 14 to 16 eligible names vs 17 in the benchmark):")
    for period in EXPECTED_MONTHS:
        for strategy in ["Value", "Combined"]:
            lookbacks = ["n/a"] if strategy == "Value" else ["12-1", "9-1", "6-1"]
            for lookback in lookbacks:
                for rebalance in REBALANCES:
                    sub = grid[(grid["period"] == period) & (grid["strategy"] == strategy)
                               & (grid["lookback"] == lookback) & (grid["rebalance"] == rebalance)]
                    d = sub.set_index("top_n").loc[TOP_NS, "net_sharpe_diff"]
                    print(f"    {period:34s} {strategy:9s} {lookback:4s} {rebalance:9s} "
                          f"{'  '.join(f'{v:+.3f}' for v in d.values)}")

    print("\nExpectation 5b: quarterly rebalancing lowers turnover and helps net Sharpe for Momentum and")
    print("  Combined more than for Value. Paired cells (same strategy, top N and lookback), quarterly minus monthly:")

    def paired(period, strategy):
        sub = grid[(grid["period"] == period) & (grid["strategy"] == strategy)]
        m = sub[sub["rebalance"] == "monthly"].set_index(["top_n", "lookback"])
        q = sub[sub["rebalance"] == "quarterly"].set_index(["top_n", "lookback"])
        turnover_lower = float((q["strategy_avg_turnover"] < m["strategy_avg_turnover"]).mean())
        net_change = (q["strategy_net_sharpe"] - m["strategy_net_sharpe"]).median()
        return turnover_lower, net_change, len(m)

    for group in [["Momentum"], ["Value", "Combined"]]:
        print(f"  {' and '.join(group)}:")
        for period in EXPECTED_MONTHS:
            for strategy in group:
                lower, change, n = paired(period, strategy)
                print(f"    {period:34s} {strategy:9s} turnover lower in {lower:.0%} of {n} pairs; "
                      f"median change in net Sharpe {change:+.3f}")


def main():
    for path in [GRID_PATH, SUMMARY_PATH]:
        if os.path.exists(path):
            raise SystemExit(f"{path} already exists. Not overwriting it; move it aside to rerun.")

    prices = load_prices()
    book_value = load_book_value()
    monthly_returns = calculate_monthly_returns(prices)
    scores = build_scores(prices, book_value)

    all_dates = monthly_returns.index
    sim_dates = all_dates[(all_dates >= SIM_START) & (all_dates <= OUT_OF_SAMPLE_END)]
    periods = {IS_LABEL: sim_dates[sim_dates <= IN_SAMPLE_END],
               OOS_LABEL: sim_dates[sim_dates >= OUT_OF_SAMPLE_START]}
    for period, dates in periods.items():
        print(f"{period:34s} {dates.min().date()} to {dates.max().date()} ({len(dates)} months)")

    grid, failures, gross_by_cell = run_grid(scores, monthly_returns, sim_dates, periods)
    if not failures:
        failures = reproduction_failures(grid, gross_by_cell)
    if failures:
        print("\nREPRODUCTION CHECK FAILED. Nothing was written. Mismatches:")
        for f in failures:
            print("  " + f)
        raise SystemExit(1)
    print("\nReproduction gates passed: 56 cells per period over 48 and 20 months; base cell gross Sharpe "
          "matches strategy_comparison_full_period.csv and oos_summary.csv; monthly top 8 at 12-1 matches "
          "strategy_comparison_concentration.csv; base cell net Sharpe at 10 bps matches cost_sensitivity.csv.")

    summary = build_summary(grid, scores, periods)
    grid.to_csv(GRID_PATH, index=False, lineterminator="\n")
    summary.to_csv(SUMMARY_PATH, index=False, lineterminator="\n")

    with pd.option_context("display.width", 220, "display.max_columns", 20):
        print("\nSummary (net Sharpe difference vs like-for-like benchmark, 10 bps, drift-inclusive, flat 2%):")
        print(summary.round(3).to_string(index=False))

    print("\nReading rules (Phase 2 design):")
    print("  1. The headline specification (top 5, monthly, 12-1) is not replaced by any cell.")
    print("  2. No per-cell significance test is run; individual cells are not read.")
    print(f"  3. Stable = sign matches the base case in at least {STABLE_SHARE:.0%} of cells; consistent = "
          "in-sample and out-of-sample medians have the same sign.")
    print(f"  4. Every cell is reported in {GRID_PATH}.")
    print_expectations(grid)
    print(f"\nOut-of-sample rows: {OOS_NOTE}.")
    print(f"\nSaved {GRID_PATH} and {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
