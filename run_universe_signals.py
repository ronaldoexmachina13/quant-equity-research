"""
Phase 4, Stage 3: signal-level tests (LIMITATIONS_PLAN.md, Phase 4 detailed
design and Amendments 8 to 12).

The script runs one of two parts (Amendment 10, item 7). Portfolio tests are a
separate stage. Both parts rerun their gates and then compute, for the new test
(2012-2020), the re-test (2021-2026) and the full period:
- rank IC: mean monthly IC, 90% bootstrap interval, share of positive months;
- quintile spread: mean monthly and annualised, with a 90% bootstrap interval;
- single-signal Fama-MacBeth: mean monthly slope with a 90% bootstrap interval.
Intervals use 5,000 resamples and seed 42.

The re-test months are already known from the published study, so they are
not out-of-sample evidence. No result here chooses or changes a specification.

With --value-combined, all of this runs in one process for Value and Combined
on four signal sets, with the joint Fama-MacBeth of Momentum and Value:
- headline: raw P/B after the validity rule of Amendment 11, decision 1;
- winsorised_pb: P/B capped at the 1st and 99th percentiles of each month, for
  Combined and for the two Value Fama-MacBeth tests (Amendment 11, decision 3);
- excl_24: without the 24 names of Amendment 11, decision 4;
- excl_37: without the 37 names of Amendment 12.
The three extras are labelled sensitivities and change no headline. Nothing is
written until every set is built, so a failure leaves no partial set.

Outputs are new files, never overwritten: if any exists the script stops
before doing anything, and each is opened with mode "x".
  With --momentum-only:
    results/universe_study_monthly_counts_momentum.csv
    results/universe_study_ic_monthly_momentum.csv
    results/universe_study_spread_monthly_momentum.csv
    results/universe_study_signal_summary_momentum.csv
  With --value-combined, 17 files:
    results/universe_study_{part}_value_combined.csv
    results/universe_study_{part}_value_combined_{extra}.csv
    results/universe_study_bv_jumps.csv
    where part is monthly_counts, ic_monthly, spread_monthly or signal_summary,
    and extra is winsorised_pb, excl_24 or excl_37.
Every file carries a universe_note column, and the extras a sensitivity column.
"""
import argparse
import sqlite3
from pathlib import Path

import pandas as pd

from run_universe_gates import (
    COVERAGE_PATH, run_gate2, run_gate1a_momentum, run_count_check, run_value_path, stop_on_failures,
)
from src.backtest import calculate_monthly_returns
from src.signal_eval import (
    rank_ic, quintile_spread, monthly_statistic, monthly_counts, fama_macbeth_slopes, summarize_signal,
)
from src.universe import FEASIBILITY_DB_PATH
from src.universe_study import (
    load_calendar, load_usability, read_month_end_prices, momentum_signal,
    study_periods, counts_frame, series_frame, UNIVERSE_NOTE,
)
from src.universe_value import (
    value_combined_outputs, existing_outputs, signal_sets, signal_set_frames, signal_set_failures,
    registered_list_failures, jump_report_frame, HEADLINE, WINSORISED, EXCLUDING_24, EXCLUDING_37,
    EXTREME_MOVE_LIST, AMENDMENT_12_LIST, JUMP_REPORT,
)

SIGNAL = "Momentum"
N_SIMS = 5000
SEED = 42
OUTPUTS = {name: Path("results") / f"universe_study_{name}_momentum.csv"
           for name in ["monthly_counts", "ic_monthly", "spread_monthly", "signal_summary"]}


def stop_if_outputs_exist(paths):
    existing = existing_outputs(paths)
    if existing:
        raise SystemExit(f"Output files already exist and are never overwritten: {existing}. Stopping.")


def load_inputs() -> tuple[pd.Series, pd.DataFrame]:
    conn = sqlite3.connect(f"file:{FEASIBILITY_DB_PATH}?mode=ro", uri=True)
    calendar = load_calendar(conn)
    usability = load_usability(conn)
    conn.close()
    return calendar, usability


def run_momentum():
    stop_if_outputs_exist(OUTPUTS.values())
    calendar, usability = load_inputs()

    run_gate2(calendar)
    prices = read_month_end_prices(calendar)
    run_gate1a_momentum(prices, usability)
    run_count_check(prices, usability)

    signal = momentum_signal(prices, usability)
    returns = calculate_monthly_returns(prices)
    counts = monthly_counts(signal, returns)
    if counts["no_return"].sum() != 0:
        raise SystemExit("A month has names with no return, so the universe note would be false. Stopping.")

    coverage = pd.read_csv(COVERAGE_PATH)
    ic = monthly_statistic(signal, returns, rank_ic)
    spread = monthly_statistic(signal, returns, quintile_spread)
    slopes = fama_macbeth_slopes({SIGNAL: signal}, returns)[SIGNAL]
    summary = summarize_signal(SIGNAL, ic, spread, {"fama_macbeth_single": slopes}, study_periods(),
                               n_sims=N_SIMS, seed=SEED)

    outputs = {
        "monthly_counts": counts_frame(counts, coverage, "momentum"),
        "ic_monthly": series_frame(ic, SIGNAL, "rank_ic"),
        "spread_monthly": series_frame(spread, SIGNAL, "quintile_spread"),
        "signal_summary": summary,
    }
    for name, frame in outputs.items():
        frame.assign(universe_note=UNIVERSE_NOTE).to_csv(OUTPUTS[name], index=False, mode="x")
        print(f"Wrote {OUTPUTS[name]} ({len(frame)} rows)")

    with pd.option_context("display.width", 220, "display.max_columns", 20):
        print("\n" + summary.round(5).to_string(index=False))


def build_value_combined(path: dict, returns: pd.DataFrame, coverage: pd.DataFrame) -> dict:
    """Every output frame, keyed as in value_combined_outputs(). Nothing is written here."""
    frames = {}
    for name, signals in signal_sets(path["momentum"], path["value"]).items():
        built = signal_set_frames(signals, returns, coverage, study_periods(), value_slopes_only=name == WINSORISED,
                                  n_sims=N_SIMS, seed=SEED)
        labelled = built if name == HEADLINE else {part: frame.assign(sensitivity=name) for part, frame in built.items()}
        frames.update({(name, part): frame for part, frame in labelled.items()})
    frames[("report", JUMP_REPORT)] = jump_report_frame(path["jumps"], path["units"], path["checks"])
    return frames


def print_value_combined_report(frames: dict, tickers: pd.Index):
    print("\nNames per month and months by set:")
    for name in (HEADLINE, WINSORISED, EXCLUDING_24, EXCLUDING_37):
        counts = frames[(name, "monthly_counts")]
        usable = counts["usable_value_combined"]
        lowest = counts.loc[usable.idxmin(), "date"].strftime("%Y-%m")
        by_period = counts["period"].value_counts().to_dict()
        print(f"  {name:14s} {len(counts)} months {by_period}; names min {usable.min()} ({lowest}), "
              f"median {usable.median():.0f}, max {usable.max()}; name-months {usable.sum()}; "
              f"no return {counts['no_return_value_combined'].sum()}; months below 100 names: {int((usable < 100).sum())}")

    for label, names in [(EXCLUDING_24, EXTREME_MOVE_LIST), (EXCLUDING_37, AMENDMENT_12_LIST)]:
        print(f"  {label}: {len(names)} names listed, not in the data: {[n for n in names if n not in tickers]}")

    print(f"\nJump report by type: {frames[('report', JUMP_REPORT)]['record_type'].value_counts().to_dict()}")
    with pd.option_context("display.width", 220, "display.max_columns", 20, "display.max_rows", 500):
        for name in (HEADLINE, WINSORISED, EXCLUDING_24, EXCLUDING_37):
            print(f"\nSignal summary, {name}:")
            print(frames[(name, "signal_summary")].drop(columns=["sensitivity"], errors="ignore").round(5).to_string(index=False))


def run_value_combined():
    outputs = value_combined_outputs()
    stop_if_outputs_exist(outputs.values())
    calendar, usability = load_inputs()

    run_gate2(calendar)
    prices = read_month_end_prices(calendar)
    run_gate1a_momentum(prices, usability)
    run_count_check(prices, usability)
    path = run_value_path(calendar, prices, usability)
    stop_on_failures("Registered 24-name list", registered_list_failures(path["jumps"]))

    returns = calculate_monthly_returns(prices)
    failures = []
    for name, signals in signal_sets(path["momentum"], path["value"]).items():
        failures += signal_set_failures(name, signals, returns)
    stop_on_failures("Signal set checks", failures)

    frames = build_value_combined(path, returns, pd.read_csv(COVERAGE_PATH))
    stop_if_outputs_exist(outputs.values())
    for key, frame in frames.items():
        frame.assign(universe_note=UNIVERSE_NOTE).to_csv(outputs[key], index=False, mode="x")
        print(f"Wrote {outputs[key]} ({len(frame)} rows)")

    print_value_combined_report(frames, prices.columns)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    part = parser.add_mutually_exclusive_group(required=True)
    part.add_argument("--momentum-only", action="store_true", help="run the Momentum part of Stage 3")
    part.add_argument("--value-combined", action="store_true", help="run the Value and Combined part of Stage 3")
    if parser.parse_args().momentum_only:
        run_momentum()
    else:
        run_value_combined()


if __name__ == "__main__":
    main()
