"""
True 12-1 Momentum sensitivity (LIMITATIONS_PLAN.md, Amendment 15, decisions 2 to 6).

The registered Momentum signal, dated t, is the return from the close of t-12
to the close of t-1, with no month skipped. This module builds the 12-1
signal, the close of t-13 to the close of t-2, and the last month's return
alone, the close of t-2 to the close of t-1. Every row dated t uses closes up
to t-1 at most and is paired with the return of month t.

The 12-1 usable set is the registered Momentum set restricted to names with a
price at t-13. The first evaluation month, 2012-01, has no t-13 price in the
calendar, so it is empty for every signal here. Combined takes the 12-1 leg
and the registered Value leg, each scaled over its own usable names, and
covers the names that have both.

Nothing here replaces a registered result. These are labelled, post-results
sensitivities.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from src.factors import calculate_momentum, calculate_momentum_skip_month
from src.signal_eval import (
    MIN_NAMES_PER_MONTH, rank_ic, quintile_spread, monthly_statistic, monthly_counts, fama_macbeth_slopes,
    summarize_signal,
)
from src.universe_portfolio import (
    top_group_weights, portfolio_series, strategy_summary, reference_summary, SIZES, GROSS, NET_DRIFT,
    MOMENTUM_BENCHMARK, VALUE_BENCHMARK,
)
from src.universe_study import NEW_TEST, RE_TEST, FULL_PERIOD, monthly_frame, series_frame
from src.universe_value import combined_signal, slope_summary, SUMMARY_COLUMNS

SENSITIVITY = "momentum_skip_month"
MOMENTUM_12_1 = "Momentum 12-1"
COMBINED_12_1 = "Combined (12-1 leg)"
LAST_MONTH = "Last-month return"
VALUE_JOINT_12_1 = "Value (joint with 12-1)"
VALUE = "Value"
START_LAG = 13          # months from the trade date back to the first close of the 12-1 window
EXPECTED_MONTHS = {NEW_TEST: 107, RE_TEST: 68, FULL_PERIOD: 175}
REGISTERED_NAME = {MOMENTUM_12_1: "Momentum", COMBINED_12_1: "Combined", VALUE_JOINT_12_1: "Value"}
RESULTS_DIR = Path("results")
SKIP_MONTH_PARTS = ["monthly_counts", "ic_monthly", "spread_monthly", "signal_summary", "inference_robustness",
                    "portfolio_returns", "portfolio_summary"]
SURVIVORSHIP_BY_YEAR = "survivorship_by_year"

# Portfolios (Amendment 15, decision 3). Each strategy is tested against the registered benchmark series
SKIP_MONTH_BENCHMARK = {MOMENTUM_12_1: MOMENTUM_BENCHMARK, COMBINED_12_1: VALUE_BENCHMARK}
REGISTERED_BENCHMARK = {"Momentum": MOMENTUM_BENCHMARK, "Combined": VALUE_BENCHMARK}
REGISTERED_STRATEGY = {MOMENTUM_12_1: "Momentum", COMBINED_12_1: "Combined"}
RETURN_COLUMNS = ["names_held", "names_without_return", GROSS, "turnover_existing", "turnover_drift",
                  "net_existing", NET_DRIFT, "rf_monthly"]
PORTFOLIO_TEST_COLUMNS = ["months", "sharpe_tbill", "benchmark_sharpe_tbill", "sharpe_diff_tbill", "ci_90_lower_tbill",
                          "ci_90_upper_tbill", "sharpe_diff_flat_2pct", "ci_90_lower_flat_2pct", "ci_90_upper_flat_2pct"]
PORTFOLIO_KEYS = ["period", "strategy", "size", "basis"]


# ---------------------------------------------------------------------------
# Usable set and signals
# ---------------------------------------------------------------------------

def skip_month_usable_mask(momentum_mask: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """The registered Momentum mask, kept only where the name has a month-end price at t-13."""
    start = prices.resample("ME").last().shift(START_LAG)
    has_start = start.reindex(index=momentum_mask.index, columns=momentum_mask.columns).notna()
    return momentum_mask & has_start


def skip_month_signal(prices: pd.DataFrame, mask: pd.DataFrame) -> pd.DataFrame:
    """calculate_momentum_skip_month() unchanged, on the mask's dates and tickers, blank outside the mask."""
    signal = calculate_momentum_skip_month(prices).reindex(index=mask.index, columns=mask.columns)
    return signal.where(mask)


def last_month_return_signal(prices: pd.DataFrame, mask: pd.DataFrame) -> pd.DataFrame:
    """The close of t-1 over the close of t-2, minus 1: calculate_momentum() with a two-month window."""
    signal = calculate_momentum(prices, lookback_months=2, skip_months=1).reindex(index=mask.index, columns=mask.columns)
    return signal.where(mask)


def missing_signal_failures(signal: pd.DataFrame, mask: pd.DataFrame) -> list[str]:
    """Every month and name that is in the mask but has no finite signal, which means no price at t-2."""
    values = signal.reindex(index=mask.index, columns=mask.columns).to_numpy(dtype=float)
    bad = mask.to_numpy(dtype=bool) & ~np.isfinite(values)
    rows, cols = np.nonzero(bad)
    return [f"{mask.index[r]:%Y-%m} {mask.columns[c]}: usable for 12-1 but no finite signal (no price at t-2)"
            for r, c in zip(rows, cols)]


def skip_month_signal_set(skip_momentum: pd.DataFrame, value: pd.DataFrame) -> dict:
    """The 12-1 signal, the registered Value signal, and Combined from the two, each leg on its own usable names."""
    return {MOMENTUM_12_1: skip_momentum, VALUE: value, COMBINED_12_1: combined_signal(skip_momentum, value)}


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def _differs(a: pd.Series, b: pd.Series) -> bool:
    return bool((a.astype(bool) != b.reindex(a.index).astype(bool)).any())


def skip_month_set_failures(signals: dict, registered_momentum: pd.DataFrame, returns: pd.DataFrame,
                            min_names: int = MIN_NAMES_PER_MONTH) -> list[str]:
    """
    signals holds MOMENTUM_12_1, VALUE, COMBINED_12_1 and LAST_MONTH. The first
    month must be empty for the three new signals. In every later month: at
    least min_names names for 12-1 and Combined, Combined on exactly the names
    with both legs, the last-month return on the 12-1 names, every 12-1 name in
    the registered Momentum set, and no usable name without a return.
    """
    momentum, value, combined, last = (signals[k] for k in (MOMENTUM_12_1, VALUE, COMBINED_12_1, LAST_MONTH))
    has_momentum = momentum.notna()
    both = has_momentum & value.reindex(index=momentum.index, columns=momentum.columns).notna()
    registered = registered_momentum.reindex(index=momentum.index, columns=momentum.columns).notna()
    month_returns = returns.reindex(index=momentum.index, columns=momentum.columns)
    checked = {MOMENTUM_12_1: momentum, COMBINED_12_1: combined, LAST_MONTH: last}

    first = momentum.index[0]
    failures = [f"{first:%Y-%m}: {name} has names, but this month has no price at t-13"
                for name, signal in checked.items() if signal.loc[first].notna().any()]
    for date in momentum.index[1:]:
        month = f"{date:%Y-%m}"
        for name in (MOMENTUM_12_1, COMBINED_12_1):
            count = int(checked[name].loc[date].notna().sum())
            if count < min_names:
                failures.append(f"{month}: {name} has {count} names, below {min_names}")
        if _differs(combined.loc[date].notna(), both.loc[date]):
            failures.append(f"{month}: Combined names differ from the names with both legs")
        if _differs(last.loc[date].notna(), has_momentum.loc[date]):
            failures.append(f"{month}: last-month return names differ from the 12-1 names")
        outside = has_momentum.loc[date] & ~registered.loc[date]
        if outside.any():
            failures.append(f"{month}: 12-1 names outside the registered Momentum set: {list(outside.index[outside])}")
        for name in (MOMENTUM_12_1, COMBINED_12_1):
            missing = checked[name].loc[date].notna() & month_returns.loc[date].isna()
            if missing.any():
                failures.append(f"{month}: {name} has {int(missing.sum())} names with no return")
    return failures


def months_failures(summary: pd.DataFrame, expected: dict = EXPECTED_MONTHS) -> list[str]:
    """Every summary row must use the expected number of months for its period."""
    wrong = summary[summary["months"] != summary["period"].map(expected)]
    return [f"{r.test} {r.signal} {r.period}: {r.months} months, expected {expected[r.period]}" for r in wrong.itertuples()]


def series_failures(found: pd.Series, saved: pd.DataFrame, signal: str, column: str,
                    tolerance: float = 1e-9) -> list[str]:
    """A recomputed monthly series against the rows of a saved monthly file for one signal. NaN matches NaN."""
    rows = saved[saved["signal"] == signal]
    expected = pd.Series(rows[column].values, index=pd.to_datetime(rows["date"]))
    aligned = pd.DataFrame({"found": found, "expected": expected})
    both_nan = aligned["found"].isna() & aligned["expected"].isna()
    differs = ~both_nan & ~((aligned["found"] - aligned["expected"]).abs() <= tolerance)
    return [f"{signal} {column} {d:%Y-%m}: found {r.found!r}, saved {r.expected!r}"
            for d, r in aligned[differs].iterrows()]


def summary_failures(found: pd.DataFrame, saved: pd.DataFrame, tolerance: float = 1e-9) -> list[str]:
    """Recomputed summary rows against saved rows on months, mean and interval. Every found row must be saved."""
    keys = ["test", "signal", "period"]
    merged = found.merge(saved, on=keys, how="left", suffixes=("", "_saved"), indicator=True)
    failures = [f"{r.test} {r.signal} {r.period}: not in the saved summary"
                for r in merged[merged["_merge"] != "both"].itertuples()]
    matched = merged[merged["_merge"] == "both"]
    for column in ("months", "mean", "ci_90_lower", "ci_90_upper"):
        wrong = matched[~((matched[column] - matched[f"{column}_saved"]).abs() <= tolerance)]
        failures += [f"{r.test} {r.signal} {r.period}: {column} {getattr(r, column)!r}, saved {getattr(r, column + '_saved')!r}"
                     for r in wrong.itertuples()]
    return failures


# ---------------------------------------------------------------------------
# Tests of the sensitivity
# ---------------------------------------------------------------------------

def skip_month_series(signals: dict, last_month: pd.DataFrame, returns: pd.DataFrame,
                      min_names: int = MIN_NAMES_PER_MONTH) -> dict:
    """{(signal, test): monthly series} for the ten series of the sensitivity and the reversal diagnostic."""
    momentum, value, combined = signals[MOMENTUM_12_1], signals[VALUE], signals[COMBINED_12_1]
    joint = fama_macbeth_slopes({MOMENTUM_12_1: momentum, VALUE: value}, returns, min_names)
    series = {}
    for name, signal in ((MOMENTUM_12_1, momentum), (COMBINED_12_1, combined), (LAST_MONTH, last_month)):
        series[(name, "rank_ic")] = monthly_statistic(signal, returns, rank_ic, min_names)
        series[(name, "quintile_spread")] = monthly_statistic(signal, returns, quintile_spread, min_names)
    for name, signal in ((MOMENTUM_12_1, momentum), (COMBINED_12_1, combined)):
        series[(name, "fama_macbeth_single")] = fama_macbeth_slopes({name: signal}, returns, min_names)[name]
    series[(MOMENTUM_12_1, "fama_macbeth_joint")] = joint[MOMENTUM_12_1]
    series[(VALUE_JOINT_12_1, "fama_macbeth_joint")] = joint[VALUE]
    return series


def skip_month_summary(series: dict, periods: dict, n_sims: int = 5000, seed: int = 42) -> pd.DataFrame:
    """The registered summary layout (SUMMARY_COLUMNS) for every series, with the registered bootstrap interval."""
    parts = []
    for name in (MOMENTUM_12_1, COMBINED_12_1, LAST_MONTH):
        slopes = {test: series[(name, test)] for test in ("fama_macbeth_single", "fama_macbeth_joint")
                  if (name, test) in series}
        parts.append(summarize_signal(name, series[(name, "rank_ic")], series[(name, "quintile_spread")], slopes,
                                      periods, n_sims=n_sims, seed=seed)[SUMMARY_COLUMNS])
    parts.append(slope_summary(VALUE_JOINT_12_1, {"fama_macbeth_joint": series[(VALUE_JOINT_12_1, "fama_macbeth_joint")]},
                               periods, n_sims, seed))
    return pd.concat(parts, ignore_index=True)


def monthly_series_frame(series: dict, test: str, column: str) -> pd.DataFrame:
    """One monthly file: the three signals with this test, every evaluation month, NaN where unused."""
    names = (MOMENTUM_12_1, COMBINED_12_1, LAST_MONTH)
    return pd.concat([series_frame(series[(name, test)], name, column) for name in names], ignore_index=True)


def skip_month_counts_frame(registered_momentum: pd.DataFrame, signals: dict, returns: pd.DataFrame,
                            coverage: pd.DataFrame) -> pd.DataFrame:
    """Names per month: registered and 12-1 Momentum, names lost to the t-13 rule, Value, Combined, no return."""
    momentum, value, combined = signals[MOMENTUM_12_1], signals[VALUE], signals[COMBINED_12_1]
    dates = momentum.index
    registered = registered_momentum.reindex(index=dates, columns=momentum.columns).notna()
    frame = monthly_frame(dates)
    frame["universe_size"] = coverage.set_index("month")["members"].reindex(dates.strftime("%Y-%m")).values
    frame["usable_momentum_registered"] = registered.sum(axis=1).values
    frame["usable_momentum_12_1"] = momentum.notna().sum(axis=1).values
    frame["lost_no_price_t13"] = (registered & momentum.isna()).sum(axis=1).values
    frame["usable_value_registered"] = value.notna().sum(axis=1).values
    frame["usable_combined_12_1"] = combined.notna().sum(axis=1).values
    frame["no_return_momentum_12_1"] = monthly_counts(momentum, returns)["no_return"].values
    frame["no_return_combined_12_1"] = monthly_counts(combined, returns)["no_return"].values
    return frame


# ---------------------------------------------------------------------------
# Printout only (Amendment 15 answers 8 and 9). Nothing here is written
# ---------------------------------------------------------------------------

def without_first_month(periods: dict) -> dict:
    """The registered periods with the first evaluation month removed, for the like-for-like comparison."""
    first = min(dates.min() for dates in periods.values())
    return {label: dates[dates != first] for label, dates in periods.items()}


def ic_correlation(registered: pd.Series, skip_month: pd.Series, periods: dict) -> pd.DataFrame:
    """Pearson correlation of two monthly IC series by period, over the months where both have a value."""
    rows = []
    for period, dates in periods.items():
        pair = pd.DataFrame({"registered": registered.reindex(dates), "skip_month": skip_month.reindex(dates)}).dropna()
        rows.append({"period": period, "months": len(pair), "pearson": pair["registered"].corr(pair["skip_month"])})
    return pd.DataFrame(rows)


def reading_rule_flags(new: pd.DataFrame, registered: pd.DataFrame) -> pd.DataFrame:
    """
    Decision 6: rows where a sensitivity interval (registered bootstrap,
    Newey-West or block) excludes zero while the registered interval of the
    matching registered test does not. new and registered are in the layout
    of the inference robustness file. A row with no registered match is an
    error, not a silent pass.
    """
    matched = new[new["signal"].isin(list(REGISTERED_NAME))]
    matched = matched.assign(registered_signal=matched["signal"].map(REGISTERED_NAME))
    merged = matched.merge(registered[["test", "signal", "period", "iid_excludes_zero"]],
                           left_on=["test", "registered_signal", "period"], right_on=["test", "signal", "period"],
                           how="left", suffixes=("", "_registered"))
    unmatched = merged["iid_excludes_zero_registered"].isna()
    if unmatched.any():
        raise ValueError(f"No registered row for: {merged.loc[unmatched, ['test', 'signal', 'period']].values.tolist()}")
    any_new = merged["iid_excludes_zero"] | merged["nw_excludes_zero"] | merged["block_excludes_zero"]
    flagged = merged[any_new & ~merged["iid_excludes_zero_registered"].astype(bool)]
    return flagged[["test", "signal", "period", "iid_excludes_zero", "nw_excludes_zero", "block_excludes_zero"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Portfolios (Amendment 15, decision 3)
# ---------------------------------------------------------------------------

def portfolio_dates(periods: dict) -> pd.DatetimeIndex:
    """Every month of the given periods, in order. With the trimmed periods, 2012-02 to 2026-08."""
    return pd.DatetimeIndex(sorted(set().union(*[set(dates) for dates in periods.values()])))


def decile_minimum_failures(signals: dict, dates: pd.DatetimeIndex, minimum: int) -> list[str]:
    """Months in which the 12-1 or Combined set has fewer names than the decile minimum of Phase 4."""
    failures = []
    for name in (MOMENTUM_12_1, COMBINED_12_1):
        counts = signals[name].loc[dates].notna().sum(axis=1)
        failures += [f"{d:%Y-%m}: {name} has {n} names, below the decile minimum of {minimum}"
                     for d, n in counts[counts < minimum].items()]
    return failures


def skip_month_portfolios(signals: dict, returns: pd.DataFrame, dates: pd.DatetimeIndex) -> dict:
    """
    {(strategy, size): monthly series} for the 12-1 and Combined top groups.
    The weights start at dates[0], so that month is the purchase from cash:
    the turnover functions treat only the first row of the frame that way.
    """
    return {(name, size): portfolio_series(top_group_weights(signals[name].loc[dates], q), returns)
            for name in (MOMENTUM_12_1, COMBINED_12_1) for size, q in SIZES.items()}


def benchmarks_from(benchmarks: dict, dates: pd.DatetimeIndex) -> dict:
    """The registered benchmark series on these dates, rows unchanged: the turnover is not restarted from cash."""
    return {name: series.loc[dates] for name, series in benchmarks.items()}


def portfolio_summary_frame(portfolios: dict, benchmarks: dict, benchmark_of: dict, rf_monthly: pd.Series,
                            periods: dict, n_sims: int = 5000, seed: int = 42,
                            include_benchmarks: bool = True) -> pd.DataFrame:
    """strategy_summary() for each portfolio against its own benchmark, then the benchmark level rows."""
    parts = [strategy_summary(strategy, size, series, benchmarks[benchmark_of[strategy]], benchmark_of[strategy],
                              rf_monthly, periods, n_sims, seed)
             for (strategy, size), series in portfolios.items()]
    if include_benchmarks:
        parts += [reference_summary(name, series, [GROSS, NET_DRIFT], rf_monthly, periods)
                  for name, series in benchmarks.items()]
    return pd.concat(parts, ignore_index=True)


def portfolio_months_failures(summary: pd.DataFrame, expected: dict = EXPECTED_MONTHS) -> list[str]:
    wrong = summary[summary["months"] != summary["period"].map(expected)]
    return [f"{r.strategy} {r.size} {r.basis} {r.period}: {r.months} months, expected {expected[r.period]}"
            for r in wrong.itertuples()]


def _keyed(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    out = frame.copy()
    if "size" in out:
        out["size"] = out["size"].fillna("")
    if "date" in out:
        out["date"] = pd.to_datetime(out["date"])
    return out.set_index(keys)


def _value_failures(found: pd.DataFrame, saved: pd.DataFrame, keys: list[str], columns: list[str],
                    tolerance: float) -> list[str]:
    """Every found row must be in saved, and each column must match within tolerance. NaN matches NaN."""
    found, saved = _keyed(found, keys), _keyed(saved, keys)
    missing = found.index.difference(saved.index)
    failures = [f"{key}: not in the saved file" for key in missing]
    common = found.index.intersection(saved.index)
    for column in columns:
        a = found.loc[common, column].astype(float)
        b = saved.loc[common, column].astype(float)
        bad = ~(a.isna() & b.isna()) & ~((a - b).abs() <= tolerance)
        failures += [f"{key}: {column} {a[key]!r}, saved {b[key]!r}" for key in a.index[bad]]
    return failures


def portfolio_returns_failures(found: pd.DataFrame, saved: pd.DataFrame, tolerance: float = 1e-9) -> list[str]:
    """Recomputed long-format portfolio returns against the saved file, by strategy, size and date."""
    return _value_failures(found, saved, ["strategy", "size", "date"], RETURN_COLUMNS, tolerance)


def portfolio_summary_failures(found: pd.DataFrame, saved: pd.DataFrame, tolerance: float = 1e-9) -> list[str]:
    """Recomputed summary rows against the saved summary, by period, strategy, size and basis."""
    return _value_failures(found, saved, PORTFOLIO_KEYS, PORTFOLIO_TEST_COLUMNS, tolerance)


def _excludes_zero(frame: pd.DataFrame) -> pd.Series:
    return ~((frame["ci_90_lower_tbill"] <= 0) & (0 <= frame["ci_90_upper_tbill"]))


def portfolio_flags(new: pd.DataFrame, registered: pd.DataFrame) -> pd.DataFrame:
    """
    Decision 6 for portfolios, as answered: gross basis, Treasury bill
    interval only. A 12-1 row is flagged if its interval excludes zero while
    the registered row of the same strategy, size and period does not. A row
    with no registered match is an error, not a silent pass.
    """
    rows = new[new["strategy"].isin(list(REGISTERED_STRATEGY)) & (new["basis"] == GROSS)]
    rows = rows.assign(registered_strategy=rows["strategy"].map(REGISTERED_STRATEGY))
    reg = registered[registered["basis"] == GROSS].assign(registered_excludes=_excludes_zero)
    merged = rows.merge(reg[["period", "strategy", "size", "registered_excludes"]],
                        left_on=["period", "registered_strategy", "size"], right_on=["period", "strategy", "size"],
                        how="left", suffixes=("", "_registered"))
    unmatched = merged["registered_excludes"].isna()
    if unmatched.any():
        raise ValueError(f"No registered row for: {merged.loc[unmatched, ['strategy', 'size', 'period']].values.tolist()}")
    merged["excludes_zero_tbill"] = _excludes_zero(merged)
    flagged = merged[merged["excludes_zero_tbill"] & ~merged["registered_excludes"].astype(bool)]
    return flagged[["period", "strategy", "size", "basis", "sharpe_diff_tbill", "ci_90_lower_tbill",
                    "ci_90_upper_tbill"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

def skip_month_outputs(folder: Path = RESULTS_DIR) -> dict:
    """{part: path} for the eight files of Amendment 15, decision 9."""
    paths = {part: folder / f"universe_study_{part}_{SENSITIVITY}.csv" for part in SKIP_MONTH_PARTS}
    paths[SURVIVORSHIP_BY_YEAR] = folder / f"universe_study_{SURVIVORSHIP_BY_YEAR}.csv"
    return paths
