"""
Amendments 16 and 17 (LIMITATIONS_PLAN.md), decision 1 of Amendment 16 as detailed by Amendment 17:
sector-neutral Value and Combined, with a control on the same names. Exploratory and post-results.

Needs the raw-data cache (prices and SEC company facts), because the registered Value signal is rebuilt
exactly as in the registered run, then standardised within sector.

Variants, each with Value and Combined:
  sector_neutral        Value score standardised within sector; Combined from registered Momentum and that score,
                        both on the names that remain (names with no sector, and names in sectors with fewer than
                        10 scored names that month, are left out and counted).
  control_same_names    The registered Value score and Combined on exactly the same remaining names, with no
                        sector adjustment. Separates the effect of sector neutrality from the effect of the
                        change of universe.
Tests as in Amendment 14: rank IC, quintile spread, single Fama-MacBeth, three periods, 5,000 resamples, seed 42,
90%, with Newey-West and block-bootstrap intervals. Portfolios: top decile and top quintile, equal weight, held one
month, gross and net on both turnover bases, against the equal-weight benchmark of the remaining names, with the
paired Sharpe difference (headline basis gross).

Before anything new is built, the gates and the registered series and portfolios are rebuilt and compared with the
saved files; a difference above 1e-9 stops the run.

Run from the repository root:
  python -m scripts.universe.run_universe_sector_neutral --dry-run
  python -m scripts.universe.run_universe_sector_neutral --write
With no flag the script exits. --write refuses to start if any of the five files exists, builds everything in
memory, then writes all five with mode "x" (if one write fails, the files this run created are removed).
"""
import argparse
import hashlib
from datetime import datetime
from pathlib import Path

import pandas as pd

from scripts.universe.run_universe_extras import robustness_table
from scripts.universe.run_universe_gates import (
    run_gate2, run_gate1a_momentum, run_count_check, run_value_path, stop_on_failures,
)
from scripts.universe.run_universe_portfolios import (
    load_rf, build_set, summary_frame, returns_long, held_without_return_failures,
)
from scripts.universe.run_universe_signals import load_inputs, stop_if_outputs_exist, N_SIMS, SEED
from scripts.universe.run_universe_skip_month import run_reproduction_checks, run_portfolio_reproduction
from src.backtest import calculate_monthly_returns
from src.sector_neutral import MIN_NAMES_PER_SECTOR, restrict_to_names, sector_neutral_score
from src.signal_eval import (
    MIN_NAMES_PER_MONTH, rank_ic, quintile_spread, monthly_statistic, fama_macbeth_slopes, summarize_signal,
)
from src.universe_study import read_month_end_prices, evaluation_dates, study_periods
from src.universe_value import registered_list_failures, combined_signal, SUMMARY_COLUMNS

MEMBERSHIP_PATH = "results/universe_membership.csv"
SAVED_PORTFOLIO_SUMMARY = "results/universe_study_portfolio_summary.csv"
OUTPUTS = {
    "counts": "results/universe_study_sector_neutral_counts.csv",
    "signal_summary": "results/universe_study_sector_neutral_signal_summary.csv",
    "inference_robustness": "results/universe_study_sector_neutral_inference_robustness.csv",
    "portfolio_returns": "results/universe_study_sector_neutral_portfolio_returns.csv",
    "portfolio_summary": "results/universe_study_sector_neutral_portfolio_summary.csv",
}
NEUTRAL, CONTROL = "sector_neutral", "control_same_names"
NOTE = ("Universe: names with a known current sector in a sector of at least 10 scored names that month. Names without a "
        "sector are mostly names that left the index, so this universe leans toward names that stayed. Survivorship "
        "affects levels and differences. See Amendment 17.")


def load_sectors() -> pd.Series:
    members = pd.read_csv(MEMBERSHIP_PATH).drop_duplicates("ticker")
    return members.set_index("ticker")["gics_sector"]


def variant_signals(momentum: pd.DataFrame, value: pd.DataFrame, sectors: pd.Series) -> tuple[dict, pd.DataFrame]:
    """{variant: {"Value": frame, "Combined": frame}} and the monthly left-out counts."""
    neutral_value, counts = sector_neutral_score(value, sectors, MIN_NAMES_PER_SECTOR)
    kept_momentum = restrict_to_names(momentum, neutral_value)
    control_value = restrict_to_names(value, neutral_value)
    return {
        NEUTRAL: {"Value": neutral_value, "Combined": combined_signal(kept_momentum, neutral_value)},
        CONTROL: {"Value": control_value, "Combined": combined_signal(kept_momentum, control_value)},
    }, counts


def signal_tests(signals: dict, returns: pd.DataFrame, periods: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    series = {}
    for name, signal in signals.items():
        series[(name, "rank_ic")] = monthly_statistic(signal, returns, rank_ic)
        series[(name, "quintile_spread")] = monthly_statistic(signal, returns, quintile_spread)
        series[(name, "fama_macbeth_single")] = fama_macbeth_slopes({name: signal}, returns)[name]
    summary = pd.concat([summarize_signal(name, series[(name, "rank_ic")], series[(name, "quintile_spread")],
                                          {"fama_macbeth_single": series[(name, "fama_macbeth_single")]}, periods,
                                          n_sims=N_SIMS, seed=SEED)[SUMMARY_COLUMNS] for name in signals],
                        ignore_index=True)
    return summary, robustness_table(series, periods)


def build_frames(path: dict, returns: pd.DataFrame, rf: pd.Series, periods: dict) -> dict:
    sectors = load_sectors()
    variants, counts = variant_signals(path["momentum"], path["value"], sectors)
    if (counts["kept"] < MIN_NAMES_PER_MONTH).any():
        low = counts.loc[counts["kept"] < MIN_NAMES_PER_MONTH, "date"].dt.strftime("%Y-%m").tolist()
        raise SystemExit(f"Fewer than {MIN_NAMES_PER_MONTH} names kept in {low}. Stopping.")
    summaries, robust, portfolio_returns, portfolio_summary = [], [], [], []
    for variant, signals in variants.items():
        print(f"\nVariant {variant}")
        summary, robustness = signal_tests(signals, returns, periods)
        summaries.append(summary.assign(variant=variant))
        robust.append(robustness.assign(variant=variant))
        portfolios, benchmarks = build_set(signals, ["Value", "Combined"], returns)
        stop_on_failures(f"{variant}: held names with a return",
                         held_without_return_failures({variant: (portfolios, benchmarks)}))
        portfolio_summary.append(summary_frame(portfolios, benchmarks, rf, periods, variant).assign(variant=variant))
        portfolio_returns.append(returns_long(portfolios, benchmarks, rf).assign(variant=variant))
    frames = {"counts": counts.assign(date=counts["date"].dt.strftime("%Y-%m-%d")),
              "signal_summary": pd.concat(summaries, ignore_index=True),
              "inference_robustness": pd.concat(robust, ignore_index=True),
              "portfolio_returns": pd.concat(portfolio_returns, ignore_index=True),
              "portfolio_summary": pd.concat(portfolio_summary, ignore_index=True)}
    for part in ("signal_summary", "inference_robustness", "portfolio_returns", "portfolio_summary"):
        frames[part]["universe_note"] = NOTE
    return frames


def print_report(frames: dict, saved_summary: pd.DataFrame):
    pd.set_option("display.width", 220, "display.max_columns", 30)
    counts = frames["counts"]
    print(f"\nLeft out each month (mean): no sector {counts['no_sector'].mean():.0f}, small sector "
          f"{counts['small_sector'].mean():.0f}; kept {counts['kept'].mean():.0f} of {counts['names_scored'].mean():.0f} scored names; "
          f"minimum kept {counts['kept'].min()}.")
    summary = frames["portfolio_summary"]
    head = summary[(summary["basis"] == "gross") & (summary["size"] == "top_decile") & summary["sharpe_diff_tbill"].notna()]
    saved = saved_summary[(saved_summary["basis"] == "gross") & (saved_summary["size"] == "top_decile")
                          & saved_summary["strategy"].isin(["Value", "Combined"])].assign(variant="registered")
    columns = ["variant", "strategy", "period", "months", "sharpe_tbill", "benchmark_sharpe_tbill", "sharpe_diff_tbill",
               "ci_90_lower_tbill", "ci_90_upper_tbill"]
    both = pd.concat([saved[columns], head[columns]], ignore_index=True)
    print("\nTop decile, gross, Sharpe difference against the equal-weight benchmark of each universe:")
    print(both.sort_values(["strategy", "period", "variant"]).round(3).to_string(index=False))
    sig = frames["signal_summary"]
    print("\nSignal tests that exclude zero under the registered interval:")
    print(sig[sig["excludes_zero"]][["variant", "signal", "test", "period", "mean", "ci_90_lower", "ci_90_upper"]]
          .round(4).to_string(index=False) if "excludes_zero" in sig else sig.head())


def write_all_or_nothing(frames: dict):
    created = []
    try:
        for part, path in OUTPUTS.items():
            with open(path, "x", newline="") as handle:
                frames[part].to_csv(handle, index=False)
            created.append(path)
    except Exception:
        for path in created:
            Path(path).unlink(missing_ok=True)
        raise
    for part, path in OUTPUTS.items():
        print(f"  {path}: {len(pd.read_csv(path))} rows, SHA-256 {hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]}")


def run(args: argparse.Namespace):
    stop_if_outputs_exist(OUTPUTS.values())
    calendar, usability = load_inputs()
    run_gate2(calendar)
    prices = read_month_end_prices(calendar)
    run_gate1a_momentum(prices, usability)
    run_count_check(prices, usability)
    path = run_value_path(calendar, prices, usability)
    stop_on_failures("Registered 24-name list", registered_list_failures(path["jumps"]))
    returns = calculate_monthly_returns(prices)
    periods = study_periods()
    run_reproduction_checks(path, returns, periods)
    rf = load_rf(evaluation_dates())
    run_portfolio_reproduction(path, returns, rf, periods)

    print(f"\nBootstrap: {N_SIMS} resamples, seed {SEED}, 90% intervals.")
    frames = build_frames(path, returns, rf, periods)
    print_report(frames, pd.read_csv(SAVED_PORTFOLIO_SUMMARY))
    if not args.write:
        print("\nDry run: nothing written. With --write these files would be written, with mode x:")
        for part, out in OUTPUTS.items():
            print(f"  {out} ({len(frames[part])} rows)")
        return
    stop_if_outputs_exist(OUTPUTS.values())
    write_all_or_nothing(frames)


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    if not (args.dry_run or args.write):
        raise SystemExit("Choose --dry-run, or --write. Nothing written.")
    started = datetime.now()
    print(f"Run started {started:%Y-%m-%d %H:%M:%S} ({'write' if args.write else 'dry run'})")
    try:
        run(args)
    finally:
        print(f"\nRun ended {datetime.now():%Y-%m-%d %H:%M:%S}")


if __name__ == "__main__":
    main()
