"""
Phase 4, Stage 3: signal-level tests (LIMITATIONS_PLAN.md, Phase 4 detailed
design and Amendments 8 to 10).

With --momentum-only, the only mode built so far (Amendment 10, item 7), the
script reruns the Momentum gates and then computes, for the new test
(2012-2020), the re-test (2021-2026) and the full period:
- rank IC: mean monthly IC, 90% bootstrap interval, share of positive months;
- quintile spread: mean monthly and annualised, with a 90% bootstrap interval;
- single-signal Fama-MacBeth: mean monthly slope with a 90% bootstrap interval.
Intervals use 5,000 resamples and seed 42.

The re-test months are already known from the published study, so they are
not out-of-sample evidence. No result here chooses or changes a specification.

Outputs are new files, never overwritten: if any exists the script stops
before doing anything, and each is opened with mode "x".
  results/universe_study_monthly_counts_momentum.csv
  results/universe_study_ic_monthly_momentum.csv
  results/universe_study_spread_monthly_momentum.csv
  results/universe_study_signal_summary_momentum.csv
Every file carries a universe_note column.
"""
import argparse
import sqlite3
from pathlib import Path

import pandas as pd

from run_universe_gates import COVERAGE_PATH, run_gate2, run_gate1a_momentum, run_count_check
from src.backtest import calculate_monthly_returns
from src.signal_eval import (
    rank_ic, quintile_spread, monthly_statistic, monthly_counts, fama_macbeth_slopes, summarize_signal,
)
from src.universe import FEASIBILITY_DB_PATH
from src.universe_study import (
    load_calendar, load_usability, read_month_end_prices, momentum_signal,
    study_periods, period_labels, UNIVERSE_NOTE,
)

SIGNAL = "Momentum"
N_SIMS = 5000
SEED = 42
OUTPUTS = {name: Path("results") / f"universe_study_{name}_momentum.csv"
           for name in ["monthly_counts", "ic_monthly", "spread_monthly", "signal_summary"]}


def stop_if_outputs_exist():
    existing = [str(p) for p in OUTPUTS.values() if p.exists()]
    if existing:
        raise SystemExit(f"Output files already exist and are never overwritten: {existing}. Stopping.")


def monthly_frame(dates: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame({"date": dates, "period": period_labels(dates).values})


def build_counts(counts: pd.DataFrame, coverage: pd.DataFrame) -> pd.DataFrame:
    frame = monthly_frame(counts.index)
    frame["universe_size"] = coverage["members"].values
    frame["usable_momentum"] = counts["usable"].values
    frame["no_return_momentum"] = counts["no_return"].values
    return frame


def build_monthly_series(series: pd.Series, column: str) -> pd.DataFrame:
    frame = monthly_frame(series.index)
    frame.insert(2, "signal", SIGNAL)
    frame[column] = series.values
    return frame


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--momentum-only", action="store_true", help="run the Momentum part of Stage 3")
    if not parser.parse_args().momentum_only:
        raise SystemExit("The Value and Combined part is not built yet. Run with --momentum-only.")
    stop_if_outputs_exist()

    conn = sqlite3.connect(f"file:{FEASIBILITY_DB_PATH}?mode=ro", uri=True)
    calendar = load_calendar(conn)
    usability = load_usability(conn)
    conn.close()

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
        "monthly_counts": build_counts(counts, coverage),
        "ic_monthly": build_monthly_series(ic, "rank_ic"),
        "spread_monthly": build_monthly_series(spread, "quintile_spread"),
        "signal_summary": summary,
    }
    for name, frame in outputs.items():
        frame.assign(universe_note=UNIVERSE_NOTE).to_csv(OUTPUTS[name], index=False, mode="x")
        print(f"Wrote {OUTPUTS[name]} ({len(frame)} rows)")

    with pd.option_context("display.width", 220, "display.max_columns", 20):
        print("\n" + summary.round(5).to_string(index=False))


if __name__ == "__main__":
    main()
