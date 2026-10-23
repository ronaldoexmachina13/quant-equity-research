"""
Statistical power analysis, as pre-registered in LIMITATIONS_PLAN.md
(Phase 1C, with Amendments 1 and 3).

Questions: how large would a strategy's annualised active return need to be
to be detectable with the data available, and how long a sample would be
needed to detect the active returns actually observed?

The purpose is to explain, not to rescue, the finding that nothing is
statistically significant. That conclusion stays unchanged whatever these
figures show (Amendment 3, item 7).

Definitions:
- Active return a_t = strategy return - equal-weight benchmark return, monthly,
  on the flat 2% basis (the same returns as the published scripts).
- The test is of the mean monthly active return against zero. It is not the
  beta-adjusted alpha regression, whose t-statistics are reported elsewhere.
- mean and sd are the sample mean and sample standard deviation (ddof = 1) of
  a_t, estimated separately for each period. Because the sd comes from the
  same sample, every figure is illustrative.
- Minimum detectable effect (MDE): (z_alpha + z_power) * sd / sqrt(n), monthly.
  Annualised as 12 x the monthly figure, the same arithmetic convention as
  the alpha regression; equivalently, annualised tracking error divided by
  the square root of the number of years.
- Months needed: ((z_alpha + z_power) * sd / |mean|)^2, rounded up.
- Primary level: 10% two-sided (z = 1.645), 80% power. The 5% two-sided
  figures (z = 1.96) are information only.

Before anything is written, the returns used here must reproduce the
published Sharpe ratios. If they do not, the script stops.
"""
import os

import numpy as np
import pandas as pd

from src.risk import (
    TRADING_PERIODS_PER_YEAR,
    sharpe_ratio,
    power_z_values,
    minimum_detectable_effect,
    months_needed_to_detect,
)
from run_rf_sensitivity import build_return_series

OUTPUT_PATH = "results/power_analysis.csv"

STRATEGIES = ["Momentum", "Value", "Combined"]
ALL_SERIES = STRATEGIES + ["Benchmark"]
POWER = 0.80
LEVELS = [("10% two-sided (primary)", 0.10), ("5% two-sided (information only)", 0.05)]
MDE_SAMPLE_LENGTHS = [48, 68, 170]
HYPOTHETICAL_N = 170

IS_LABEL = "In sample (2021-2024)"
OOS_LABEL = "Out of sample (Jan 2025-Aug 2026)"
COMBINED_LABEL = "In and out of sample combined (2021-Aug 2026)"
EXPECTED_LENGTHS = {IS_LABEL: 48, OOS_LABEL: 20, COMBINED_LABEL: 68}

TEST_LABEL = "test of the mean monthly active return against zero; not the beta-adjusted alpha regression"
SD_SOURCE = "estimated from the same sample; illustrative"
HYPOTHETICAL_NOTE = "hypothetical sample length (about 2012-2026); not a result"
MONTHS_NOTE = ("assumes the true mean active return equals the observed mean; "
               "the observed mean is itself noisy, so this is illustrative")


def reproduction_failures(returns: dict, periods: dict) -> list[str]:
    """
    The returns must reproduce the published Sharpe ratios (in sample and
    out of sample, to 1e-9), the saved out-of-sample monthly series, and the
    registered period lengths.
    """
    failures = []
    for period, n in EXPECTED_LENGTHS.items():
        if len(periods[period]) != n:
            failures.append(f"{period}: {len(periods[period])} months, expected {n}")

    published = {
        IS_LABEL: pd.read_csv("results/strategy_comparison_full_period.csv", index_col="label"),
        OOS_LABEL: pd.read_csv("results/oos_summary.csv", index_col="label"),
    }
    for period, table in published.items():
        for name in ALL_SERIES:
            recomputed = sharpe_ratio(returns[name].loc[periods[period]])
            if abs(recomputed - table.loc[name, "sharpe_ratio"]) > 1e-9:
                failures.append(f"{period} {name} Sharpe: recomputed {recomputed!r}, "
                                f"published {table.loc[name, 'sharpe_ratio']!r}")

    saved = pd.read_csv("results/oos_monthly_returns.csv", index_col="date", parse_dates=True)
    for name in ALL_SERIES:
        rebuilt = returns[name].loc[periods[OOS_LABEL]]
        if len(rebuilt) != len(saved) or np.abs(rebuilt.values - saved[name].values).max() > 1e-12:
            failures.append(f"oos_monthly_returns.csv {name}: rebuilt series differs from the saved one")
    return failures


def compute_rows(returns: dict, periods: dict) -> pd.DataFrame:
    """
    For each period, strategy and significance level: the annualised MDE at
    n = 48, 68 and 170, and the months needed to detect the observed mean.
    """
    rows = []
    for period, dates in periods.items():
        bench = returns["Benchmark"].loc[dates]
        for name in STRATEGIES:
            active = returns[name].loc[dates] - bench
            mean, sd = active.mean(), active.std()
            for level_label, alpha_level in LEVELS:
                z_alpha, z_power = power_z_values(alpha_level, POWER)
                base = {
                    "period": period,
                    "strategy": name,
                    "significance_level": level_label,
                    "z_alpha": z_alpha,
                    "z_power": z_power,
                    "n_sample": len(active),
                    "mean_active_monthly": mean,
                    "mean_active_annualised": TRADING_PERIODS_PER_YEAR * mean,
                    "sd_active_monthly": sd,
                    "sd_active_annualised": sd * np.sqrt(TRADING_PERIODS_PER_YEAR),
                }
                for n in MDE_SAMPLE_LENGTHS:
                    mde = TRADING_PERIODS_PER_YEAR * minimum_detectable_effect(sd, n, z_alpha, z_power)
                    rows.append({**base, "metric": "mde_annualised", "n_months": n, "value": mde,
                                 "note": HYPOTHETICAL_NOTE if n == HYPOTHETICAL_N else ""})
                needed = months_needed_to_detect(mean, sd, z_alpha, z_power)
                note = MONTHS_NOTE + (f"; {needed['note']}" if needed["note"] else "")
                rows.append({**base, "metric": "months_needed", "n_months": np.nan,
                             "value": needed["months"], "note": note})
    df = pd.DataFrame(rows)
    df["sd_source"] = SD_SOURCE
    df["test"] = TEST_LABEL
    df["n_months"] = df["n_months"].astype("Int64")
    return df


def print_summary(results: pd.DataFrame):
    """Readable tables, plus the registered reading rules."""
    for level_label, _ in LEVELS:
        sub = results[results["significance_level"] == level_label]
        z_alpha, z_power = sub["z_alpha"].iloc[0], sub["z_power"].iloc[0]
        print(f"\n=== {level_label}: z_alpha = {z_alpha:.4f}, z_power = {z_power:.4f} (80% power) ===")
        for period in EXPECTED_LENGTHS:
            p = sub[sub["period"] == period]
            print(f"\n{period} (sd estimated from these {p['n_sample'].iloc[0]} months; illustrative)")
            print(f"  {'':9s} {'mean act.':>10s} {'tracking':>9s} {'MDE n=48':>9s} {'MDE n=68':>9s} "
                  f"{'MDE n=170*':>11s} {'months needed':>14s}")
            for name in STRATEGIES:
                s = p[p["strategy"] == name]
                mde = s[s["metric"] == "mde_annualised"].set_index("n_months")["value"]
                needed = s[s["metric"] == "months_needed"].iloc[0]
                months = "n/a (zero mean)" if pd.isna(needed["value"]) else f"{int(needed['value']):,}"
                if needed["mean_active_monthly"] < 0:
                    months += " (underperf.)"
                print(f"  {name:9s} {needed['mean_active_annualised']:>+10.2%} {needed['sd_active_annualised']:>9.2%} "
                      f"{mde[48]:>9.2%} {mde[68]:>9.2%} {mde[170]:>11.2%} {months:>14s}")
    print("\n  mean act. = mean active return x 12; tracking = sd of active return x sqrt(12).")
    print(f"  * n = 170: {HYPOTHETICAL_NOTE}.")
    print(f"  Months needed: {MONTHS_NOTE}.")
    print(f"  All figures: {TEST_LABEL}.")

    print("\nReading rules (Amendment 3, item 7):")
    print("  (a) The conclusion that no result is statistically significant stays unchanged.")
    print("  (b) These figures explain the tests' low power; they do not re-interpret any observed result.")
    combined = results[(results["period"] == COMBINED_LABEL)
                       & (results["significance_level"] == LEVELS[0][0])]
    largest = combined["mean_active_annualised"].max()
    largest_name = combined.loc[combined["mean_active_annualised"].idxmax(), "strategy"]
    mde68 = combined[(combined["metric"] == "mde_annualised") & (combined["n_months"] == 68)].set_index("strategy")["value"]
    print(f"  (c) Combined period, primary level: largest observed annualised active return is "
          f"{largest:+.2%} ({largest_name}).")
    for name in STRATEGIES:
        verdict = "exceeds" if mde68[name] > largest else "does NOT exceed"
        print(f"      {name:9s} MDE at n = 68: {mde68[name]:.2%} -> {verdict} the largest observed active return")
    all_exceed = bool((mde68 > largest).all())
    print(f"      MDE at n = 68 exceeds the largest observed active return for every strategy: "
          f"{'yes' if all_exceed else 'NO'}")


def main():
    returns, _, is_dates, oos_dates = build_return_series()
    periods = {IS_LABEL: is_dates, OOS_LABEL: oos_dates, COMBINED_LABEL: is_dates.union(oos_dates)}
    for period, dates in periods.items():
        print(f"{period:46s} {dates.min().date()} to {dates.max().date()} ({len(dates)} months)")

    failures = reproduction_failures(returns, periods)
    if failures:
        print("\nREPRODUCTION CHECK FAILED. Nothing was written. Mismatches:")
        for f in failures:
            print("  " + f)
        raise SystemExit(1)
    print("\nReproduction check passed: the returns reproduce the published Sharpe ratios "
          "and the saved out-of-sample monthly series.")

    if os.path.exists(OUTPUT_PATH):
        raise SystemExit(f"{OUTPUT_PATH} already exists. Not overwriting it; move it aside to rerun.")

    results = compute_rows(returns, periods)
    results.to_csv(OUTPUT_PATH, index=False, lineterminator="\n")

    print_summary(results)
    print(f"\nSaved {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
