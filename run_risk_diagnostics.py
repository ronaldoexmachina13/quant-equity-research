"""
Risk diagnostics, as pre-registered in LIMITATIONS_PLAN.md ("Phase 2B
detailed design: risk diagnostics").

Descriptive tail-risk and consistency measures on the published monthly
gross returns of Momentum, Value, Combined and the monthly equal-weight
benchmark, in the base specification (top 5, monthly, 12-1). No hypothesis
is tested and no strategy or published result changes.

- Historical VaR and Expected Shortfall at 95% (positive losses), with 90%
  bootstrap intervals (5,000 resamples, seed 42), for in sample (48 months)
  and the full 68 months. Not for the 20 out-of-sample months alone, where
  the 5% tail holds a single observation.
- Hit rates (share of positive months; share of months beating the
  benchmark, strategies only), worst and best month, number of months: in
  sample, out of sample and the full 68 months.
- Drawdown (underwater) series: in sample from 1.0 at the end of December
  2020, out of sample from 1.0 at the end of December 2024.

Before anything is written, the returns must reproduce the published Sharpe
ratios and out-of-sample monthly returns, and the drawdown series must
reproduce the published maximum drawdowns. If not, the script stops.
"""
import os

import numpy as np
import pandas as pd

from src.risk import (
    sharpe_ratio,
    historical_var,
    expected_shortfall,
    bootstrap_statistic_ci,
    hit_rate,
    hit_rate_vs_benchmark,
    drawdown_series,
)
from run_rf_sensitivity import build_return_series

DIAGNOSTICS_PATH = "results/risk_diagnostics.csv"
DRAWDOWN_PATH = "results/drawdown_series.csv"

SERIES = ["Momentum", "Value", "Combined", "Benchmark"]  # fixed order, not by result
STRATEGIES = SERIES[:3]
LEVEL = 0.95
N_SIMS = 5000
CI = 0.90
# Same seed for every series. The resampled month positions depend only on
# the seed and the series length, so within a period every strategy and the
# benchmark are resampled on the same months: the intervals are paired.
SEED = 42

IS_LABEL = "In sample (2021-2024)"
OOS_LABEL = "Out of sample (Jan 2025-Aug 2026)"
FULL_LABEL = "Full period (Jan 2021-Aug 2026)"
EXPECTED_MONTHS = {IS_LABEL: 48, OOS_LABEL: 20, FULL_LABEL: 68}
VAR_PERIODS = [IS_LABEL, FULL_LABEL]

METHOD_NOTE = (f"historical, monthly gross returns, base specification; "
               f"{CI:.0%} bootstrap, {N_SIMS:,} resamples, seed {SEED}")
OOS_VAR_NOTE = "VaR and ES not reported for 20 months (one observation in the 5% tail)"


def reproduction_failures(returns: dict, periods: dict, drawdowns: dict) -> list[str]:
    """Registered gates 1 and 2 (gate 3 is the unit-test suite)."""
    failures = []
    for period, n in EXPECTED_MONTHS.items():
        if len(periods[period]) != n:
            failures.append(f"{period}: {len(periods[period])} months, expected {n}")
    if failures:
        return failures

    published = {IS_LABEL: pd.read_csv("results/strategy_comparison_full_period.csv", index_col="label"),
                 OOS_LABEL: pd.read_csv("results/oos_summary.csv", index_col="label")}
    for period, table in published.items():
        for name in SERIES:
            sharpe = sharpe_ratio(returns[name].loc[periods[period]])
            if abs(sharpe - table.loc[name, "sharpe_ratio"]) > 1e-9:
                failures.append(f"{period} {name} Sharpe: recomputed {sharpe!r}, published {table.loc[name, 'sharpe_ratio']!r}")
            dd = drawdowns[period][name]["drawdown"].min()
            if abs(dd - table.loc[name, "max_drawdown"]) > 1e-9:
                failures.append(f"{period} {name} max drawdown: from series {dd!r}, published {table.loc[name, 'max_drawdown']!r}")

    saved = pd.read_csv("results/oos_monthly_returns.csv", index_col="date", parse_dates=True)
    for name in SERIES:
        rebuilt = returns[name].loc[periods[OOS_LABEL]]
        if len(rebuilt) != len(saved) or np.abs(rebuilt.values - saved[name].values).max() > 1e-9:
            failures.append(f"oos_monthly_returns.csv {name}: rebuilt series differs from the saved one")
    return failures


def diagnostics_rows(returns: dict, periods: dict) -> pd.DataFrame:
    """One row per period and series, in fixed order."""
    rows = []
    for period, dates in periods.items():
        bench = returns["Benchmark"].loc[dates]
        for name in SERIES:
            r = returns[name].loc[dates]
            row = {"period": period, "strategy": name, "n_months": len(r)}
            if period in VAR_PERIODS:
                var = bootstrap_statistic_ci(r, lambda x: historical_var(x, LEVEL), n_sims=N_SIMS, ci=CI, seed=SEED)
                es = bootstrap_statistic_ci(r, lambda x: expected_shortfall(x, LEVEL), n_sims=N_SIMS, ci=CI, seed=SEED)
                row.update({
                    "var_95": var["point"], "var_95_ci_lower": var["lower"], "var_95_ci_upper": var["upper"],
                    "es_95": es["point"], "es_95_ci_lower": es["lower"], "es_95_ci_upper": es["upper"],
                    "n_tail_months": int((r <= -var["point"]).sum()),
                })
            else:
                row.update({k: float("nan") for k in ["var_95", "var_95_ci_lower", "var_95_ci_upper",
                                                      "es_95", "es_95_ci_lower", "es_95_ci_upper"]})
                row["n_tail_months"] = pd.NA
            row.update({
                "hit_rate_positive": hit_rate(r),
                "hit_rate_vs_benchmark": hit_rate_vs_benchmark(r, bench) if name != "Benchmark" else float("nan"),
                "worst_month": float(r.min()),
                "worst_month_date": r.idxmin().date().isoformat(),
                "best_month": float(r.max()),
                "best_month_date": r.idxmax().date().isoformat(),
                "note": METHOD_NOTE if period in VAR_PERIODS else f"{OOS_VAR_NOTE}; {METHOD_NOTE}",
            })
            rows.append(row)
    df = pd.DataFrame(rows)
    df["n_tail_months"] = df["n_tail_months"].astype("Int64")
    return df


def build_drawdowns(returns: dict, periods: dict) -> dict:
    """Underwater series for in sample and out of sample, each from 1.0 the month-end before."""
    drawdowns = {}
    for period in [IS_LABEL, OOS_LABEL]:
        dates = periods[period]
        start = dates[0] - pd.offsets.MonthEnd(1)
        drawdowns[period] = {name: drawdown_series(returns[name].loc[dates], start) for name in SERIES}
    return drawdowns


def drawdown_rows(drawdowns: dict) -> pd.DataFrame:
    """
    One row per period, month (including the 1.0 starting point) and series.
    monthly_return comes from drawdown_series() itself, which leaves the
    starting row blank by construction.
    """
    frames = []
    for period, by_series in drawdowns.items():
        for name in SERIES:
            dd = by_series[name]
            frames.append(pd.DataFrame({
                "period": period,
                "date": [d.date().isoformat() for d in dd.index],
                "strategy": name,
                "monthly_return": dd["monthly_return"].values,
                "cumulative_value": dd["cumulative_value"].values,
                "running_peak": dd["running_peak"].values,
                "drawdown": dd["drawdown"].values,
            }))
    return pd.concat(frames, ignore_index=True)


def drawdown_file_failures(rows: pd.DataFrame) -> list[str]:
    """
    Gate on the drawdown file before it is written: for every period and
    series, exactly 48 (in sample) or 20 (out of sample) non-blank monthly
    returns, and a first row that is the blank 1.0 starting point.
    """
    failures = []
    for period in [IS_LABEL, OOS_LABEL]:
        for name in SERIES:
            sub = rows[(rows["period"] == period) & (rows["strategy"] == name)]
            filled = int(sub["monthly_return"].notna().sum())
            if filled != EXPECTED_MONTHS[period]:
                failures.append(f"drawdown series {period} {name}: {filled} non-blank monthly returns, "
                                f"expected {EXPECTED_MONTHS[period]}")
            first = sub.iloc[0]
            if pd.notna(first["monthly_return"]) or first["cumulative_value"] != 1.0:
                failures.append(f"drawdown series {period} {name}: starting row {first['date']} is not a blank 1.0 row")
    return failures


def print_overlap_check(diagnostics: pd.DataFrame):
    """
    Reading rule 2, checked factually. One-dimensional intervals all overlap
    each other exactly when the largest lower bound is at most the smallest
    upper bound; both are printed so this can be verified by eye. No series
    is named as having higher or lower tail risk.
    """
    print("\nReading rule 2: do the 90% intervals of the strategies and the benchmark overlap?")
    for measure in ["var_95", "es_95"]:
        for period in VAR_PERIODS:
            sub = diagnostics[diagnostics["period"] == period]
            lowers, uppers = sub[f"{measure}_ci_lower"], sub[f"{measure}_ci_upper"]
            largest_lower, smallest_upper = lowers.max(), uppers.min()
            overlap = largest_lower <= smallest_upper
            print(f"  {measure.upper().replace('_95', ' 95%'):8s} {period:32s} largest lower bound {largest_lower:.2%}, "
                  f"smallest upper bound {smallest_upper:.2%} -> all four overlap: {'yes' if overlap else 'NO'}")
            if not overlap:
                names = list(sub["strategy"])
                for i in range(len(names)):
                    for j in range(i + 1, len(names)):
                        a, b = sub.iloc[i], sub.iloc[j]
                        if a[f"{measure}_ci_lower"] > b[f"{measure}_ci_upper"] or b[f"{measure}_ci_lower"] > a[f"{measure}_ci_upper"]:
                            print(f"      intervals of {names[i]} and {names[j]} do not overlap")


def main():
    for path in [DIAGNOSTICS_PATH, DRAWDOWN_PATH]:
        if os.path.exists(path):
            raise SystemExit(f"{path} already exists. Not overwriting it; move it aside to rerun.")

    returns, _, is_dates, oos_dates = build_return_series()
    periods = {IS_LABEL: is_dates, OOS_LABEL: oos_dates, FULL_LABEL: is_dates.union(oos_dates)}
    for period, dates in periods.items():
        print(f"{period:34s} {dates.min().date()} to {dates.max().date()} ({len(dates)} months)")

    drawdowns = build_drawdowns(returns, periods)
    failures = reproduction_failures(returns, periods, drawdowns)
    if failures:
        print("\nREPRODUCTION CHECK FAILED. Nothing was written. Mismatches:")
        for f in failures:
            print("  " + f)
        raise SystemExit(1)
    print("\nReproduction gates passed: published Sharpe ratios and out-of-sample monthly returns reproduced; "
          "drawdown series reproduce the published maximum drawdowns, in sample and out of sample.")

    diagnostics = diagnostics_rows(returns, periods)
    drawdown_file = drawdown_rows(drawdowns)
    failures = drawdown_file_failures(drawdown_file)
    if failures:
        print("\nDRAWDOWN FILE CHECK FAILED. Nothing was written:")
        for f in failures:
            print("  " + f)
        raise SystemExit(1)
    print("Drawdown file check passed: 48 and 20 non-blank monthly returns per series, blank 1.0 starting rows.")

    diagnostics.to_csv(DIAGNOSTICS_PATH, index=False, lineterminator="\n")
    drawdown_file.to_csv(DRAWDOWN_PATH, index=False, lineterminator="\n")

    shown = diagnostics.drop(columns=["note"])
    with pd.option_context("display.width", 240, "display.max_columns", 30):
        print("\n" + shown.round(4).to_string(index=False))
    print(f"\n  {METHOD_NOTE}. Out of sample: {OOS_VAR_NOTE}.")

    print("\nReading rules (Phase 2B design):")
    print("  1. The measures are descriptive. No test between strategies is run.")
    print_overlap_check(diagnostics)
    print("  3. Hit rates are read against 50%; the difference from 50% is not tested.")
    print("  4. The drawdown series show what happened; the published maximum drawdowns are unchanged.")
    print(f"\nSaved {DIAGNOSTICS_PATH} and {DRAWDOWN_PATH}")


if __name__ == "__main__":
    main()
