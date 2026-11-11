"""
Amendment 14, decisions 1 and 2: quintile mean returns, and Newey-West and
block-bootstrap intervals for the 33 headline signal tests.

The script rebuilds the headline signals exactly as Stage 3 did (same gates,
same inputs) and recomputes every monthly series. Before anything is written
it checks that the registered mean and 90% interval of every test, in every
period, equal the saved summary files to within 1e-9, and that Q5 minus Q1
from the new table equals the saved quintile spread. A failure writes nothing.

Exploratory and post-results. No registered figure is changed.

Outputs are new files, never overwritten (each is opened with mode "x"):
    results/universe_study_quintile_returns_monthly.csv   one row per month and signal, groups 1 to 5
    results/universe_study_quintile_returns.csv           mean by group, period and signal, with monotonicity
    results/universe_study_inference_robustness.csv       registered, Newey-West and block-bootstrap intervals

Run from the repository root:  python -m scripts.universe.run_universe_extras
"""
from pathlib import Path

import pandas as pd

from scripts.universe.run_universe_gates import (
    run_gate2, run_gate1a_momentum, run_count_check, run_value_path, stop_on_failures,
)
from scripts.universe.run_universe_signals import load_inputs, stop_if_outputs_exist, N_SIMS, SEED
from src.backtest import calculate_monthly_returns
from src.signal_eval import rank_ic, quintile_spread, monthly_statistic, fama_macbeth_slopes, series_summary
from src.signal_extras import (
    monthly_quintile_returns, quintile_return_summary, inference_robustness_row,
)
from src.universe_study import read_month_end_prices, momentum_signal, study_periods
from src.universe_value import signal_sets, signal_set_failures, registered_list_failures, HEADLINE

RESULTS = Path("results")
OUTPUTS = {
    "quintile_monthly": RESULTS / "universe_study_quintile_returns_monthly.csv",
    "quintile_summary": RESULTS / "universe_study_quintile_returns.csv",
    "robustness": RESULTS / "universe_study_inference_robustness.csv",
}
SAVED_SUMMARIES = [RESULTS / "universe_study_signal_summary_momentum.csv",
                   RESULTS / "universe_study_signal_summary_value_combined.csv"]
TOLERANCE = 1e-9
SIGNALS = ("Momentum", "Value", "Combined")


def headline_series(prices: pd.DataFrame, usability: pd.DataFrame, path: dict, returns: pd.DataFrame) -> tuple[dict, dict]:
    """
    {(signal, test): monthly series} for the 33 headline tests, built as in
    Stage 3: Momentum's IC, spread and single slope from the Momentum run,
    the joint slopes from the Momentum and Value signals together, and Value
    and Combined from the headline signal set.
    """
    headline = signal_sets(path["momentum"], path["value"])[HEADLINE]
    failures = signal_set_failures(HEADLINE, headline, returns)
    stop_on_failures("Headline signal set checks", failures)

    momentum = momentum_signal(prices, usability)
    joint = fama_macbeth_slopes({name: headline[name] for name in ("Momentum", "Value")}, returns)
    series = {
        ("Momentum", "rank_ic"): monthly_statistic(momentum, returns, rank_ic),
        ("Momentum", "quintile_spread"): monthly_statistic(momentum, returns, quintile_spread),
        ("Momentum", "fama_macbeth_single"): fama_macbeth_slopes({"Momentum": momentum}, returns)["Momentum"],
        ("Momentum", "fama_macbeth_joint"): joint["Momentum"],
        ("Value", "fama_macbeth_joint"): joint["Value"],
    }
    for name in ("Value", "Combined"):
        series[(name, "rank_ic")] = monthly_statistic(headline[name], returns, rank_ic)
        series[(name, "quintile_spread")] = monthly_statistic(headline[name], returns, quintile_spread)
        series[(name, "fama_macbeth_single")] = fama_macbeth_slopes({name: headline[name]}, returns)[name]
    return series, {"Momentum": momentum, "Value": headline["Value"], "Combined": headline["Combined"]}


def robustness_table(series: dict, periods: dict) -> pd.DataFrame:
    """One row per test, signal and period: the registered interval, then the two new ones."""
    rows = []
    for (signal, test), values in series.items():
        for period, dates in periods.items():
            window = values.reindex(dates)
            registered = series_summary(window, n_sims=N_SIMS, seed=SEED)
            new = inference_robustness_row(window, n_sims=N_SIMS, seed=SEED)
            rows.append({
                "test": test, "signal": signal, "period": period, "months": registered["months"], "mean": registered["mean"],
                "iid_ci_90_lower": registered["ci_90_lower"], "iid_ci_90_upper": registered["ci_90_upper"],
                "iid_excludes_zero": registered["excludes_zero"],
                **{k: v for k, v in new.items() if k not in ("months", "mean")},
            })
    return pd.DataFrame(rows)


def reproduction_failures(table: pd.DataFrame, quintile_summary: pd.DataFrame, saved: pd.DataFrame) -> list[str]:
    """Registered mean and interval against the saved summaries, and Q5 minus Q1 against the saved spread."""
    keys = ["test", "signal", "period"]
    merged = table.merge(saved, on=keys, suffixes=("", "_saved"), how="outer", indicator=True)
    failures = [f"{row.test} {row.signal} {row.period}: in only one of the new and the saved table"
                for row in merged[merged["_merge"] != "both"].itertuples()]
    both = merged[merged["_merge"] == "both"]
    for new, old in [("mean", "mean_saved"), ("iid_ci_90_lower", "ci_90_lower"), ("iid_ci_90_upper", "ci_90_upper"),
                     ("months", "months_saved")]:
        wrong = both[(both[new] - both[old]).abs() > TOLERANCE]
        failures += [f"{row.test} {row.signal} {row.period}: {new} {getattr(row, new):.12g} against saved {getattr(row, old):.12g}"
                     for row in wrong.itertuples()]

    spreads = saved[saved["test"] == "quintile_spread"].set_index(["signal", "period"])["mean"]
    pivot = quintile_summary.pivot_table(index=["signal", "period"], columns="quintile", values="mean_monthly")
    for key, value in spreads.items():
        if key in pivot.index and abs((pivot.loc[key, 5] - pivot.loc[key, 1]) - value) > TOLERANCE:
            failures.append(f"{key}: Q5 minus Q1 {pivot.loc[key, 5] - pivot.loc[key, 1]:.12g} against saved spread {value:.12g}")
    return failures


def main():
    stop_if_outputs_exist(OUTPUTS.values())
    calendar, usability = load_inputs()
    run_gate2(calendar)
    prices = read_month_end_prices(calendar)
    run_gate1a_momentum(prices, usability)
    run_count_check(prices, usability)
    path = run_value_path(calendar, prices, usability)
    stop_on_failures("Registered 24-name list", registered_list_failures(path["jumps"]))
    returns = calculate_monthly_returns(prices)

    series, signals = headline_series(prices, usability, path, returns)
    periods = study_periods()

    monthly = {name: monthly_quintile_returns(signals[name], returns) for name in SIGNALS}
    quintile_summary = pd.concat([quintile_return_summary(monthly[name], periods).assign(signal=name) for name in SIGNALS],
                                 ignore_index=True)
    quintile_summary = quintile_summary[["signal", "period", "quintile", "months", "mean_monthly", "mean_annualised", "monotonicity"]]
    table = robustness_table(series, periods)

    saved = pd.concat([pd.read_csv(p) for p in SAVED_SUMMARIES], ignore_index=True)
    stop_on_failures("Reproduction of the registered results", reproduction_failures(table, quintile_summary, saved))

    monthly_frame = pd.concat([m.rename(columns=lambda q: f"q{q}").rename_axis("date").reset_index().assign(signal=name)
                               for name, m in monthly.items()], ignore_index=True)
    monthly_frame = monthly_frame[["date", "signal"] + [f"q{q}" for q in range(1, 6)]]

    stop_if_outputs_exist(OUTPUTS.values())
    for key, frame in {"quintile_monthly": monthly_frame, "quintile_summary": quintile_summary, "robustness": table}.items():
        frame.to_csv(OUTPUTS[key], index=False, mode="x")
        print(f"Wrote {OUTPUTS[key]} ({len(frame)} rows)")

    print_report(quintile_summary, table)


def print_report(quintile_summary: pd.DataFrame, table: pd.DataFrame):
    with pd.option_context("display.width", 240, "display.max_columns", 30, "display.max_rows", 200):
        full = quintile_summary[quintile_summary["period"].str.startswith("Full")]
        print("\nMean monthly return by group, full period (%):")
        wide = full.pivot(index="signal", columns="quintile", values="mean_monthly") * 100
        wide["monotonicity"] = full.groupby("signal")["monotonicity"].first()
        print(wide.round(3).to_string())

        shown = table.assign(registered=table["iid_excludes_zero"], newey_west=table["nw_excludes_zero"],
                             block=table["block_excludes_zero"])
        print("\nDoes the 90% interval exclude zero? (registered, Newey-West, block bootstrap)")
        print(shown[["test", "signal", "period", "months", "mean", "autocorrelation_lag1", "nw_t_stat",
                     "registered", "newey_west", "block"]].round(4).to_string(index=False))

        flips = table[table["iid_excludes_zero"] & ~(table["nw_excludes_zero"] & table["block_excludes_zero"])]
        print(f"\nRegistered interval excludes zero in {int(table['iid_excludes_zero'].sum())} of {len(table)} rows; "
              f"of these, {len(flips)} do not exclude zero under both new intervals.")
        for row in flips.itertuples():
            print(f"  {row.test} {row.signal} {row.period}: Newey-West {'excludes' if row.nw_excludes_zero else 'includes'} zero, "
                  f"block {'excludes' if row.block_excludes_zero else 'includes'} zero")
        gained = table[~table["iid_excludes_zero"] & (table["nw_excludes_zero"] | table["block_excludes_zero"])]
        print(f"Registered interval includes zero but a new interval excludes it in {len(gained)} rows.")


if __name__ == "__main__":
    main()
