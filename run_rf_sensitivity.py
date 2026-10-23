"""
Risk-free rate sensitivity, as pre-registered in LIMITATIONS_PLAN.md
(Phase 1A, with Amendment 1).

Question: how much do the Sharpe ratios, Sortino ratios and alphas change
when the flat 2% risk-free rate is replaced by the actual 3-month Treasury
bill rate, month by month?

This is a labelled sensitivity. It changes no strategy rule and no holding:
the strategies are rebuilt with the same functions as
run_strategy_comparison.py and run_out_of_sample.py, and only the hurdle
rate is changed. No existing results file is modified; the output goes to
the new file results/rf_sensitivity.csv.

Data: FRED series TB3MS (3-month Treasury bill, secondary market rate,
monthly average, percent per annum). The raw download is saved once to
results/tbill_3m_monthly.csv and reused on later runs, never overwritten.

Before anything is written, the flat-2% figures recomputed here must
reproduce the published CSVs. If they do not, the script stops.
"""
import os

import numpy as np
import pandas as pd
import requests

from config import IN_SAMPLE_END, OUT_OF_SAMPLE_START, OUT_OF_SAMPLE_END
from src.factors import load_prices
from src.database import load_book_value
from src.backtest import calculate_monthly_returns, calculate_benchmark_returns
from src.risk import (
    sharpe_ratio,
    sortino_ratio,
    alpha_regression,
    tbill_yield_to_monthly,
    annualized_risk_free,
    sharpe_ratio_tbill,
    sortino_ratio_tbill,
    alpha_regression_tbill,
)
from run_strategy_comparison import compute_all_scores, backtest_strategy

TBILL_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=TB3MS"
TBILL_PATH = "results/tbill_3m_monthly.csv"
OUTPUT_PATH = "results/rf_sensitivity.csv"

FLAT_RF = 0.02         # the frozen assumption used everywhere else
TOP_N = 5              # frozen portfolio size
T_SIGNIFICANT = 1.65   # project's 90% level (Amendment 1, item 1)
T_INFO = 1.96          # 95% level, printed as information only

STRATEGIES = ["Momentum", "Value", "Combined"]
ALL_SERIES = STRATEGIES + ["Benchmark"]
ALPHA_METRICS = ["alpha", "alpha_tstat", "alpha_pvalue", "beta"]

OOS_LABEL = "Out of sample (Jan 2025-Aug 2026)"


def load_tbill_yields() -> pd.Series:
    """
    TB3MS in percent per annum, indexed by FRED's observation date (the
    first day of each month). Downloads and saves the raw file only if it
    is not already in results/, so a rerun uses the same data.
    """
    if not os.path.exists(TBILL_PATH):
        response = requests.get(TBILL_URL, timeout=30)
        response.raise_for_status()
        if "TB3MS" not in response.text.splitlines()[0]:
            raise ValueError(f"Unexpected FRED response header: {response.text[:200]!r}")
        with open(TBILL_PATH, "xb") as f:  # "x": fail rather than overwrite
            f.write(response.content)
        print(f"Downloaded TB3MS from FRED and saved the raw file to {TBILL_PATH}")
    else:
        print(f"Using the saved TB3MS file {TBILL_PATH}")

    raw = pd.read_csv(TBILL_PATH)
    dates = pd.to_datetime(raw.iloc[:, 0])
    # FRED marks a missing observation as "."; it becomes NaN and is caught
    # by the coverage check in rf_on_return_dates().
    return pd.Series(pd.to_numeric(raw["TB3MS"], errors="coerce").values, index=dates, name="TB3MS")


def rf_on_return_dates(tbill_yields: pd.Series, dates: pd.DatetimeIndex) -> pd.Series:
    """
    Monthly risk-free rate (decimal) for each month-end return date.

    Registered convention (LIMITATIONS_PLAN.md, Phase 1A and Amendment 1,
    item 7): the TB3MS average for month t is applied to the return earned
    during month t. The rate is a hurdle, not a signal: it never affects
    which stocks are held, so this is not look-ahead.

    FRED dates each month on its first day and the returns are dated at
    month end, so the two are matched by calendar month.
    """
    by_month = tbill_yields.copy()
    by_month.index = by_month.index.to_period("M")
    yields = by_month.reindex(dates.to_period("M"))
    if yields.isna().any():
        missing = [str(p) for p in yields.index[yields.isna()]]
        raise ValueError(f"TB3MS has no value for {missing}. Stopping: every month needs a rate.")
    return pd.Series(tbill_yield_to_monthly(yields).values, index=dates, name="rf_monthly")


def build_return_series() -> tuple[dict, pd.Series, pd.DatetimeIndex, pd.DatetimeIndex]:
    """
    Rebuild the monthly return series exactly as the published scripts do:
    each strategy over the whole history, restricted to the dates common
    to all three, then split into the in-sample and out-of-sample windows.
    """
    prices = load_prices()
    book_value = load_book_value()
    monthly_returns = calculate_monthly_returns(prices)
    scores = compute_all_scores(prices, book_value)

    returns = {name: backtest_strategy(score_df, monthly_returns, top_n=TOP_N)
               for name, score_df in scores.items()}
    common = None
    for r in returns.values():
        common = r.index if common is None else common.intersection(r.index)

    is_dates = common[common <= IN_SAMPLE_END]
    oos_dates = common[(common >= OUT_OF_SAMPLE_START) & (common <= OUT_OF_SAMPLE_END)]
    returns["Benchmark"] = calculate_benchmark_returns(monthly_returns).loc[common]
    return returns, returns["Benchmark"], is_dates, oos_dates


def define_periods(is_dates: pd.DatetimeIndex, oos_dates: pd.DatetimeIndex) -> dict:
    """The four pre-registered evaluation windows, as sets of return dates."""
    return {
        "Full period (2021-2024)": is_dates,
        "2021-2022": is_dates[(is_dates >= "2021-01-01") & (is_dates <= "2022-12-31")],
        "2023-2024": is_dates[(is_dates >= "2023-01-01") & (is_dates <= "2024-12-31")],
        OOS_LABEL: oos_dates,
    }


def compute_rows(returns: dict, periods: dict, rf_monthly: pd.Series) -> pd.DataFrame:
    """
    One row per (period, strategy, metric), with the flat-2% value from the
    published functions and the T-bill value from the *_tbill functions.
    The benchmark gets Sharpe and Sortino only (Amendment 1, item 4), and
    each period gets a "Risk-free" row with the annualized rate (item 5).
    """
    rows = []
    for period, dates in periods.items():
        bench = returns["Benchmark"].loc[dates]
        for name in ALL_SERIES:
            r = returns[name].loc[dates]
            rows.append((period, name, "sharpe_ratio", sharpe_ratio(r, FLAT_RF), sharpe_ratio_tbill(r, rf_monthly)))
            rows.append((period, name, "sortino_ratio", sortino_ratio(r, FLAT_RF), sortino_ratio_tbill(r, rf_monthly)))
            if name == "Benchmark":
                continue
            flat = alpha_regression(r, bench, FLAT_RF)
            tbill = alpha_regression_tbill(r, bench, rf_monthly)
            for metric in ALPHA_METRICS:
                rows.append((period, name, metric, flat[metric], tbill[metric]))
        rows.append((period, "Risk-free", "annualized_rate", FLAT_RF, annualized_risk_free(rf_monthly.loc[dates])))
    return pd.DataFrame(rows, columns=["period", "strategy", "metric", "flat_2pct", "tbill"])


def reproduction_failures(results: pd.DataFrame, returns: dict, periods: dict) -> list[str]:
    """
    Compare the flat-2% column with the published CSVs. Returns a list of
    mismatches (empty if everything reproduces).

    The strategy-comparison and out-of-sample files are saved at full
    precision and are compared to 1e-9; alpha_significance.csv was saved
    rounded, so it is compared after the same rounding.
    """
    failures = []

    def value(period, strategy, metric):
        row = results.query("period == @period and strategy == @strategy and metric == @metric")
        return float(row["flat_2pct"].iloc[0])

    def check(label, recomputed, published, tol=1e-9):
        if abs(recomputed - published) > tol:
            failures.append(f"{label}: recomputed {recomputed!r}, published {published!r}")

    published_files = {
        "Full period (2021-2024)": "results/strategy_comparison_full_period.csv",
        "2021-2022": "results/strategy_comparison_2021_2022.csv",
        "2023-2024": "results/strategy_comparison_2023_2024.csv",
        OOS_LABEL: "results/oos_summary.csv",
    }
    for period, path in published_files.items():
        published = pd.read_csv(path, index_col="label")
        for name in ALL_SERIES:
            for metric in ["sharpe_ratio", "sortino_ratio"]:
                check(f"{path} {name} {metric}", value(period, name, metric), published.loc[name, metric])

    oos = pd.read_csv("results/oos_summary.csv", index_col="label")
    for name in STRATEGIES:
        check(f"oos_summary.csv {name} alpha_ols", value(OOS_LABEL, name, "alpha"), oos.loc[name, "alpha_ols"])
        check(f"oos_summary.csv {name} alpha_tstat", value(OOS_LABEL, name, "alpha_tstat"), oos.loc[name, "alpha_tstat"])

    alpha_sig = pd.read_csv("results/alpha_significance.csv")
    for _, row in alpha_sig.iterrows():
        for metric, decimals in [("alpha", 4), ("alpha_tstat", 2), ("alpha_pvalue", 3), ("beta", 3)]:
            recomputed = round(value(row["period"], row["strategy"], metric), decimals)
            check(f"alpha_significance.csv {row['period']} {row['strategy']} {metric}", recomputed, row[metric], tol=1e-12)

    # The OOS monthly returns must also match the saved series, month by month.
    saved = pd.read_csv("results/oos_monthly_returns.csv", index_col="date", parse_dates=True)
    for name in ALL_SERIES:
        rebuilt = returns[name].loc[periods[OOS_LABEL]]
        if len(rebuilt) != len(saved) or np.abs(rebuilt.values - saved[name].values).max() > 1e-12:
            failures.append(f"oos_monthly_returns.csv {name}: rebuilt series differs from the saved one")
    return failures


def ranking(results: pd.DataFrame, period: str, metric: str, column: str, names: list) -> list[str]:
    """Names ordered from highest to lowest on one metric in one period."""
    sub = results.query("period == @period and metric == @metric and strategy in @names")
    return list(sub.sort_values(column, ascending=False)["strategy"])


def print_reading_rules(results: pd.DataFrame, periods: dict):
    """The three pre-registered reading rules (Phase 1A, with Amendment 1)."""
    print("\nAnnualized risk-free rate by period (flat vs T-bill):")
    for period in periods:
        rf = results.query("period == @period and strategy == 'Risk-free'").iloc[0]
        print(f"  {period:36s} {rf['flat_2pct']:.2%} vs {rf['tbill']:.2%}")

    print("\nRule (a): does the benchmark still have the highest out-of-sample Sharpe?")
    for column in ["flat_2pct", "tbill"]:
        order = ranking(results, OOS_LABEL, "sharpe_ratio", column, ALL_SERIES)
        print(f"  {column:9s} {' > '.join(order)}  -> benchmark highest: {'yes' if order[0] == 'Benchmark' else 'NO'}")

    print("\nRule (b): ranking within each period, flat 2% vs T-bill:")
    for period in periods:
        for metric, names in [("sharpe_ratio", ALL_SERIES), ("sortino_ratio", ALL_SERIES), ("alpha", STRATEGIES)]:
            flat = ranking(results, period, metric, "flat_2pct", names)
            tbill = ranking(results, period, metric, "tbill", names)
            if flat == tbill:
                print(f"  {period:36s} {metric:14s} unchanged: {' > '.join(flat)}")
            else:
                print(f"  {period:36s} {metric:14s} CHANGED: flat {' > '.join(flat)} | T-bill {' > '.join(tbill)}")

    print(f"\nRule (c): alpha significant at the 90% level if |t| > {T_SIGNIFICANT}:")
    t_rows = results.query("metric == 'alpha_tstat'")
    for column in ["flat_2pct", "tbill"]:
        hits = t_rows[t_rows[column].abs() > T_SIGNIFICANT]
        largest = t_rows.loc[t_rows[column].abs().idxmax()]
        print(f"  {column:9s} significant: {len(hits)} of {len(t_rows)}; largest |t| = {abs(largest[column]):.2f} "
              f"({largest['strategy']}, {largest['period']})")
        for _, h in hits.iterrows():
            print(f"            {h['strategy']}, {h['period']}: t = {h[column]:.2f}")
    info = t_rows[t_rows["tbill"].abs() > T_INFO]
    print(f"  Information only: |t| > {T_INFO} under T-bill rates in {len(info)} of {len(t_rows)} cases.")


def main():
    tbill_yields = load_tbill_yields()
    returns, _, is_dates, oos_dates = build_return_series()
    periods = define_periods(is_dates, oos_dates)
    rf_monthly = rf_on_return_dates(tbill_yields, is_dates.union(oos_dates))

    for period, dates in periods.items():
        print(f"{period:36s} {dates.min().date()} to {dates.max().date()} ({len(dates)} months)")

    results = compute_rows(returns, periods, rf_monthly)

    failures = reproduction_failures(results, returns, periods)
    if failures:
        print("\nREPRODUCTION CHECK FAILED. Nothing was written. Mismatches:")
        for f in failures:
            print("  " + f)
        raise SystemExit(1)
    print("\nReproduction check passed: the flat-2% column matches every published figure checked.")

    if os.path.exists(OUTPUT_PATH):
        raise SystemExit(f"{OUTPUT_PATH} already exists. Not overwriting it; move it aside to rerun.")
    results.to_csv(OUTPUT_PATH, index=False)

    shown = results.copy()
    shown["change"] = shown["tbill"] - shown["flat_2pct"]
    with pd.option_context("display.width", 200, "display.max_rows", 200):
        print("\n" + shown.round(4).to_string(index=False))

    print_reading_rules(results, periods)
    print(f"\nSaved {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
