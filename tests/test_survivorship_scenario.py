"""Hand-worked tests for the survivorship scenario functions."""
import numpy as np
import pandas as pd
import pytest

from src.survivorship_scenario import adjusted_spread, gate_failures, period_months, reference_share_missing, scenario_table


def test_adjusted_spread_hand_worked():
    # group 1 = 2%, group 5 = 3%, 20% of the true group 1 missing at -5% a month:
    # group 1 adjusted = 0.8 x 0.02 + 0.2 x (-0.05) = 0.006, so the spread is 0.03 - 0.006 = 0.024.
    spread = adjusted_spread(pd.Series([0.02]), pd.Series([0.03]), 0.20, -0.05)
    assert spread.iloc[0] == pytest.approx(0.024)


def test_adjusted_spread_with_no_missing_share_is_the_saved_spread():
    g1, g5 = pd.Series([0.01, -0.02]), pd.Series([0.03, 0.00])
    assert adjusted_spread(g1, g5, 0.0, -0.05).tolist() == pytest.approx((g5 - g1).tolist())


def test_adjusted_spread_equals_saved_spread_plus_s_times_gap():
    g1, g5 = pd.Series([0.02]), pd.Series([0.03])
    saved = g5 - g1
    assert adjusted_spread(g1, g5, 0.30, 0.0).iloc[0] == pytest.approx(saved.iloc[0] + 0.30 * (0.02 - 0.0))


def test_period_months_splits_at_31_december_2020():
    dates = pd.to_datetime(["2020-11-30", "2020-12-31", "2021-01-31"])
    masks = period_months(dates)
    assert masks["New test (2012-2020)"].tolist() == [True, True, False]
    assert masks["Re-test (2021-2026)"].tolist() == [False, False, True]
    assert masks["Full period (2012-2026)"].tolist() == [True, True, True]


def test_reference_share_is_total_without_price_over_total_members():
    coverage = pd.DataFrame({"members": [100, 300], "members_no_price_t1": [10, 30]})
    assert reference_share_missing(coverage, np.array([True, True])) == pytest.approx(0.10)
    assert reference_share_missing(coverage, np.array([False, True])) == pytest.approx(0.10)


def _monthly_inputs(months=48):
    dates = pd.date_range("2019-01-31", periods=months, freq="ME")
    rng = np.random.default_rng(0)
    quintiles = pd.DataFrame({"date": dates, "signal": "Momentum",
                              "q1": rng.normal(0.01, 0.03, months), "q5": rng.normal(0.01, 0.03, months)})
    coverage = pd.DataFrame({"month": dates.strftime("%Y-%m-01"), "members": 100, "members_no_price_t1": 10})
    return quintiles, coverage


def test_scenario_table_has_ten_rows_per_period_and_the_unadjusted_row_equals_q5_minus_q1():
    quintiles, coverage = _monthly_inputs()
    table = scenario_table(quintiles, coverage)
    assert len(table) == 30                      # 3 periods x (1 unadjusted + 3 shares x 3 returns)
    assert table["assumed_share_missing_in_group1"].value_counts().to_dict() == {0.0: 3, 0.1: 9, 0.2: 9, 0.3: 9}
    full = table[(table["period"] == "Full period (2012-2026)") & (table["assumed_share_missing_in_group1"] == 0.0)]
    assert full["spread_mean_monthly"].iloc[0] == pytest.approx((quintiles["q5"] - quintiles["q1"]).mean())
    assert table["reference_share_members_without_price"].tolist() == pytest.approx([0.10] * 30)


def test_gate_failures_is_empty_for_matching_summary_and_names_a_changed_value():
    quintiles, coverage = _monthly_inputs()
    table = scenario_table(quintiles, coverage)
    base = table[table["assumed_share_missing_in_group1"] == 0.0]
    saved = pd.DataFrame({"test": "quintile_spread", "period": base["period"], "mean": base["spread_mean_monthly"],
                          "ci_90_lower": base["spread_ci_90_lower"], "ci_90_upper": base["spread_ci_90_upper"]})
    assert gate_failures(table, saved) == []
    saved.loc[saved.index[0], "mean"] += 0.001
    failures = gate_failures(table, saved)
    assert len(failures) == 1 and "spread_mean_monthly" in failures[0]


# Amendment 20: positive returns for the missing names


def test_positive_missing_return_lowers_the_spread_hand_worked():
    # group 1 = 1%, group 5 = 2%, 20% of the true group 1 missing at +5% a month:
    # group 1 adjusted = 0.8 x 0.01 + 0.2 x 0.05 = 0.018, so the spread is 0.02 - 0.018 = 0.002, below the saved 0.01.
    spread = adjusted_spread(pd.Series([0.01]), pd.Series([0.02]), 0.20, 0.05)
    assert spread.iloc[0] == pytest.approx(0.002)


def test_positive_grid_has_seven_rows_per_period_and_keeps_the_unadjusted_row():
    from src.survivorship_scenario import MISSING_RETURNS_POSITIVE
    quintiles, coverage = _monthly_inputs()
    table = scenario_table(quintiles, coverage, missing_returns=MISSING_RETURNS_POSITIVE)
    assert len(table) == 21                      # 3 periods x (1 unadjusted + 3 shares x 2 returns)
    assert sorted(table["assumed_monthly_return_missing"].dropna().unique().tolist()) == [0.02, 0.05]
    base19 = scenario_table(quintiles, coverage)
    pick = lambda t: t[t["assumed_share_missing_in_group1"] == 0.0]["spread_mean_monthly"].tolist()
    assert pick(table) == pytest.approx(pick(base19))


def test_default_grid_is_unchanged_by_amendment_20():
    quintiles, coverage = _monthly_inputs()
    table = scenario_table(quintiles, coverage)
    assert sorted(table["assumed_monthly_return_missing"].dropna().unique().tolist()) == [-0.05, -0.02, 0.0]
