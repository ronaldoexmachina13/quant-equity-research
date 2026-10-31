"""
Phase 4, Stage 2: reproduction gates (LIMITATIONS_PLAN.md, Phase 4 detailed
design and Amendments 8 to 10).

Reads the Phase 3 cache and database/universe_feasibility.db, and opens
database/quant_research.db through the existing loaders. It prints its checks
and writes no result file.

With --momentum-only, the only mode built so far, it runs the part that needs
no book value or split data:
- revised Gate 2: for each of the 17 stocks, the ratio of cached to stored
  month-end price is constant within 1e-5, with all level differences printed;
- Gate 1a, Momentum and benchmark: on the 17 stocks from January 2021 to
  December 2024, gross Sharpe within 1e-4 of
  results/strategy_comparison_full_period.csv, with a report-only comparison
  of Momentum holdings against the portfolio_weights table;
- the usable_momentum counts, and the delisting_gap_momentum counts, match
  results/universe_coverage_monthly.csv exactly in every month.
Any failure stops the run with a non-zero exit.
"""
import argparse
import sqlite3

import pandas as pd

from config import UNIVERSE
from src.backtest import calculate_monthly_returns, calculate_benchmark_returns
from src.database import get_connection
from src.factors import load_prices
from src.signal_eval import monthly_counts, MIN_NAMES_PER_MONTH
from src.universe import FEASIBILITY_DB_PATH
from src.universe_study import (
    evaluation_dates, load_calendar, load_usability, read_month_end_prices, momentum_signal,
    count_mismatches, price_ratio_report, price_ratio_failures, top_n_returns, sharpe_failures,
    holdings_differences,
)

COVERAGE_PATH = "results/universe_coverage_monthly.csv"
PUBLISHED_PATH = "results/strategy_comparison_full_period.csv"
GATE1_START, GATE1_END = "2021-01", "2024-12"


def stop_on_failures(label: str, failures: list[str]):
    if failures:
        print(f"\n{label} FAILED. Stopping. Mismatches:")
        for failure in failures:
            print("  " + failure)
        raise SystemExit(1)
    print(f"{label} passed.")


def run_gate2(calendar: pd.Series):
    """Revised Gate 2 on the 17 study stocks."""
    cached = read_month_end_prices(calendar, tickers=UNIVERSE)
    report = price_ratio_report(cached, load_prices()[UNIVERSE])
    print(f"\nGate 2: cached against stored month-end prices, {int(report['months'].max())} months")
    print(report.to_string(index=False, float_format=lambda x: f"{x:.3g}"))
    stop_on_failures("Gate 2", price_ratio_failures(report))


def stored_momentum_holdings() -> pd.DataFrame:
    conn = get_connection()
    rows = pd.read_sql_query("SELECT date, ticker FROM portfolio_weights WHERE strategy = 'momentum'", conn)
    conn.close()
    return rows


def run_gate1a_momentum(prices: pd.DataFrame, usability: pd.DataFrame):
    """Momentum and benchmark on the 17 stocks through the study's own month-end frame and mask."""
    study = prices[UNIVERSE]
    returns = calculate_monthly_returns(study)
    dates = evaluation_dates(GATE1_START, GATE1_END)
    gross, weights = top_n_returns(momentum_signal(study, usability, dates), returns, dates)
    series = {"Momentum": gross, "Benchmark": calculate_benchmark_returns(returns).loc[dates]}

    published = pd.read_csv(PUBLISHED_PATH, index_col="label")
    print(f"\nGate 1a, Momentum and benchmark: {len(dates)} months, against {PUBLISHED_PATH}")
    differing = holdings_differences(weights, stored_momentum_holdings())
    print(f"  Momentum holdings differ from portfolio_weights in {len(differing)} months (report only): {differing}")
    stop_on_failures("Gate 1a, Momentum and benchmark", sharpe_failures(series, published))


def run_count_check(prices: pd.DataFrame, usability: pd.DataFrame):
    """The study's own usable and no-return counts against the Phase 3 coverage file, every month."""
    signal = momentum_signal(prices, usability)
    counts = monthly_counts(signal, calculate_monthly_returns(prices))
    coverage = pd.read_csv(COVERAGE_PATH)

    print(f"\nCount check against {COVERAGE_PATH}: {len(counts)} months")
    print(f"  Usable for Momentum: {counts['usable'].min()} to {counts['usable'].max()} names a month; "
          f"{counts['no_return'].sum()} name-months with no return")
    failures = []
    for label, found, column in [("usable_momentum", counts["usable"], "usable_momentum"),
                                 ("delisting_gap_momentum", counts["no_return"], "delisting_gap_momentum")]:
        mismatches = count_mismatches(found, coverage, column)
        failures += [f"{label} {r.month}: found {r.found}, expected {r.expected}" for r in mismatches.itertuples()]
    below = counts.index[counts["usable"] < MIN_NAMES_PER_MONTH]
    failures += [f"{d.strftime('%Y-%m')}: below {MIN_NAMES_PER_MONTH} usable names" for d in below]
    stop_on_failures("Count check", failures)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--momentum-only", action="store_true", help="run the gates that need no book value or splits")
    if not parser.parse_args().momentum_only:
        raise SystemExit("The Value path is not built yet. Run with --momentum-only.")

    conn = sqlite3.connect(f"file:{FEASIBILITY_DB_PATH}?mode=ro", uri=True)
    calendar = load_calendar(conn)
    usability = load_usability(conn)
    conn.close()

    run_gate2(calendar)
    prices = read_month_end_prices(calendar)
    print(f"\nMonth-end prices: {prices.shape[0]} months, {prices.shape[1]} tickers")
    run_gate1a_momentum(prices, usability)
    run_count_check(prices, usability)
    print("\nMomentum path: all gates passed. No result file was written.")


if __name__ == "__main__":
    main()
