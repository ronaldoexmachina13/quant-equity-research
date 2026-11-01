"""
Phase 4, Stage 2: reproduction gates (LIMITATIONS_PLAN.md, Phase 4 detailed
design and Amendments 8 to 11).

Reads the Phase 3 cache and database/universe_feasibility.db, and opens
database/quant_research.db through the existing loaders. It prints its checks
and writes no result file.

With --momentum-only it runs the part that needs no book value or split data:
- revised Gate 2: for each of the 17 stocks, the ratio of cached to stored
  month-end price is constant within 1e-5, with all level differences printed;
- Gate 1a, Momentum and benchmark: on the 17 stocks from January 2021 to
  December 2024, gross Sharpe within 1e-4 of
  results/strategy_comparison_full_period.csv, with a report-only comparison
  of Momentum holdings against the portfolio_weights table;
- the usable_momentum counts, and the delisting_gap_momentum counts, match
  results/universe_coverage_monthly.csv exactly in every month.

Without it, the script also runs the Value and Combined path:
- every ticker has a saved split file and a cached book value source;
- the validity rule for units errors (Amendment 11, decision 1), already in
  the book value records;
- the filing-date rule on every split, and the jump report (Amendment 8),
  with the names that still move by more than a factor of 100 (Amendment 11,
  decisions 2 and 4);
- the range of P/B after the validity rule, with the remaining cases listed
  (Amendment 11, decision 2);
- the usable set under the fixed rule, reconciled by name to the Phase 3
  coverage file, closing exactly every month, and the 200 and 100 name
  thresholds re-checked (Amendment 10, item 1);
- Gate 1a, Value and Combined: the published definition with the stored
  book_value table as input, within 1e-4 of the published gross Sharpe;
- Gate 1b, report only: the fixed rule against the stored table by stock and
  month, and the months in which the Value top-5 holdings differ.
A gate failure stops the run with a non-zero exit. Gate 1b cannot fail.
"""
import argparse
import sqlite3

import numpy as np
import pandas as pd

from config import UNIVERSE, IN_SAMPLE_END, OUT_OF_SAMPLE_START
from src.backtest import calculate_monthly_returns, calculate_benchmark_returns
from src.database import get_connection, load_book_value
from src.factors import load_prices
from src.signal_eval import monthly_counts, MIN_NAMES_PER_MONTH
from src.split_adjust import filled_book_value
from src.universe import (
    FEASIBILITY_DB_PATH, FIRST_PRICE_MONTH, EVALUATION_END, cache_dir, make_cached_company_facts,
)
from src.universe_study import (
    evaluation_dates, load_calendar, load_usability, read_month_end_prices, momentum_signal, usable_mask,
    count_mismatches, price_ratio_report, price_ratio_failures, top_n_returns, sharpe_failures,
    holdings_differences, study_periods,
)
from src.universe_value import (
    load_split_history, apply_split_cutoff, build_records, restate_all, value_usable_mask, value_signal,
    combined_signal, reconcile_usable, reconciliation_failures, book_value_jumps, split_event_check,
    extreme_move_names, pb_range, pb_cases, SPLIT_CUTOFF, EXTREME_MOVE_FACTOR, LOW_PB,
)

COVERAGE_PATH = "results/universe_coverage_monthly.csv"
PUBLISHED_PATH = "results/strategy_comparison_full_period.csv"
GATE1_START, GATE1_END = "2021-01", "2024-12"
TOP_DECILE_MINIMUM = 200   # Phase 4: decile portfolios need at least this many usable names


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


def stored_holdings(strategy: str) -> pd.DataFrame:
    conn = get_connection()
    rows = pd.read_sql_query("SELECT date, ticker FROM portfolio_weights WHERE strategy = ?", conn, params=(strategy,))
    conn.close()
    return rows


def load_splits_or_stop(tickers: list[str]) -> dict:
    history, missing = load_split_history(tickers)
    if missing:
        raise SystemExit(f"{len(missing)} tickers have no split file and are never read as no splits: {missing}. "
                         "Run run_universe_splits.py. Stopping.")
    splits, ignored = apply_split_cutoff(history)
    total = sum(len(ratios) for ratios in splits.values())
    print(f"\nSplits: {total} events on or before {SPLIT_CUTOFF}, in {sum(len(r) > 0 for r in splits.values())} tickers")
    print(f"Later splits ignored and listed (Amendment 10, item 3): {len(ignored)}")
    if not ignored.empty:
        print(ignored.to_string(index=False))
    return splits


def print_split_check(checks: pd.DataFrame):
    print(f"\nFiling-date rule on every split of a stock with book value records: {len(checks)} events")
    print(f"  With a filing on both sides: {int(checks['restated_step'].notna().sum())}")
    print(f"  Restated step above a factor of 2: {int(checks['large_step'].sum())}")
    print(f"  Ratios that are not simple fractions: {int((~checks['ordinary_ratio']).sum())}")
    print(checks.round(4).to_string(index=False))


def print_jump_report(jumps: pd.DataFrame, units: pd.DataFrame, used: pd.DataFrame):
    """Printed in Stage 2 and written in Stage 3 (Amendment 10, item 4)."""
    in_universe = used.columns[used.any()]
    print(f"\nJump report: {len(jumps)} moves above a factor of 2 in {jumps['ticker'].nunique()} tickers, "
          f"{int(jumps['ticker'].isin(in_universe).sum())} of them in tickers ever usable")
    print(jumps.round(4).to_string(index=False))
    filings = units[["ticker", "filed_date"]].drop_duplicates()
    print(f"\nSuspected units errors, no book value under Amendment 11, decision 1: {len(units)} tag pairs "
          f"in {len(filings)} filings and {units['ticker'].nunique()} tickers")
    if not units.empty:
        print(units.round(2).to_string(index=False))

    extreme = jumps[jumps["factor"] > EXTREME_MOVE_FACTOR]
    names = extreme_move_names(jumps)
    print(f"\nStill above a factor of {EXTREME_MOVE_FACTOR}: {len(extreme)} moves in {len(names)} tickers, "
          f"{int(pd.Index(names).isin(in_universe).sum())} of them ever usable")
    print(extreme.round(4).to_string(index=False))
    print(f"Names for the labelled sensitivity (Amendment 11, decision 4): {names}")


def print_pb_range(value: pd.DataFrame):
    """Printed before any signal test (Amendment 11, decision 2). No threshold here is a rule."""
    print("\nRange of P/B after the validity rule, usable names:")
    rows = {"All months": pb_range(value)}
    rows.update({label: pb_range(value, dates) for label, dates in study_periods().items()})
    print(pd.DataFrame(rows).T.to_string(float_format=lambda x: f"{x:.6g}"))

    low, high = pb_cases(value)
    print(f"\nName-months with P/B below {LOW_PB}: {len(low)} in {low['ticker'].nunique()} tickers")
    print(low.to_string(index=False, float_format=lambda x: f"{x:.6g}"))
    print(f"\nHighest P/B, {len(high)} name-months:")
    print(high.to_string(index=False, float_format=lambda x: f"{x:.6g}"))


def print_reconciliation(table: pd.DataFrame):
    print(f"\nReconciliation with {COVERAGE_PATH}, {len(table)} months")
    print(f"  Phase 3 name-months {table['phase3'].sum()}, lost {table['lost'].sum()}, "
          f"gained {table['gained'].sum()}, used {table['used'].sum()}")
    print(f"  Months with a change: {int(((table['lost'] > 0) | (table['gained'] > 0)).sum())}")
    print(table.to_string(index=False, max_colwidth=120))
    for label, column in [("lost", "lost_names"), ("gained", "gained_names")]:
        names = table[column].str.split().explode().dropna()
        print(f"\nName-months {label} by ticker:\n" + names.value_counts().to_string())


def run_gate1a_value(prices: pd.DataFrame, usability: pd.DataFrame, stored: pd.DataFrame) -> pd.DataFrame:
    """Value and Combined on the 17 stocks: the published definition, with the stored table as input."""
    study = prices[UNIVERSE]
    returns = calculate_monthly_returns(study)
    dates = evaluation_dates(GATE1_START, GATE1_END)
    momentum = momentum_signal(study, usability, dates)
    value = value_signal(study, stored, usable_mask(usability, "usable_value_combined", dates, UNIVERSE))
    combined = combined_signal(momentum, value)

    series, published_names = {}, {"Value": value, "Combined": combined}
    print(f"\nGate 1a, Value and Combined: {len(dates)} months, stored book value, cached adjusted close")
    for name, signal in published_names.items():
        series[name], weights = top_n_returns(signal, returns, dates)
        differing = holdings_differences(weights, stored_holdings(name.lower()))
        print(f"  {name} holdings differ from portfolio_weights in {len(differing)} months (report only): {differing}")
    stop_on_failures("Gate 1a, Value and Combined", sharpe_failures(series, pd.read_csv(PUBLISHED_PATH, index_col="label")))
    return value


def run_gate1b(prices: pd.DataFrame, usability: pd.DataFrame, stored: pd.DataFrame, records: dict):
    """Report only: how much the published Value result depends on the arbitrary choice in the stored table."""
    month_ends = stored.index
    fixed = filled_book_value({t: records.get(t, pd.DataFrame(columns=["end_date", "filed_date", "book_value_per_share"]))
                               for t in stored.columns}, month_ends)
    relative = (fixed / stored - 1).abs()
    one_sided = fixed.isna() != stored.isna()
    table = pd.DataFrame({
        "months_differ": (relative > 1e-6).sum(),
        "months_one_side_only": one_sided.sum(),
        "largest_difference": relative.max(),
    })
    print(f"\nGate 1b (report only): fixed rule against the stored table, {len(month_ends)} months")
    print(table.to_string(float_format=lambda x: f"{x:.2%}"))
    for ticker in table.index[table["months_differ"] > 0]:
        differ = relative[ticker] > 1e-6
        print(f"  {ticker} months: {list(differ.index[differ].strftime('%Y-%m'))}")

    dates = evaluation_dates(GATE1_START, month_ends[-1].strftime("%Y-%m"))
    mask = usable_mask(usability, "usable_value_combined", dates, UNIVERSE)
    study = prices[UNIVERSE]
    returns = calculate_monthly_returns(study)
    stored_value = value_signal(study, stored, mask)
    fixed_value = value_signal(study, fixed, value_usable_mask(mask, fixed))
    _, stored_weights = top_n_returns(stored_value, returns, dates)
    _, fixed_weights = top_n_returns(fixed_value, returns, dates)
    differs = (stored_weights > 0).ne(fixed_weights > 0).any(axis=1)
    months = differs.index.strftime("%Y-%m")
    in_sample = differs.index <= pd.Timestamp(IN_SAMPLE_END)
    print(f"  Value top-5 holdings differ in {int(differs[in_sample].sum())} of {int(in_sample.sum())} in-sample months "
          f"and {int(differs[~in_sample].sum())} of {int((~in_sample).sum())} later months: {list(months[differs])}")


def run_value_path(calendar: pd.Series, prices: pd.DataFrame, usability: pd.DataFrame) -> dict:
    """Builds and checks the Value and Combined path, and returns what the signal tests need."""
    conn = sqlite3.connect(f"file:{FEASIBILITY_DB_PATH}?mode=ro", uri=True)
    ciks = dict(conn.execute("SELECT ticker, cik FROM ticker_cik WHERE cik IS NOT NULL").fetchall())
    conn.close()

    tickers = list(prices.columns)
    splits = load_splits_or_stop(tickers)
    with_cik = [t for t in tickers if t in ciks]
    read_facts = make_cached_company_facts(lambda ticker: ciks[ticker], cache_dir() / "sec" / "companyfacts")
    print(f"\nBuilding fixed-rule book value for {len(with_cik)} of {len(tickers)} tickers (the rest have no CIK)")
    records, units = build_records(with_cik, read_facts)

    stored = load_book_value()
    run_gate1a_value(prices, usability, stored)
    run_gate1b(prices, usability, stored, records)

    restated_records = restate_all(records, splits)
    checks = split_event_check(records, splits)
    print_split_check(checks)

    month_ends = evaluation_dates(FIRST_PRICE_MONTH, EVALUATION_END)
    restated = filled_book_value(restated_records, month_ends)
    close = read_month_end_prices(calendar, field="Close")

    dates = evaluation_dates()
    momentum_mask = usable_mask(usability, "usable_momentum", dates, tickers)
    phase3 = usable_mask(usability, "usable_value_combined", dates, tickers)
    used = value_usable_mask(momentum_mask, restated)
    momentum = momentum_signal(prices, usability)
    value = value_signal(close, restated, used)
    combined = combined_signal(momentum, value)

    jumps = book_value_jumps(restated)
    print_jump_report(jumps, units, used)
    print_pb_range(value)

    table = reconcile_usable(phase3, used)
    print_reconciliation(table)
    coverage = pd.read_csv(COVERAGE_PATH)
    failures = reconciliation_failures(table, coverage, value.notna().sum(axis=1))
    failures += [f"{d.strftime('%Y-%m')}: Value has {v} names, Combined {c}" for d, v, c in
                 zip(dates, value.notna().sum(axis=1), combined.notna().sum(axis=1)) if v != c]
    stop_on_failures("Reconciliation", failures)

    print(f"\nThresholds for the Value universe under the fixed rule: {table['used'].min()} to {table['used'].max()} names; "
          f"months below {TOP_DECILE_MINIMUM}: {int((table['used'] < TOP_DECILE_MINIMUM).sum())}; "
          f"months below {MIN_NAMES_PER_MONTH}: {int((table['used'] < MIN_NAMES_PER_MONTH).sum())}")
    extreme = -value.to_numpy()[np.isfinite(value.to_numpy())]
    print(f"Check of finite P/B: {extreme.size} name-months, all positive: {bool((extreme > 0).all())}")
    return {"momentum": momentum, "value": value, "jumps": jumps, "units": units, "checks": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--momentum-only", action="store_true", help="run the gates that need no book value or splits")
    momentum_only = parser.parse_args().momentum_only

    conn = sqlite3.connect(f"file:{FEASIBILITY_DB_PATH}?mode=ro", uri=True)
    calendar = load_calendar(conn)
    usability = load_usability(conn)
    conn.close()

    run_gate2(calendar)
    prices = read_month_end_prices(calendar)
    print(f"\nMonth-end prices: {prices.shape[0]} months, {prices.shape[1]} tickers")
    run_gate1a_momentum(prices, usability)
    run_count_check(prices, usability)
    print("\nMomentum path: all gates passed.")
    if not momentum_only:
        run_value_path(calendar, prices, usability)
        print("\nValue and Combined path: all gates passed.")
    print("No result file was written.")


if __name__ == "__main__":
    main()
