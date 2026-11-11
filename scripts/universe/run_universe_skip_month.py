"""
Amendment 15 (LIMITATIONS_PLAN.md): the true 12-1 Momentum sensitivity and
the reversal diagnostic. The 12-1 portfolios and the survivorship-by-year
table are added in later steps.

The registered Momentum signal ends at the close of t-1 and skips no month.
The 12-1 signal runs from the close of t-13 to the close of t-2. It is tested
like the headline: rank IC, quintile spread, single Fama-MacBeth, and the
joint Fama-MacBeth with the registered Value signal. Combined is rebuilt with
the 12-1 leg and the registered Value leg. The last month's return alone
(close of t-2 to close of t-1) gets rank IC and quintile spread with the
registered interval only. The usable set is the registered Momentum set with
a price at t-13, so 2012-01 is not used. Intervals: 5,000 resamples, seed 42,
90%, and the Newey-West and block-bootstrap intervals of Amendment 14.

Nothing here replaces a registered result. The re-test months are already
known from the published study, so they are not out-of-sample evidence.

Before anything new is built, the gates rerun and the registered Momentum and
Combined counts, monthly series and summaries are recomputed and compared with
the saved files. Any difference above 1e-9 stops the run.

Run from the repository root:
  python -m scripts.universe.run_universe_skip_month --dry-run
The dry run runs every check, builds every frame in memory, prints everything
and writes nothing. Writing is not available yet: all eight files of
Amendment 15, decision 9 are written in one run, with mode "x", once the
portfolio and survivorship parts exist.
"""
import argparse

import pandas as pd

from scripts.universe.run_universe_extras import robustness_table
from scripts.universe.run_universe_gates import (
    COVERAGE_PATH, run_gate2, run_gate1a_momentum, run_count_check, run_value_path, stop_on_failures,
)
from scripts.universe.run_universe_signals import load_inputs, stop_if_outputs_exist, N_SIMS, SEED
from src.backtest import calculate_monthly_returns
from src.signal_eval import rank_ic, quintile_spread, monthly_statistic, fama_macbeth_slopes, summarize_signal
from src.universe_portfolio import stage3_count_failures
from src.universe_study import read_month_end_prices, evaluation_dates, usable_mask, study_periods
from src.universe_value import registered_list_failures, combined_signal, slope_summary, SUMMARY_COLUMNS
from src.universe_skip_month import (
    skip_month_usable_mask, skip_month_signal, last_month_return_signal, missing_signal_failures,
    skip_month_signal_set, skip_month_set_failures, months_failures, series_failures, summary_failures,
    skip_month_series, skip_month_summary, monthly_series_frame, skip_month_counts_frame, without_first_month,
    ic_correlation, reading_rule_flags, skip_month_outputs,
    SENSITIVITY, MOMENTUM_12_1, COMBINED_12_1, LAST_MONTH, VALUE_JOINT_12_1, REGISTERED_NAME,
)

MOMENTUM_COUNTS_PATH = "results/universe_study_monthly_counts_momentum.csv"
VALUE_COUNTS_PATH = "results/universe_study_monthly_counts_value_combined.csv"
SAVED_MONTHLY = {
    ("Momentum", "rank_ic"): "results/universe_study_ic_monthly_momentum.csv",
    ("Momentum", "quintile_spread"): "results/universe_study_spread_monthly_momentum.csv",
    ("Combined", "rank_ic"): "results/universe_study_ic_monthly_value_combined.csv",
    ("Combined", "quintile_spread"): "results/universe_study_spread_monthly_value_combined.csv",
}
SAVED_SUMMARIES = ["results/universe_study_signal_summary_momentum.csv",
                   "results/universe_study_signal_summary_value_combined.csv"]
SAVED_ROBUSTNESS = "results/universe_study_inference_robustness.csv"
STEP_2_PARTS = ["monthly_counts", "ic_monthly", "spread_monthly", "signal_summary", "inference_robustness"]


# ---------------------------------------------------------------------------
# Registered results, recomputed and checked against the saved files
# ---------------------------------------------------------------------------

def registered_series(momentum: pd.DataFrame, value: pd.DataFrame, returns: pd.DataFrame) -> dict:
    """{(signal, test): monthly series} for the registered tests that have a 12-1 counterpart."""
    combined = combined_signal(momentum, value)
    joint = fama_macbeth_slopes({"Momentum": momentum, "Value": value}, returns)
    series = {}
    for name, signal in (("Momentum", momentum), ("Combined", combined)):
        series[(name, "rank_ic")] = monthly_statistic(signal, returns, rank_ic)
        series[(name, "quintile_spread")] = monthly_statistic(signal, returns, quintile_spread)
        series[(name, "fama_macbeth_single")] = fama_macbeth_slopes({name: signal}, returns)[name]
    series[("Momentum", "fama_macbeth_joint")] = joint["Momentum"]
    series[("Value", "fama_macbeth_joint")] = joint["Value"]
    return series


def registered_summary(series: dict, periods: dict) -> pd.DataFrame:
    """The registered summary rows of those tests, in the registered layout and with the registered interval."""
    parts = [summarize_signal(name, series[(name, "rank_ic")], series[(name, "quintile_spread")],
                              {"fama_macbeth_single": series[(name, "fama_macbeth_single")]}, periods,
                              n_sims=N_SIMS, seed=SEED)[SUMMARY_COLUMNS]
             for name in ("Momentum", "Combined")]
    for name in ("Momentum", "Value"):
        parts.append(slope_summary(name, {"fama_macbeth_joint": series[(name, "fama_macbeth_joint")]}, periods,
                                   N_SIMS, SEED))
    return pd.concat(parts, ignore_index=True)


def run_reproduction_checks(path: dict, returns: pd.DataFrame, periods: dict) -> tuple[dict, pd.DataFrame]:
    """Counts, monthly series and summaries of the registered run. Returns the series and the saved robustness rows."""
    failures = stage3_count_failures(path["momentum"].notna().sum(axis=1), pd.read_csv(MOMENTUM_COUNTS_PATH),
                                     "usable_momentum", "Momentum")
    failures += stage3_count_failures(path["value"].notna().sum(axis=1), pd.read_csv(VALUE_COUNTS_PATH),
                                      "usable_value_combined", "Value and Combined")
    stop_on_failures("Registered usable counts", failures)

    series = registered_series(path["momentum"], path["value"], returns)
    failures = []
    for (name, test), file in SAVED_MONTHLY.items():
        failures += series_failures(series[(name, test)], pd.read_csv(file), name, test)
    stop_on_failures("Registered monthly series", failures)

    recomputed = registered_summary(series, periods)
    saved = pd.concat([pd.read_csv(p) for p in SAVED_SUMMARIES], ignore_index=True)
    robustness = pd.read_csv(SAVED_ROBUSTNESS)
    saved_robust_iid = robustness.rename(columns={"iid_ci_90_lower": "ci_90_lower", "iid_ci_90_upper": "ci_90_upper"})
    failures = summary_failures(recomputed, saved) + summary_failures(recomputed, saved_robust_iid)
    stop_on_failures("Registered summaries", failures)
    print(f"\nReproduction: registered counts, {len(SAVED_MONTHLY)} monthly series and {len(recomputed)} summary rows "
          f"match the saved files within 1e-9.")
    return series, robustness


# ---------------------------------------------------------------------------
# The 12-1 sensitivity and the reversal diagnostic
# ---------------------------------------------------------------------------

def build_skip_month(prices: pd.DataFrame, usability: pd.DataFrame, path: dict, returns: pd.DataFrame,
                     periods: dict) -> tuple[dict, dict]:
    """Every step 2 frame, keyed by output part, and the monthly series. Nothing is written here."""
    momentum_mask = usable_mask(usability, "usable_momentum", evaluation_dates(), list(prices.columns))
    mask = skip_month_usable_mask(momentum_mask, prices)
    skip = skip_month_signal(prices, mask)
    stop_on_failures("12-1 signal on the usable set", missing_signal_failures(skip, mask))

    signals = skip_month_signal_set(skip, path["value"])
    last = last_month_return_signal(prices, mask)
    stop_on_failures("12-1 set checks", skip_month_set_failures({**signals, LAST_MONTH: last}, path["momentum"], returns))

    series = skip_month_series(signals, last, returns)
    summary = skip_month_summary(series, periods, n_sims=N_SIMS, seed=SEED)
    robust = robustness_table({key: s for key, s in series.items() if key[0] != LAST_MONTH}, periods)
    stop_on_failures("Months used", months_failures(summary) + months_failures(robust))

    frames = {
        "monthly_counts": skip_month_counts_frame(path["momentum"], signals, returns, pd.read_csv(COVERAGE_PATH)),
        "ic_monthly": monthly_series_frame(series, "rank_ic", "rank_ic"),
        "spread_monthly": monthly_series_frame(series, "quintile_spread", "quintile_spread"),
        "signal_summary": summary,
        "inference_robustness": robust,
    }
    return {part: frame.assign(sensitivity=SENSITIVITY) for part, frame in frames.items()}, series


# ---------------------------------------------------------------------------
# Printout
# ---------------------------------------------------------------------------

def print_usable_set(counts: pd.DataFrame, periods: dict):
    by_date = counts.set_index("date")
    print("\nUsable set: registered Momentum names with a price at t-13. 2012-01 is not used: the calendar starts "
          "in 2011-01, so no name has a price at t-13.")
    for period, dates in periods.items():
        used = by_date.loc[dates]
        used = used[used["usable_momentum_12_1"] > 0]
        m, c, lost = used["usable_momentum_12_1"], used["usable_combined_12_1"], used["lost_no_price_t13"]
        print(f"  {period}: {len(used)} months; Momentum 12-1 names min {m.min()}, median {m.median():.0f}, "
              f"max {m.max()}, name-months {m.sum()}; lost to t-13 per month min {lost.min()}, median "
              f"{lost.median():.0f}, max {lost.max()}, total {lost.sum()}; Combined names min {c.min()}, median "
              f"{c.median():.0f}, max {c.max()}; months below 100: {int((m < 100).sum() + (c < 100).sum())}")


def side_by_side(summary: pd.DataFrame, robust: pd.DataFrame, saved_robust: pd.DataFrame) -> pd.DataFrame:
    new = robust.merge(summary[["test", "signal", "period", "share_positive"]], on=["test", "signal", "period"])
    new = new.assign(registered_signal=new["signal"].map(REGISTERED_NAME))
    merged = new.merge(saved_robust, left_on=["test", "registered_signal", "period"],
                       right_on=["test", "signal", "period"], suffixes=("", "_reg"))
    merged["robust"] = merged["iid_excludes_zero"] & merged["nw_excludes_zero"] & merged["block_excludes_zero"]
    merged["robust_reg"] = (merged["iid_excludes_zero_reg"] & merged["nw_excludes_zero_reg"]
                            & merged["block_excludes_zero_reg"])
    return merged[["test", "signal", "period",
                   "months_reg", "mean_reg", "iid_ci_90_lower_reg", "iid_ci_90_upper_reg", "iid_excludes_zero_reg",
                   "nw_excludes_zero_reg", "block_excludes_zero_reg", "robust_reg",
                   "months", "mean", "iid_ci_90_lower", "iid_ci_90_upper", "iid_excludes_zero",
                   "nw_excludes_zero", "block_excludes_zero", "robust", "autocorrelation_lag1"]]


def like_for_like(series: dict, periods: dict, summary: pd.DataFrame) -> pd.DataFrame:
    """Registered tests over the registered periods without 2012-01, next to the 12-1 rows. Printout only."""
    registered = registered_summary(series, without_first_month(periods))
    registered = registered.assign(signal_12_1=registered["signal"].map({v: k for k, v in REGISTERED_NAME.items()}))
    merged = registered.merge(summary, left_on=["test", "signal_12_1", "period"], right_on=["test", "signal", "period"],
                              suffixes=("_reg", ""))
    return merged[["test", "signal", "period", "months_reg", "mean_reg", "ci_90_lower_reg", "ci_90_upper_reg",
                   "excludes_zero_reg", "months", "mean", "ci_90_lower", "ci_90_upper", "excludes_zero"]]


def print_report(frames: dict, series: dict, registered: dict, saved_robust: pd.DataFrame, periods: dict):
    summary, robust = frames["signal_summary"], frames["inference_robustness"]
    print_usable_set(frames["monthly_counts"], periods)
    with pd.option_context("display.width", 300, "display.max_columns", 40, "display.max_rows", 200):
        print("\nRegistered (_reg, from the saved files) next to 12-1. 90% intervals: registered bootstrap (iid), "
              "Newey-West (nw), block bootstrap (block). Robust means all three exclude zero.")
        print(side_by_side(summary, robust, saved_robust).round(5).to_string(index=False))

        flags = reading_rule_flags(robust, saved_robust)
        print("\nDecision 6: rows where a 12-1 interval excludes zero while the registered interval does not:")
        print(flags.to_string(index=False) if len(flags) else "  none")

        print(f"\nReversal diagnostic, {LAST_MONTH} (close of t-2 to close of t-1), registered 90% interval only, "
              f"descriptive:")
        print(summary[summary["signal"] == LAST_MONTH].drop(columns=["sensitivity"]).round(5).to_string(index=False))

        print("\nNot registered, like-for-like: registered tests without 2012-01, next to 12-1. Registered 90% "
              "interval only. Printout only, not written.")
        print(like_for_like(registered, periods, summary).round(5).to_string(index=False))

        correlation = ic_correlation(registered[("Momentum", "rank_ic")], series[(MOMENTUM_12_1, "rank_ic")], periods)
        print("\nPearson correlation of the registered and 12-1 monthly rank IC series. Printout only, not written:")
        print(correlation.round(4).to_string(index=False))

    added = len(summary) + 2 * len(robust)
    print(f"\nIntervals added by this step: {len(summary)} registered-type bootstrap intervals and {len(robust)} each of "
          f"Newey-West and block bootstrap, {added} in all. They are read as one family with the registered results "
          f"and the Amendment 14 additions, so no single interval is read on its own.")
    print(f"Signals: {MOMENTUM_12_1}, {COMBINED_12_1}, {LAST_MONTH}, and {VALUE_JOINT_12_1} for the Value slope of the "
          f"joint regression. Nothing replaces the registered Momentum or Combined result. The re-test months are not "
          f"out-of-sample evidence.")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="run every check and print everything, write nothing")
    if not parser.parse_args().dry_run:
        raise SystemExit("Only --dry-run is available. The portfolio and survivorship parts are not built yet, and "
                         "all eight files are written in one run. Nothing written.")

    outputs = skip_month_outputs()
    stop_if_outputs_exist(outputs.values())
    calendar, usability = load_inputs()
    run_gate2(calendar)
    prices = read_month_end_prices(calendar)
    run_gate1a_momentum(prices, usability)
    run_count_check(prices, usability)
    path = run_value_path(calendar, prices, usability)
    stop_on_failures("Registered 24-name list", registered_list_failures(path["jumps"]))

    returns = calculate_monthly_returns(prices)
    periods = study_periods()
    registered, saved_robust = run_reproduction_checks(path, returns, periods)

    print(f"\nBootstrap: {N_SIMS} resamples, seed {SEED}, 90% intervals.")
    frames, series = build_skip_month(prices, usability, path, returns, periods)
    print_report(frames, series, registered, saved_robust, periods)

    print("\nDry run: nothing written. These files would be written, with mode x:")
    for part in STEP_2_PARTS:
        print(f"  {outputs[part]} ({len(frames[part])} rows)")
    print("Not built yet: " + ", ".join(str(outputs[p]) for p in outputs if p not in STEP_2_PARTS))


if __name__ == "__main__":
    main()
