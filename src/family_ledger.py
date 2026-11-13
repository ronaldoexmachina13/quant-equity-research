"""
Test ledger by family (Amendment 19, decision 3). One row per family. For each family it counts the
intervals that were run and how many exclude zero, from the saved result files, with the direction of the
point estimate. It adds nothing across families: there is no pooled total and no pooled rate, because the
families overlap (the same Value result in 2012 to 2020 recurs in several of them).

Counting rules, fixed here so that nobody can pick them after seeing the numbers:
  - One row per test. Cost-adjusted rows (net_existing, net_drift) repeat a gross test and are not counted.
  - A Sharpe comparison is a row with headline_test True in a portfolio summary file (gross, Treasury bill basis).
  - An alpha row is a gross row of the regression files.
  - Newey-West and block-bootstrap intervals are listed in their own rows, two per test, not mixed in.
  - The yearly intervals of universe_study_survivorship_by_year.csv are listed as descriptive. The file's own
    note says they are not part of any test family.

These functions only calculate. Reading and writing files is done by scripts/universe/make_test_ledger.py,
which refuses to write results unless Amendment 19 is in docs/LIMITATIONS_PLAN.md.
"""
from pathlib import Path

import pandas as pd

GROSS_FAMILIES = {"R2", "S2", "E2", "E3", "E4", "E5", "E6", "E7", "D1"}   # families that exist on a gross and a cost-adjusted basis


def counts(table, point_column, flag_column):
    """Intervals run, how many exclude zero, and how many of those have a positive or negative estimate."""
    flagged = table[table[flag_column].astype(bool)]
    return len(table), len(flagged), int((flagged[point_column] > 0).sum()), int((flagged[point_column] < 0).sum())


def signal_rows(read, names):
    return pd.concat([read(n) for n in names], ignore_index=True)


def sharpe_rows(read, names):
    table = pd.concat([read(n) for n in names], ignore_index=True)
    return table[table["headline_test"].astype(bool)]


def inference_rows(read, name):
    """Two intervals per test: Newey-West and block bootstrap."""
    table = read(name)
    both = pd.concat([
        table.assign(point=table["mean"], flag=table["nw_excludes_zero"]),
        table.assign(point=table["mean"], flag=table["block_excludes_zero"]),
    ], ignore_index=True)
    return both


def ledger(results_dir) -> pd.DataFrame:
    """Build the ledger from the saved CSVs in results_dir."""
    def read(name):
        return pd.read_csv(Path(results_dir) / name)

    alpha = read("universe_study_alpha_regression.csv")
    alpha = alpha[alpha["basis"] == "gross"]
    four = read("universe_study_alpha_factor4.csv")
    four = four[four["basis"] == "gross"]
    yearly = read("universe_study_survivorship_by_year.csv")
    sn_sig = read("universe_study_sector_neutral_signal_summary.csv")

    families = [
        # id, tier, family, files, table, point column, flag column
        ("R1", "Registered", "Signal tests (rank IC, quintile spread, Fama-MacBeth)",
         "signal_summary_momentum; signal_summary_value_combined",
         signal_rows(read, ["universe_study_signal_summary_momentum.csv", "universe_study_signal_summary_value_combined.csv"]),
         "mean", "excludes_zero"),
        ("R2", "Registered", "Headline Sharpe differences, gross, against the equal-weight benchmark",
         "portfolio_summary", sharpe_rows(read, ["universe_study_portfolio_summary.csv"]),
         "sharpe_diff_tbill", "significant_tbill"),
        ("S1", "Sensitivity", "Signal tests: winsorised P/B, two exclusion lists, true 12-1",
         "signal_summary_*_winsorised_pb, _excl_24, _excl_37, _momentum_skip_month",
         signal_rows(read, ["universe_study_signal_summary_value_combined_winsorised_pb.csv",
                      "universe_study_signal_summary_value_combined_excl_24.csv",
                      "universe_study_signal_summary_value_combined_excl_37.csv",
                      "universe_study_signal_summary_momentum_skip_month.csv"]),
         "mean", "excludes_zero"),
        ("S2", "Sensitivity", "Sharpe differences: two exclusion lists, true 12-1",
         "portfolio_summary_excl_24, _excl_37, _momentum_skip_month",
         sharpe_rows(read, ["universe_study_portfolio_summary_excl_24.csv", "universe_study_portfolio_summary_excl_37.csv",
                      "universe_study_portfolio_summary_momentum_skip_month.csv"]),
         "sharpe_diff_tbill", "significant_tbill"),
        ("E1", "Exploratory, after results", "Sector-neutral and same-names signal tests",
         "sector_neutral_signal_summary", sn_sig, "mean", "excludes_zero"),
        ("E2", "Exploratory, after results", "Sector-neutral and same-names Sharpe differences",
         "sector_neutral_portfolio_summary", sharpe_rows(read, ["universe_study_sector_neutral_portfolio_summary.csv"]),
         "sharpe_diff_tbill", "significant_tbill"),
        ("E3", "Exploratory, after results", "Alpha against the matched equal-weight benchmark, gross",
         "alpha_regression", alpha[alpha["benchmark"] != "SPY (reference)"], "alpha_annual", "alpha_excludes_zero"),
        ("E4", "Exploratory, after results", "Alpha against SPY, gross",
         "alpha_regression", alpha[alpha["benchmark"] == "SPY (reference)"], "alpha_annual", "alpha_excludes_zero"),
        ("E5", "Exploratory, after results", "Four-factor alpha, registered portfolios, gross",
         "alpha_factor4 (published)", four[four["variant"] == "published"], "alpha_annual", "alpha_excludes_zero"),
        ("E6", "Exploratory, after results", "Four-factor alpha, same-names Value and Combined, gross",
         "alpha_factor4 (control_same_names)", four[four["variant"] == "control_same_names"], "alpha_annual", "alpha_excludes_zero"),
        ("E7", "Exploratory, after results", "Four-factor alpha, sector-neutral Value and Combined, gross",
         "alpha_factor4 (sector_neutral)", four[four["variant"] == "sector_neutral"], "alpha_annual", "alpha_excludes_zero"),
        ("V1", "Inference variants", "Newey-West and block intervals on the 33 registered signal tests",
         "inference_robustness", inference_rows(read, "universe_study_inference_robustness.csv"), "point", "flag"),
        ("V2", "Inference variants", "Newey-West and block intervals on the true 12-1 signal tests",
         "inference_robustness_momentum_skip_month", inference_rows(read, "universe_study_inference_robustness_momentum_skip_month.csv"), "point", "flag"),
        ("V3", "Inference variants", "Newey-West and block intervals on the sector-neutral and same-names tests",
         "sector_neutral_inference_robustness", inference_rows(read, "universe_study_sector_neutral_inference_robustness.csv"), "point", "flag"),
        ("D1", "Descriptive, not a test family", "Yearly Sharpe-difference intervals on 8 to 12 months",
         "survivorship_by_year", yearly, "sharpe_diff_tbill", "interval_excludes_zero"),
    ]
    rows = []
    for fid, tier, name, files, table, point, flag in families:
        run, excl, pos, neg = counts(table, point, flag)
        rows.append({"family_id": fid, "tier": tier, "family": name, "source_files": files,
                     "basis": "gross" if fid in GROSS_FAMILIES else "not applicable",
                     "intervals_run": run, "exclude_zero": excl, "exclude_zero_positive": pos,
                     "exclude_zero_negative": neg})
    return pd.DataFrame(rows)


def gate_failures(table: pd.DataFrame) -> list[str]:
    """The registered families must equal the counts already published: 33 tests with 0 excluding zero, 18 with 2."""
    expected = {"R1": (33, 0), "R2": (18, 2)}
    by_id = table.set_index("family_id")
    return [f"{fid}: found {int(by_id.loc[fid, 'intervals_run'])} run and {int(by_id.loc[fid, 'exclude_zero'])} excluding zero, expected {want}"
            for fid, want in expected.items()
            if (int(by_id.loc[fid, "intervals_run"]), int(by_id.loc[fid, "exclude_zero"])) != want]
