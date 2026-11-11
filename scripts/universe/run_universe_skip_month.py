"""
Amendment 15 (LIMITATIONS_PLAN.md): the true 12-1 Momentum sensitivity, the
reversal diagnostic, the 12-1 portfolios and the survivorship-by-year table.

The registered Momentum signal ends at the close of t-1 and skips no month.
The 12-1 signal runs from the close of t-13 to the close of t-2. It is tested
like the headline: rank IC, quintile spread, single Fama-MacBeth, and the
joint Fama-MacBeth with the registered Value signal. Combined is rebuilt with
the 12-1 leg and the registered Value leg. The last month's return alone
(close of t-2 to close of t-1) gets rank IC and quintile spread with the
registered interval only. The usable set is the registered Momentum set with
a price at t-13, so 2012-01 is not used. Intervals: 5,000 resamples, seed 42,
90%, and the Newey-West and block-bootstrap intervals of Amendment 14.

Portfolios: the top decile and top quintile of Momentum 12-1 and of Combined
(12-1 leg), equal weight, held one month, from 2012-02. The weights start in
2012-02, so that month is the purchase from cash. Each is tested against the
registered benchmark series from 2012-02 onward, which are not restarted from
cash, gross and net on both turnover bases, with the paired Sharpe difference
on the Treasury bill rate (headline basis: gross) and the flat 2% (comparison
only). A month with fewer than 200 names in either set stops the run.

Survivorship by year (decision 7): a descriptive table for the registered
Momentum, Value and Combined signals, not the 12-1 sensitivity, built from the
saved result files. Per year: the share of the index usable (all, removed,
stayed, and the tested set), the mean rank IC, and the gross top-decile and
benchmark levels with their Sharpe difference and a paired 90% interval (Treasury
bill rate only). Survivorship affects both the levels and the differences, so
neither is presented as unbiased. The table adds no test.

Nothing here replaces a registered result. The re-test months are already
known from the published study, so they are not out-of-sample evidence.

Before anything new is built, the gates rerun and the registered Momentum and
Combined counts, monthly series, signal summaries, portfolio returns and the 12
gross headline portfolio rows are recomputed and compared with the saved files.
Before the survivorship table is built, the coverage shares, period mean IC,
period top-decile Sharpe figures and the registered survivorship diagnostic are
reproduced from the saved files. Any difference above 1e-9 stops the run.

Run from the repository root:
  python -m scripts.universe.run_universe_skip_month --dry-run
  python -m scripts.universe.run_universe_skip_month --dry-run --survivorship-only
  python -m scripts.universe.run_universe_skip_month --write
With no flag the script exits at once. The dry run runs every check, builds
every frame in memory, prints everything and writes nothing. With
--survivorship-only it builds and prints only the survivorship table and its
checks. --write is the single run of Amendment 15, decision 9: it refuses to
start if any of the eight files exists, builds and checks everything in memory,
then writes all eight files with mode "x", reads each back and prints its row
count and SHA-256. If any write fails, the files this run created are removed,
so either all eight files exist or none.
"""
import argparse
from datetime import datetime

import pandas as pd

from scripts.universe.run_universe_extras import robustness_table
from scripts.universe.run_universe_gates import (
    COVERAGE_PATH, TOP_DECILE_MINIMUM, run_gate2, run_gate1a_momentum, run_count_check, run_value_path,
    stop_on_failures,
)
from scripts.universe.run_universe_portfolios import (
    BY_YEAR_PATH, MOMENTUM_SET, VALUE_SET, load_rf, load_groups, build_set, returns_long, held_without_return_failures,
)
from scripts.universe.run_universe_signals import load_inputs, stop_if_outputs_exist, N_SIMS, SEED
from src.backtest import calculate_monthly_returns
from src.signal_eval import rank_ic, quintile_spread, monthly_statistic, fama_macbeth_slopes, summarize_signal
from src.survivorship_by_year import (
    yearly_shares, share_tested_by_year, share_failures, period_ic_failures, period_sharpe_failures,
    diagnostic_failures, survivorship_by_year_table, yearly_total_failures, SIGNALS, SHARE_COLUMN, COUNT_COLUMN,
)
from src.universe_portfolio import stage3_count_failures, survivorship_monthly, survivorship_summary, HEADLINE_BASIS
from src.universe_study import read_month_end_prices, evaluation_dates, usable_mask, study_periods, FULL_PERIOD
from src.universe_value import registered_list_failures, combined_signal, slope_summary, SUMMARY_COLUMNS
from src.universe_skip_month import (
    skip_month_usable_mask, skip_month_signal, last_month_return_signal, missing_signal_failures,
    skip_month_signal_set, skip_month_set_failures, months_failures, series_failures, summary_failures,
    skip_month_series, skip_month_summary, monthly_series_frame, skip_month_counts_frame, without_first_month,
    ic_correlation, reading_rule_flags, skip_month_outputs, prepare_outputs, output_failures, write_stage,
    portfolio_dates, decile_minimum_failures, skip_month_portfolios, benchmarks_from, portfolio_summary_frame,
    portfolio_months_failures, portfolio_returns_failures, portfolio_summary_failures, portfolio_flags,
    SENSITIVITY, MOMENTUM_12_1, COMBINED_12_1, LAST_MONTH, VALUE_JOINT_12_1, REGISTERED_NAME,
    SKIP_MONTH_BENCHMARK, REGISTERED_BENCHMARK, REGISTERED_STRATEGY, PORTFOLIO_KEYS, SURVIVORSHIP_BY_YEAR,
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
SAVED_PORTFOLIO_RETURNS = "results/universe_study_portfolio_returns.csv"
SAVED_PORTFOLIO_SUMMARY = "results/universe_study_portfolio_summary.csv"
SAVED_SURVIVORSHIP = "results/universe_study_survivorship.csv"
IC_PATHS = {"Momentum": SAVED_MONTHLY[("Momentum", "rank_ic")], "Value": SAVED_MONTHLY[("Combined", "rank_ic")],
            "Combined": SAVED_MONTHLY[("Combined", "rank_ic")]}
REGISTERED_HEADLINE_ROWS = 12   # Momentum and Combined, two sizes, three periods, gross
BUILT_PARTS = ["monthly_counts", "ic_monthly", "spread_monthly", "signal_summary", "inference_robustness",
               "portfolio_returns", "portfolio_summary", SURVIVORSHIP_BY_YEAR]


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


def run_portfolio_reproduction(path: dict, returns: pd.DataFrame, rf: pd.Series,
                               periods: dict) -> tuple[dict, dict, pd.DataFrame]:
    """
    The registered Momentum and Combined portfolios and both benchmarks, rebuilt
    with build_set() and checked against the saved returns, then the 12 gross
    headline rows recomputed and checked against the saved summary. Returns the
    registered portfolios, benchmarks and the saved summary.
    """
    signals = {"Momentum": path["momentum"], "Value": path["value"],
               "Combined": combined_signal(path["momentum"], path["value"])}
    portfolios, benchmarks = build_set(signals, ["Momentum", "Combined"], returns)
    stop_on_failures("Registered held names with a return",
                     held_without_return_failures({"registered": (portfolios, benchmarks)}))
    found = returns_long(portfolios, benchmarks, rf)
    stop_on_failures("Registered portfolio returns", portfolio_returns_failures(found, pd.read_csv(SAVED_PORTFOLIO_RETURNS)))

    print("  Recomputing the registered gross headline portfolio rows")
    recomputed = portfolio_summary_frame(portfolios, benchmarks, REGISTERED_BENCHMARK, rf, periods,
                                         n_sims=N_SIMS, seed=SEED, include_benchmarks=False)
    headline = recomputed[recomputed["basis"] == HEADLINE_BASIS]
    saved = pd.read_csv(SAVED_PORTFOLIO_SUMMARY)
    failures = [] if len(headline) == REGISTERED_HEADLINE_ROWS else [
        f"{len(headline)} gross rows recomputed, expected {REGISTERED_HEADLINE_ROWS}"]
    stop_on_failures("Registered gross headline rows", failures + portfolio_summary_failures(headline, saved))
    print(f"Reproduction: {len(portfolios) + len(benchmarks)} registered portfolio series x {len(found) // 6} months "
          f"and {len(headline)} gross headline rows match the saved files within 1e-9.")
    return portfolios, benchmarks, saved


# ---------------------------------------------------------------------------
# The 12-1 sensitivity and the reversal diagnostic
# ---------------------------------------------------------------------------

def build_skip_month(prices: pd.DataFrame, usability: pd.DataFrame, path: dict, returns: pd.DataFrame,
                     periods: dict) -> tuple[dict, dict, dict]:
    """Every signal-level frame keyed by output part, the monthly series and the 12-1 signal set. Nothing is written."""
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
    return {part: frame.assign(sensitivity=SENSITIVITY) for part, frame in frames.items()}, series, signals


def build_skip_month_portfolios(signals: dict, returns: pd.DataFrame, rf: pd.Series, registered_benchmarks: dict,
                                periods: dict) -> tuple[dict, dict, dict]:
    """The two portfolio frames keyed by output part, and the 12-1 portfolios and sliced benchmarks. Nothing is written."""
    trimmed = without_first_month(periods)
    dates = portfolio_dates(trimmed)
    stop_on_failures("Decile minimum", decile_minimum_failures(signals, dates, TOP_DECILE_MINIMUM))

    portfolios = skip_month_portfolios(signals, returns, dates)
    benchmarks = benchmarks_from(registered_benchmarks, dates)
    stop_on_failures("12-1 held names with a return", held_without_return_failures({"12-1": (portfolios, benchmarks)}))

    summary = portfolio_summary_frame(portfolios, benchmarks, SKIP_MONTH_BENCHMARK, rf, trimmed,
                                      n_sims=N_SIMS, seed=SEED)
    stop_on_failures("Portfolio months", portfolio_months_failures(summary))
    frames = {"portfolio_returns": returns_long(portfolios, benchmarks, rf), "portfolio_summary": summary}
    return {part: frame.assign(sensitivity=SENSITIVITY) for part, frame in frames.items()}, portfolios, benchmarks


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


PORTFOLIO_TESTS = ["sharpe_tbill", "benchmark_sharpe_tbill", "sharpe_diff_tbill", "ci_90_lower_tbill",
                   "ci_90_upper_tbill", "significant_tbill", "sharpe_diff_flat_2pct", "ci_90_lower_flat_2pct",
                   "ci_90_upper_flat_2pct"]
PORTFOLIO_LEVELS = ["period", "strategy", "size", "basis", "months", "total_return", "annualized_return",
                    "annualized_volatility", "sharpe_tbill", "sharpe_flat_2pct", "max_drawdown",
                    "avg_turnover_existing", "avg_turnover_drift"]


def portfolio_side_by_side(new: pd.DataFrame, registered: pd.DataFrame, bases: list[str] | None = None) -> pd.DataFrame:
    """12-1 strategy rows next to the registered rows of the same strategy, size, period and basis."""
    rows = new[new["strategy"].isin(list(REGISTERED_STRATEGY))]
    if bases is not None:
        rows = rows[rows["basis"].isin(bases)]
    rows = rows.assign(registered_strategy=rows["strategy"].map(REGISTERED_STRATEGY))
    merged = rows.merge(registered[PORTFOLIO_KEYS + ["months"] + PORTFOLIO_TESTS],
                        left_on=["period", "registered_strategy", "size", "basis"],
                        right_on=PORTFOLIO_KEYS, suffixes=("", "_reg"))
    return merged[["period", "strategy", "size", "basis", "months_reg", "sharpe_tbill_reg", "sharpe_diff_tbill_reg",
                   "ci_90_lower_tbill_reg", "ci_90_upper_tbill_reg", "significant_tbill_reg", "months"]
                  + PORTFOLIO_TESTS]


def print_portfolio_report(frames: dict, portfolios: dict, benchmarks: dict, registered_portfolios: dict,
                           registered_benchmarks: dict, saved_summary: pd.DataFrame, rf: pd.Series, periods: dict):
    summary = frames["portfolio_summary"]
    first = next(iter(portfolios.values())).index[0]
    print(f"\nFirst month {first:%Y-%m}: purchase from cash for each 12-1 portfolio (Amendment 13, decision 9)")
    for key, series in portfolios.items():
        print(f"  {str(key):45s} turnover existing {series.loc[first, 'turnover_existing']:.4f}, "
              f"drift {series.loc[first, 'turnover_drift']:.4f}")
    for name, series in benchmarks.items():
        print(f"  {name:45s} turnover existing {series.loc[first, 'turnover_existing']:.4f}, "
              f"drift {series.loc[first, 'turnover_drift']:.4f}")
    print(f"The benchmark's {first:%Y-%m} month is a rebalance of the registered series, not a purchase from cash, so "
          f"its purchase from cash is not charged on the net bases. The 12-1 portfolios are charged a full purchase "
          f"in {first:%Y-%m}.")
    print("The benchmarks hold the registered usable names, including those lost to the t-13 rule, which the 12-1 "
          "strategies cannot hold.")

    print("\nNames held per month (min, median, max):")
    for key, series in {**portfolios, **benchmarks}.items():
        held = series["names_held"]
        print(f"  {str(key):45s} {held.min()}, {held.median():.0f}, {held.max()}")

    with pd.option_context("display.width", 300, "display.max_columns", 40, "display.max_rows", 200):
        print("\nSharpe differences against the benchmark. Registered (_reg, saved file, 2012-01 included) next to 12-1 "
              "(from 2012-02). Gross with the Treasury bill rate is the headline basis; net bases and the flat 2% "
              "are shown for comparison:")
        print(portfolio_side_by_side(summary, saved_summary).round(4).to_string(index=False))

        print("\nLevels and turnover, 12-1 portfolios and the sliced benchmarks:")
        print(summary[PORTFOLIO_LEVELS].round(4).to_string(index=False))

        flags = portfolio_flags(summary, saved_summary)
        print("\nDecision 6 (portfolios, gross, Treasury bill interval only): rows where the 12-1 interval excludes "
              "zero while the registered interval does not:")
        print(flags.round(4).to_string(index=False) if len(flags) else "  none")

        print("\nNot registered, like-for-like: registered portfolios without 2012-01, gross basis only, against the "
              "registered benchmarks over the same months. Printout only, not written.")
        trimmed = without_first_month(periods)
        like = portfolio_summary_frame(registered_portfolios, benchmarks_from(registered_benchmarks, portfolio_dates(trimmed)),
                                       REGISTERED_BENCHMARK, rf, trimmed, n_sims=N_SIMS, seed=SEED,
                                       include_benchmarks=False)
        like = like[like["basis"] == HEADLINE_BASIS]
        print(portfolio_side_by_side(summary, like, bases=[HEADLINE_BASIS]).round(4).to_string(index=False))

    headline = summary[summary["headline_test"]]
    print(f"\nHeadline tests: {len(headline)} intervals at the 90% level (gross, Treasury bill rate). With no effect at "
          f"all, about {0.1 * len(headline):.1f} would exclude zero by chance alone, so no interval is read on its own.")
    print(f"Headline intervals that exclude zero: {int(headline['significant_tbill'].astype(bool).sum())}")
    tested = summary["sharpe_diff_tbill"].notna()
    print(f"Intervals added by the portfolios: {int(tested.sum())} with the Treasury bill rate and {int(tested.sum())} "
          f"with the flat 2% (comparison only).")


# ---------------------------------------------------------------------------
# Survivorship by year (decision 7)
# ---------------------------------------------------------------------------

def build_survivorship_by_year(path: dict, prices: pd.DataFrame, returns: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The reproduction checks, then the 45-row table. Returns the table and the saved registered diagnostic."""
    periods = study_periods()
    by_year = pd.read_csv(BY_YEAR_PATH)
    counts = {"Momentum": pd.read_csv(MOMENTUM_COUNTS_PATH)}
    counts["Value"] = counts["Combined"] = pd.read_csv(VALUE_COUNTS_PATH)
    tested = {signal: share_tested_by_year(counts[signal], COUNT_COLUMN[signal]) for signal in SIGNALS}
    ic = {signal: pd.read_csv(IC_PATHS[signal]) for signal in SIGNALS}
    returns_saved = pd.read_csv(SAVED_PORTFOLIO_RETURNS)
    signal_summary = pd.concat([pd.read_csv(p) for p in SAVED_SUMMARIES], ignore_index=True)
    portfolio_summary = pd.read_csv(SAVED_PORTFOLIO_SUMMARY)
    saved_diagnostic = pd.read_csv(SAVED_SURVIVORSHIP)

    failures = share_failures(pd.read_csv(COVERAGE_PATH), by_year)
    coverage_momentum = yearly_shares(by_year, SHARE_COLUMN["Momentum"])["share_usable_all"]
    failures += [f"{year}: Momentum tested share {share!r}, coverage share {coverage_momentum[year]!r}"
                 for year, share in tested["Momentum"].items() if not abs(share - coverage_momentum[year]) <= 1e-9]
    for signal in SIGNALS:
        failures += period_ic_failures(ic[signal], signal_summary, signal, periods)
        failures += period_sharpe_failures(returns_saved, portfolio_summary, signal, periods)

    groups = load_groups(list(prices.columns))
    diagnostic = pd.concat([survivorship_summary(survivorship_monthly(path[key].notna(), returns, groups), periods, label)
                            for key, label in (("momentum", MOMENTUM_SET), ("value", VALUE_SET))], ignore_index=True)
    failures += diagnostic_failures(diagnostic, saved_diagnostic)
    stop_on_failures("Survivorship-by-year reproduction", failures)
    print("\nReproduction: coverage shares by year, the Momentum tested share, period mean IC and period gross "
          "top-decile Sharpe figures for Momentum, Value and Combined, and the registered survivorship diagnostic "
          "match the saved files within 1e-9.")

    print(f"  Survivorship by year: one {N_SIMS}-resample bootstrap per year and signal (Treasury bill rate only)")
    table = survivorship_by_year_table(by_year, tested, ic, returns_saved, n_sims=N_SIMS, seed=SEED)
    stop_on_failures("Yearly totals", yearly_total_failures(table, signal_summary, portfolio_summary, FULL_PERIOD))
    return table, saved_diagnostic


SURVIVORSHIP_SHOWN = ["year", "months", "share_usable_all", "share_usable_removed", "share_usable_stayed",
                      "share_usable_tested", "ic_months", "mean_rank_ic", "top_decile_annualized_return",
                      "benchmark_annualized_return", "top_decile_sharpe_tbill", "benchmark_sharpe_tbill",
                      "sharpe_diff_tbill", "ci_90_lower_tbill", "ci_90_upper_tbill", "interval_excludes_zero"]


def print_survivorship_report(table: pd.DataFrame, saved_diagnostic: pd.DataFrame):
    with pd.option_context("display.width", 300, "display.max_columns", 40, "display.max_rows", 200):
        print("\nRegistered survivorship diagnostic by period (Amendment 13, decision 8), descriptive, context only:")
        print(saved_diagnostic.drop(columns=["universe_note"], errors="ignore").round(5).to_string(index=False))

        print("\nSurvivorship by year (Amendment 15, decision 7). Registered signals and portfolios, not the 12-1 "
              "sensitivity. Gross basis, Treasury bill rate.")
        print("  share_usable_all, _removed, _stayed: share of index member-months usable for the signal, from the "
              "Phase 3 coverage file (for Value and Combined, before the validity rule of Amendment 11).")
        print("  share_usable_tested: share of index member-months in the set actually tested (Stage 3 counts), "
              "all names only.")
        for signal in SIGNALS:
            rows = table[table["signal"] == signal]
            print(f"\n{signal} (benchmark: {rows['benchmark'].iloc[0]}):")
            print(rows[SURVIVORSHIP_SHOWN].round(4).to_string(index=False))

    partial = sorted(table.loc[table["partial_year"], "year"].unique())
    print(f"\nDescriptive only, no test. The missing names are mostly acquired or bankrupt companies and are absent from "
          f"both the strategy and its benchmark, so survivorship affects the levels and the differences alike; neither "
          f"is an unbiased estimate. The {len(table)} yearly intervals, on 8 to 12 months, are wide and are not part of "
          f"any test family. Partial years: {partial}.")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

NO_FLAG_MESSAGE = ("Choose --dry-run, or --write for the single run that writes all eight files. Nothing written.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="run every check and print everything, write nothing")
    mode.add_argument("--write", action="store_true",
                      help="the single run: every check, then write all eight files with mode x, or none")
    parser.add_argument("--survivorship-only", action="store_true",
                        help="with --dry-run: build and print only the survivorship-by-year table and its checks")
    args = parser.parse_args(argv)
    if args.survivorship_only and not args.dry_run:
        parser.error("--survivorship-only works only with --dry-run; the eight files are written together")
    return args


def print_manifest(manifest: pd.DataFrame):
    print("\nFiles written (mode x, read back, SHA-256 of the bytes on disk):")
    for row in manifest.itertuples():
        print(f"  {row.file}  rows {row.rows}  bytes {row.bytes}  sha256 {row.sha256}")
    print("To check the hashes yourself in PowerShell:")
    print(r"  Get-FileHash -Algorithm SHA256 results\universe_study_*_momentum_skip_month.csv")
    print(r"  Get-FileHash -Algorithm SHA256 results\universe_study_survivorship_by_year.csv")
    print(f"{len(manifest)} of {len(BUILT_PARTS)} files written with mode x and read back. The hashes are of the "
          f"working copy as written; Git line-ending conversion can change them in a later checkout.")


def run(args: argparse.Namespace):
    outputs = skip_month_outputs()
    stop_if_outputs_exist(outputs.values())     # before any computation
    calendar, usability = load_inputs()
    run_gate2(calendar)
    prices = read_month_end_prices(calendar)
    run_gate1a_momentum(prices, usability)
    run_count_check(prices, usability)
    path = run_value_path(calendar, prices, usability)
    stop_on_failures("Registered 24-name list", registered_list_failures(path["jumps"]))

    returns = calculate_monthly_returns(prices)
    if args.survivorship_only:
        table, saved_diagnostic = build_survivorship_by_year(path, prices, returns)
        print_survivorship_report(table, saved_diagnostic)
        print(f"\nDry run, survivorship only: nothing written. The full dry run builds all eight files together.\n"
              f"  {outputs[SURVIVORSHIP_BY_YEAR]} would have {len(table)} rows.")
        return

    periods = study_periods()
    registered, saved_robust = run_reproduction_checks(path, returns, periods)

    rf = load_rf(evaluation_dates())
    print(f"\nTreasury bill rate: {len(rf)} months, every month has a rate.")
    registered_portfolios, registered_benchmarks, saved_summary = run_portfolio_reproduction(path, returns, rf, periods)

    print(f"\nBootstrap: {N_SIMS} resamples, seed {SEED}, 90% intervals.")
    frames, series, signals = build_skip_month(prices, usability, path, returns, periods)
    portfolio_frames, portfolios, benchmarks = build_skip_month_portfolios(signals, returns, rf, registered_benchmarks,
                                                                           periods)
    frames.update(portfolio_frames)
    frames[SURVIVORSHIP_BY_YEAR], saved_diagnostic = build_survivorship_by_year(path, prices, returns)

    print_report(frames, series, registered, saved_robust, periods)
    print_portfolio_report(frames, portfolios, benchmarks, registered_portfolios, registered_benchmarks, saved_summary,
                           rf, periods)
    print_survivorship_report(frames[SURVIVORSHIP_BY_YEAR], saved_diagnostic)

    stop_on_failures("Output checks", output_failures(prepare_outputs(frames)))
    print(f"\nOutput checks: {len(frames)} frames, row counts {dict((p, len(f)) for p, f in frames.items())}, "
          f"notes and sensitivity columns as registered.")

    if not args.write:
        print("\nDry run: nothing written. With --write these files would be written, with mode x:")
        for part in BUILT_PARTS:
            print(f"  {outputs[part]} ({len(frames[part])} rows)")
        return

    stop_if_outputs_exist(outputs.values())     # again, in case a file appeared during the run
    print_manifest(write_stage(frames, outputs))


def main(argv: list[str] | None = None):
    args = parse_args(argv)
    if not (args.dry_run or args.write):
        raise SystemExit(NO_FLAG_MESSAGE)
    started = datetime.now()
    mode = "write" if args.write else ("dry run, survivorship only" if args.survivorship_only else "dry run")
    print(f"Run started {started:%Y-%m-%d %H:%M:%S} ({mode})")
    try:
        run(args)
    finally:
        ended = datetime.now()
        print(f"\nRun ended {ended:%Y-%m-%d %H:%M:%S}, duration {str(ended - started).split('.')[0]}")


if __name__ == "__main__":
    main()
