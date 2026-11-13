"""
Tests added after mutation testing of the S29, S31 and S39 code. Each one pins a behaviour that a deliberate
bug could change without any existing test noticing. All inputs are small and worked by hand.
"""
import importlib
import sys
import types

import numpy as np
import pandas as pd
import pytest

from src.family_ledger import counts, ledger
from src.registration_guard import check_dry_run_target
from src.signal_eval import series_summary
from src.survivorship_scenario import gate_failures, scenario_table


def _scenario_inputs(coverage_members, coverage_missing):
    dates = pd.to_datetime(["2020-11-30", "2021-01-31"])
    quintiles = pd.DataFrame({"date": dates, "signal": "Momentum", "q1": [0.00, 0.02], "q5": [0.01, 0.03]})
    coverage = pd.DataFrame({"month": ["2020-11-01", "2021-01-01"], "members": coverage_members,
                             "members_no_price_t1": coverage_missing})
    return quintiles, coverage


def test_each_month_uses_its_own_coverage_row_and_periods_pool_members_not_ratios():
    # Nov 2020: 50 of 100 members have no price. Jan 2021: 10 of 300. The coverage file is dated by the first of the
    # month, the quintile file by month end, so the two must be matched by month. The first window holds Nov only (0.5),
    # the second Jan only (10/300), the full period pools the counts (60/400), not the average of the ratios.
    quintiles, coverage = _scenario_inputs([100, 300], [50, 10])
    table = scenario_table(quintiles, coverage)
    reference = table.drop_duplicates("period").set_index("period")["reference_share_members_without_price"]
    assert reference["New test (2012-2020)"] == pytest.approx(0.5)
    assert reference["Re-test (2021-2026)"] == pytest.approx(10 / 300)
    assert reference["Full period (2012-2026)"] == pytest.approx(60 / 400)


def test_annualised_spread_is_twelve_times_the_monthly_mean():
    # Group 5 earns 1% a month more than group 1 in every month, so the arithmetic annual figure is 12%.
    quintiles, coverage = _scenario_inputs([100, 100], [10, 10])
    quintiles["q1"], quintiles["q5"] = [0.00, 0.00], [0.01, 0.01]
    row = scenario_table(quintiles, coverage).query("period == 'Full period (2012-2026)'").iloc[0]
    assert row["spread_mean_annualised"] == pytest.approx(0.12)


def test_the_interval_uses_the_registered_bootstrap_settings():
    # The saved intervals were made with 5000 resamples and seed 42. A different seed gives a different interval.
    quintiles, coverage = _scenario_inputs([100, 100], [10, 10])
    quintiles = pd.concat([quintiles] * 12, ignore_index=True)
    quintiles["date"] = pd.date_range("2020-01-31", periods=24, freq="ME")
    quintiles["q5"] = quintiles["q5"] + np.linspace(-0.02, 0.02, 24)
    coverage = pd.DataFrame({"month": quintiles["date"].dt.strftime("%Y-%m-01"), "members": 100, "members_no_price_t1": 10})
    row = scenario_table(quintiles, coverage).query("period == 'Full period (2012-2026)'").iloc[0]
    expected = series_summary(quintiles["q5"] - quintiles["q1"], n_sims=5000, seed=42)
    assert row["spread_ci_90_lower"] == pytest.approx(expected["ci_90_lower"], abs=1e-15)
    assert row["spread_ci_90_upper"] == pytest.approx(expected["ci_90_upper"], abs=1e-15)


def test_gate_accepts_rounding_noise_but_not_a_visible_difference():
    quintiles, coverage = _scenario_inputs([100, 100], [10, 10])
    table = scenario_table(quintiles, coverage)
    base = table[table["assumed_share_missing_in_group1"] == 0.0]
    saved = pd.DataFrame({"test": "quintile_spread", "period": base["period"], "mean": base["spread_mean_monthly"],
                          "ci_90_lower": base["spread_ci_90_lower"], "ci_90_upper": base["spread_ci_90_upper"]})
    saved["mean"] += 1e-12            # far below the 1e-9 tolerance
    assert gate_failures(table, saved) == []
    saved["mean"] += 1e-6             # a visible change in the third decimal of a basis point
    assert len(gate_failures(table, saved)) == 3


def test_counts_separates_positive_from_negative_estimates_when_they_differ():
    # Three intervals exclude zero: two with a positive estimate and one negative. A symmetric example cannot
    # tell the two columns apart.
    table = pd.DataFrame({"est": [0.5, 0.4, -0.1, 0.9], "flag": [True, True, True, False]})
    assert counts(table, "est", "flag") == (4, 3, 2, 1)


def _write_ledger_inputs(folder):
    generic = pd.DataFrame({
        "mean": [0.1, -0.1], "excludes_zero": [True, False], "headline_test": [True, False],
        "sharpe_diff_tbill": [0.2, 0.0], "significant_tbill": [True, False],
        "nw_excludes_zero": [True, False], "block_excludes_zero": [False, False],
        "interval_excludes_zero": [False, False],
    })
    for name in ["signal_summary_momentum", "signal_summary_value_combined", "signal_summary_value_combined_winsorised_pb",
                 "signal_summary_value_combined_excl_24", "signal_summary_value_combined_excl_37",
                 "signal_summary_momentum_skip_month", "sector_neutral_signal_summary", "portfolio_summary",
                 "portfolio_summary_excl_24", "portfolio_summary_excl_37", "portfolio_summary_momentum_skip_month",
                 "sector_neutral_portfolio_summary", "inference_robustness", "inference_robustness_momentum_skip_month",
                 "sector_neutral_inference_robustness", "survivorship_by_year"]:
        generic.to_csv(folder / f"universe_study_{name}.csv", index=False)
    pd.DataFrame({
        "basis": ["gross", "gross", "net_existing"],
        "benchmark": ["matched", "SPY (reference)", "matched"],
        "alpha_annual": [0.04, 0.03, 0.05], "alpha_excludes_zero": [True, False, True],
    }).to_csv(folder / "universe_study_alpha_regression.csv", index=False)
    pd.DataFrame({
        "basis": ["gross", "gross", "gross", "net_existing"],
        "variant": ["published", "control_same_names", "sector_neutral", "published"],
        "alpha_annual": [0.04, 0.01, -0.02, 0.06], "alpha_excludes_zero": [True, False, True, True],
    }).to_csv(folder / "universe_study_alpha_factor4.csv", index=False)


def test_ledger_counts_only_gross_alpha_rows_and_labels_the_basis(tmp_path):
    # A cost-adjusted row is the same test as its gross row, so counting both would double the family.
    _write_ledger_inputs(tmp_path)
    table = ledger(tmp_path).set_index("family_id")
    assert table.loc["E3", ["intervals_run", "exclude_zero"]].tolist() == [1, 1]     # matched benchmark, gross only
    assert table.loc["E4", ["intervals_run", "exclude_zero"]].tolist() == [1, 0]     # SPY row is its own family
    assert table.loc["E5", ["intervals_run", "exclude_zero", "exclude_zero_positive"]].tolist() == [1, 1, 1]
    assert table.loc["E6", ["intervals_run", "exclude_zero"]].tolist() == [1, 0]
    assert table.loc["E7", ["intervals_run", "exclude_zero_negative"]].tolist() == [1, 1]
    assert table.loc["R2", "basis"] == "gross" and table.loc["R1", "basis"] == "not applicable"


def test_dry_run_refuses_results_folder_given_as_a_relative_path(tmp_path, monkeypatch):
    # The scripts pass Path("results"), which is relative. It must still be recognised as the parent of the target.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "results").mkdir()
    with pytest.raises(SystemExit):
        check_dry_run_target(tmp_path / "results" / "x.csv", "results")


def _price_loader(monkeypatch, columns):
    def download(*args, **kwargs):
        index = pd.date_range("2021-01-01", periods=3)
        frame = pd.DataFrame(columns, index=index)
        frame.columns = pd.MultiIndex.from_product([["Adj Close"], frame.columns])
        return frame
    stub = types.ModuleType("yfinance")
    stub.download = download
    monkeypatch.setitem(sys.modules, "yfinance", stub)
    monkeypatch.delitem(sys.modules, "src.data_loader", raising=False)
    return importlib.import_module("src.data_loader")


def test_a_ticker_with_some_missing_days_is_not_treated_as_a_failed_download(monkeypatch):
    # A stock that listed during the window has no prices before it listed. That is normal, not a failed download.
    loader = _price_loader(monkeypatch, {"AAA": [1.0, 2.0, 3.0], "BBB": [np.nan, 5.0, 6.0]})
    prices = loader.get_price_history_multi(["AAA", "BBB"], "2021-01-01", "2021-01-04")
    assert prices["BBB"].isna().sum() == 1
