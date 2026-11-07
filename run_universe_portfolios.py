"""
Phase 4, Stage 4: portfolio tests (LIMITATIONS_PLAN.md, Phase 4 detailed
design, Amendments 8 to 12, and Amendment 13).

The portfolio tests are secondary evidence and are read only alongside the
Stage 3 signal tests (reading rule 3 of the Phase 4 entry).

Portfolios: Momentum, Value and Combined, top decile and top quintile, equal
weight, monthly rebalancing, one continuous run from January 2012 that is
sliced into the new test (2012-2020), the re-test (2021-2026) and the full
period. January 2012 is a purchase from cash, for strategies and benchmarks
alike. Each strategy is compared with the equal-weight portfolio of its own
usable names: Momentum with the Momentum-usable names, Value and Combined with
the Value and Combined-usable names. Costs are 10 bps one-way, on the
existing and the drift-inclusive turnover bases, and benchmarks are always
charged on the drift-inclusive basis.

Sharpe ratios use the 3-month Treasury bill rate saved in
results/tbill_3m_monthly.csv, with the flat 2% next to it. The Sharpe
difference against the benchmark has a 90% paired bootstrap interval (5,000
resamples, seed 42) on three bases: gross (the headline), net on the drift
basis and net on the existing basis. The flat 2% difference has its interval
from bootstrap_sharpe_diff, for comparison only. The headline holds 18
intervals, so about two would exclude zero by chance alone.

Sensitivities (Amendments 10 to 13): Value and Combined without the 24 names
of Amendment 11 and without the 37 names of Amendment 12, each against the
equal-weight portfolio of the usable names that remain. No winsorised
portfolio is run. A check is printed that winsorising does not change the
Value top decile or top quintile.

SPY is reference only, read from the cache written by run_universe_spy.py,
and checked against results/spy_reference_monthly_returns.csv within 1e-6 in
every month of 2021 to 2026. The survivorship diagnostic compares the mean
monthly return of names later removed from the index with names that stayed,
for both usable sets. It is descriptive and is not a correction.

Outputs are new files, never overwritten: if any exists the script stops
before doing anything, nothing is written until every frame is built, and
each file is opened with mode "x".
  results/universe_study_portfolio_returns.csv
  results/universe_study_portfolio_summary.csv
  results/universe_study_survivorship.csv
  results/universe_study_portfolio_returns_excl_24.csv
  results/universe_study_portfolio_summary_excl_24.csv
  results/universe_study_portfolio_returns_excl_37.csv
  results/universe_study_portfolio_summary_excl_37.csv
Every file carries a universe_note column, and the sensitivity files a
sensitivity column.

Run after run_universe_spy.py:
  python run_universe_portfolios.py
"""
import os
import sqlite3

import pandas as pd

from run_rf_sensitivity import TBILL_PATH, load_tbill_yields, rf_on_return_dates
from run_universe_gates import run_gate2, run_gate1a_momentum, run_count_check, run_value_path, stop_on_failures
from run_universe_signals import load_inputs, stop_if_outputs_exist
from src.backtest import calculate_monthly_returns
from src.universe import FEASIBILITY_DB_PATH, survivor_group
from src.universe_study import read_month_end_prices, evaluation_dates, study_periods, UNIVERSE_NOTE
from src.universe_value import (
    signal_sets, signal_set_failures, registered_list_failures, HEADLINE, WINSORISED, EXCLUDING_24, EXCLUDING_37,
)
from src.universe_portfolio import (
    top_group_weights, universe_weights, portfolio_series, top_group_changes, strategy_summary, reference_summary,
    returns_frame, survivorship_monthly, survivorship_summary, spy_cache_path, spy_month_end_returns,
    spy_overlap_failures, stage3_count_failures, portfolio_outputs, SIZES, GROSS, NET_DRIFT, HEADLINE_BASIS,
    MOMENTUM_BENCHMARK, VALUE_BENCHMARK, SPY_LABEL, PORTFOLIO_SETS,
)

N_SIMS = 5000
SEED = 42
SPY_SAVED_PATH = "results/spy_reference_monthly_returns.csv"
BY_YEAR_PATH = "results/universe_coverage_by_year.csv"
MOMENTUM_COUNTS_PATH = "results/universe_study_monthly_counts_momentum.csv"
VALUE_COUNTS_PATHS = {
    HEADLINE: "results/universe_study_monthly_counts_value_combined.csv",
    EXCLUDING_24: "results/universe_study_monthly_counts_value_combined_excl_24.csv",
    EXCLUDING_37: "results/universe_study_monthly_counts_value_combined_excl_37.csv",
}
STRATEGIES = {HEADLINE: ["Momentum", "Value", "Combined"], EXCLUDING_24: ["Value", "Combined"],
              EXCLUDING_37: ["Value", "Combined"]}
MOMENTUM_SET, VALUE_SET = "Momentum usable", "Value and Combined usable"


# ---------------------------------------------------------------------------
# Inputs and checks
# ---------------------------------------------------------------------------

def load_rf(dates: pd.DatetimeIndex) -> pd.Series:
    """The saved TB3MS file only. load_tbill_yields() would download and write it if it were missing."""
    if not os.path.exists(TBILL_PATH):
        raise SystemExit(f"{TBILL_PATH} is missing. This stage does not download it. Stopping.")
    return rf_on_return_dates(load_tbill_yields(), dates)


def load_spy(calendar: pd.Series, dates: pd.DatetimeIndex) -> pd.Series:
    path = spy_cache_path()
    if not path.exists():
        raise SystemExit(f"{path} is missing. Run run_universe_spy.py first. Stopping.")
    daily = pd.read_csv(path, index_col="Date", parse_dates=True)
    spy = spy_month_end_returns(daily, calendar).reindex(dates)
    saved = pd.read_csv(SPY_SAVED_PATH, index_col="date", parse_dates=True)["SPY"]
    failures = [f"{d:%Y-%m}: no SPY return" for d in spy.index[spy.isna()]]
    failures += spy_overlap_failures(spy, saved)
    print(f"\nSPY check: {spy.notna().sum()} of {len(dates)} months, {len(saved)} months compared with {SPY_SAVED_PATH}")
    stop_on_failures("SPY check", failures)
    return spy


def load_groups(tickers: list[str]) -> pd.Series:
    """Removed or stayed for every ticker (Amendment 6, item 6)."""
    conn = sqlite3.connect(f"file:{FEASIBILITY_DB_PATH}?mode=ro", uri=True)
    intervals = pd.read_sql_query("SELECT * FROM index_membership", conn)
    conn.close()
    return pd.Series({t: survivor_group(intervals, t) for t in tickers})


def run_stage3_count_check(sets: dict):
    """Usable names per month equal the committed Stage 3 counts, for every set the portfolios use."""
    failures = stage3_count_failures(sets[HEADLINE]["Momentum"].notna().sum(axis=1),
                                     pd.read_csv(MOMENTUM_COUNTS_PATH), "usable_momentum", "Momentum")
    for name in PORTFOLIO_SETS:
        failures += stage3_count_failures(sets[name]["Value"].notna().sum(axis=1),
                                          pd.read_csv(VALUE_COUNTS_PATHS[name]), "usable_value_combined", name)
    stop_on_failures("Stage 3 count check", failures)


# ---------------------------------------------------------------------------
# Portfolios and frames
# ---------------------------------------------------------------------------

def benchmark_for(strategy: str) -> str:
    return MOMENTUM_BENCHMARK if strategy == "Momentum" else VALUE_BENCHMARK


def build_set(signals: dict, strategies: list[str], returns: pd.DataFrame) -> tuple[dict, dict]:
    """({(strategy, size): series}, {benchmark: series}) for one signal set."""
    portfolios = {(strategy, size): portfolio_series(top_group_weights(signals[strategy], q), returns)
                  for strategy in strategies for size, q in SIZES.items()}
    benchmarks = {VALUE_BENCHMARK: portfolio_series(universe_weights(signals["Value"].notna()), returns)}
    if "Momentum" in strategies:
        benchmarks[MOMENTUM_BENCHMARK] = portfolio_series(universe_weights(signals["Momentum"].notna()), returns)
    return portfolios, benchmarks


def summary_frame(portfolios: dict, benchmarks: dict, rf: pd.Series, periods: dict, label: str,
                  spy: pd.Series | None = None) -> pd.DataFrame:
    parts = []
    for i, ((strategy, size), series) in enumerate(portfolios.items(), start=1):
        print(f"  {label}: bootstrap {i}/{len(portfolios)}, {strategy} {size}")
        name = benchmark_for(strategy)
        parts.append(strategy_summary(strategy, size, series, benchmarks[name], name, rf, periods, N_SIMS, SEED))
    for name, series in benchmarks.items():
        parts.append(reference_summary(name, series, [GROSS, NET_DRIFT], rf, periods))
    if spy is not None:
        parts.append(reference_summary(SPY_LABEL, spy.to_frame(GROSS), [GROSS], rf, periods))
    return pd.concat(parts, ignore_index=True)


def returns_long(portfolios: dict, benchmarks: dict, rf: pd.Series, spy: pd.Series | None = None) -> pd.DataFrame:
    parts = [returns_frame(strategy, size, series, rf) for (strategy, size), series in portfolios.items()]
    parts += [returns_frame(name, None, series, rf) for name, series in benchmarks.items()]
    if spy is not None:
        parts.append(returns_frame(SPY_LABEL, None, spy.to_frame(GROSS), rf))
    return pd.concat(parts, ignore_index=True)


def held_without_return_failures(built: dict) -> list[str]:
    """The universe note states that no usable name lacks a return, so no held name may lack one."""
    failures = []
    for name, (portfolios, benchmarks) in built.items():
        for key, series in {**portfolios, **benchmarks}.items():
            missing = int(series["names_without_return"].sum())
            if missing:
                failures.append(f"{name} {key}: {missing} held name-months with no return")
    return failures


def build_frames(built: dict, sets: dict, returns: pd.DataFrame, rf: pd.Series, spy: pd.Series,
                 groups: pd.Series) -> dict:
    """Every output frame, keyed as in portfolio_outputs(). Nothing is written here."""
    periods = study_periods()
    frames = {}
    for name, (portfolios, benchmarks) in built.items():
        headline = name == HEADLINE
        frames[(name, "portfolio_returns")] = returns_long(portfolios, benchmarks, rf, spy if headline else None)
        frames[(name, "portfolio_summary")] = summary_frame(portfolios, benchmarks, rf, periods, name,
                                                            spy if headline else None)

    survivorship = [survivorship_summary(survivorship_monthly(sets[HEADLINE][signal].notna(), returns, groups),
                                         periods, label)
                    for signal, label in (("Momentum", MOMENTUM_SET), ("Value", VALUE_SET))]
    frames[(HEADLINE, "survivorship")] = pd.concat(survivorship, ignore_index=True)

    return {key: frame if key[0] == HEADLINE else frame.assign(sensitivity=key[0]) for key, frame in frames.items()}


# ---------------------------------------------------------------------------
# Printout
# ---------------------------------------------------------------------------

def print_first_month(built: dict, dates: pd.DatetimeIndex):
    first = dates[0]
    print(f"\nFirst month {first:%Y-%m}: purchase from cash for every portfolio and benchmark (Amendment 13, decision 9)")
    for name, (portfolios, benchmarks) in built.items():
        for key, series in {**portfolios, **benchmarks}.items():
            print(f"  {name:9s} {str(key):40s} turnover existing {series.loc[first, 'turnover_existing']:.4f}, "
                  f"drift {series.loc[first, 'turnover_drift']:.4f}")


def print_names_held(built: dict):
    print("\nNames held per month (min, median, max):")
    for name, (portfolios, benchmarks) in built.items():
        for key, series in {**portfolios, **benchmarks}.items():
            held = series["names_held"]
            print(f"  {name:9s} {str(key):40s} {held.min()}, {held.median():.0f}, {held.max()}")


def print_summary(frames: dict):
    tests = ["period", "strategy", "size", "basis", "sharpe_tbill", "benchmark_sharpe_tbill", "sharpe_diff_tbill",
             "ci_90_lower_tbill", "ci_90_upper_tbill", "significant_tbill", "sharpe_diff_flat_2pct",
             "ci_90_lower_flat_2pct", "ci_90_upper_flat_2pct"]
    levels = ["period", "strategy", "size", "basis", "months", "total_return", "annualized_return",
              "annualized_volatility", "sharpe_tbill", "sharpe_flat_2pct", "max_drawdown",
              "avg_turnover_existing", "avg_turnover_drift"]
    with pd.option_context("display.width", 250, "display.max_columns", 30, "display.max_rows", 500):
        for name in PORTFOLIO_SETS:
            summary = frames[(name, "portfolio_summary")]
            tested = summary["sharpe_diff_tbill"].notna()
            print(f"\nSharpe differences against the benchmark, {name} (gross is the headline basis):")
            print(summary.loc[tested, tests].round(4).to_string(index=False))
            print(f"\nLevels and turnover, {name}:")
            print(summary[levels].round(4).to_string(index=False))

    headline = frames[(HEADLINE, "portfolio_summary")]
    read = headline[headline["headline_test"]]
    print(f"\nHeadline tests: {len(read)} intervals at the 90% level (gross, Treasury bill rate). With no effect at all, "
          f"about {0.1 * len(read):.1f} would exclude zero by chance alone, so no interval is read on its own.")
    print(f"Headline intervals that exclude zero: {int(read['significant_tbill'].sum())}")


def print_winsorised_check(sets: dict):
    print("\nWinsorised P/B check (Amendment 13, decision 6, report only):")
    for size, q in SIZES.items():
        changed = top_group_changes(sets[HEADLINE]["Value"], sets[WINSORISED]["Value"], q)
        print(f"  Value {size}: months whose holdings change under winsorising: {len(changed)} {changed}")


def print_survivorship(frames: dict):
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print("\nSurvivorship diagnostic (descriptive, not a correction):")
        print(frames[(HEADLINE, "survivorship")].round(5).to_string(index=False))
    by_year = pd.read_csv(BY_YEAR_PATH)
    first = by_year[by_year["year"] == by_year["year"].min()].set_index("group")
    print(f"Phase 3 context, {by_year['year'].min()}: share of member-months usable for Momentum, removed "
          f"{first.loc['removed', 'share_usable_momentum']:.1%} against stayed {first.loc['stayed', 'share_usable_momentum']:.1%}; "
          f"for Value and Combined, removed {first.loc['removed', 'share_usable_value_combined']:.1%} against stayed "
          f"{first.loc['stayed', 'share_usable_value_combined']:.1%} ({BY_YEAR_PATH}).")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def main():
    outputs = portfolio_outputs()
    stop_if_outputs_exist(outputs.values())
    calendar, usability = load_inputs()
    dates = evaluation_dates()

    run_gate2(calendar)
    prices = read_month_end_prices(calendar)
    run_gate1a_momentum(prices, usability)
    run_count_check(prices, usability)
    path = run_value_path(calendar, prices, usability)
    stop_on_failures("Registered 24-name list", registered_list_failures(path["jumps"]))

    returns = calculate_monthly_returns(prices)
    sets = signal_sets(path["momentum"], path["value"])
    failures = []
    for name in PORTFOLIO_SETS:
        failures += signal_set_failures(name, sets[name], returns)
    stop_on_failures("Signal set checks", failures)
    run_stage3_count_check(sets)

    rf = load_rf(dates)
    print(f"\nTreasury bill rate: {len(rf)} months from {TBILL_PATH}, every month has a rate.")
    spy = load_spy(calendar, dates)
    groups = load_groups(list(prices.columns))

    built = {name: build_set(sets[name], STRATEGIES[name], returns) for name in PORTFOLIO_SETS}
    stop_on_failures("Held names with a return", held_without_return_failures(built))

    print(f"\nBootstrap: {N_SIMS} resamples, seed {SEED}, on three bases with the Treasury bill rate and the flat 2%.")
    frames = build_frames(built, sets, returns, rf, spy, groups)
    stop_if_outputs_exist(outputs.values())
    for key, frame in frames.items():
        frame.assign(universe_note=UNIVERSE_NOTE).to_csv(outputs[key], index=False, mode="x")
        print(f"Wrote {outputs[key]} ({len(frame)} rows)")

    print_first_month(built, dates)
    print_names_held(built)
    print_summary(frames)
    print_winsorised_check(sets)
    print_survivorship(frames)
    print(f"\nHeadline basis for reading: {HEADLINE_BASIS}. The re-test months are already known from the published "
          f"study and are not out-of-sample evidence.")


if __name__ == "__main__":
    main()
