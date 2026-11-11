"""
Unit tests for src/universe_skip_month.py (Amendment 15, the true 12-1
Momentum sensitivity and the reversal diagnostic).

All inputs are small invented examples whose answers were worked out by
hand. No network, no real data.
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.backtest import calculate_monthly_returns
from src.signal_eval import fama_macbeth_slopes
from src.universe_skip_month import (
    skip_month_usable_mask, skip_month_signal, last_month_return_signal, missing_signal_failures,
    skip_month_signal_set, skip_month_set_failures, months_failures, series_failures, summary_failures,
    skip_month_series, skip_month_summary, monthly_series_frame, skip_month_counts_frame, without_first_month,
    ic_correlation, reading_rule_flags, skip_month_outputs,
    MOMENTUM_12_1, COMBINED_12_1, LAST_MONTH, VALUE_JOINT_12_1, VALUE, EXPECTED_MONTHS,
)
from src.universe_study import NEW_TEST, RE_TEST, FULL_PERIOD
from src.universe_value import SUMMARY_COLUMNS, combined_signal

DATES = pd.date_range("2020-01-31", periods=15, freq="ME")


def prices_frame() -> pd.DataFrame:
    """
    Rows 0 to 14. A has every price. B has no price in row 0. C has every
    price. In row 14 (t): t-13 is row 1 and t-2 is row 12.
    """
    a = [80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 100, 120, 50]
    b = [np.nan] + [40 + i for i in range(14)]
    c = [10 + i for i in range(15)]
    return pd.DataFrame({"A": a, "B": b, "C": c}, index=DATES, dtype=float)


def all_true(dates, tickers=("A", "B", "C")) -> pd.DataFrame:
    return pd.DataFrame(True, index=dates, columns=list(tickers))


# ---------------------------------------------------------------------------
# Usable set and signals
# ---------------------------------------------------------------------------

def test_usable_mask_needs_a_price_at_t_minus_13():
    """Row 13: t-13 is row 0, where B has no price. Row 14: t-13 is row 1, where B has one."""
    mask = skip_month_usable_mask(all_true(DATES[13:]), prices_frame())
    assert mask.loc[DATES[13]].to_dict() == {"A": True, "B": False, "C": True}
    assert mask.loc[DATES[14]].to_dict() == {"A": True, "B": True, "C": True}


def test_usable_mask_keeps_the_registered_rule():
    registered = all_true(DATES[14:])
    registered.loc[DATES[14], "C"] = False
    mask = skip_month_usable_mask(registered, prices_frame())
    assert not mask.loc[DATES[14], "C"]


def test_usable_mask_is_empty_when_t_minus_13_is_before_the_first_price():
    """Row 12: t-13 would be the month before row 0, outside the price history."""
    mask = skip_month_usable_mask(all_true(DATES[12:13]), prices_frame())
    assert not mask.loc[DATES[12]].any()


def test_skip_month_signal_is_t_minus_2_over_t_minus_13_by_hand():
    """A in row 14: price[12] / price[1] - 1 = 100 / 81 - 1."""
    mask = all_true(DATES[14:])
    mask.loc[DATES[14], "C"] = False
    signal = skip_month_signal(prices_frame(), mask)
    assert signal.loc[DATES[14], "A"] == pytest.approx(100 / 81 - 1, rel=1e-12)
    assert np.isnan(signal.loc[DATES[14], "C"])


def test_last_month_return_is_t_minus_1_over_t_minus_2_by_hand():
    """A in row 14: price[13] / price[12] - 1 = 120 / 100 - 1 = 0.2."""
    signal = last_month_return_signal(prices_frame(), all_true(DATES[14:]))
    assert signal.loc[DATES[14], "A"] == pytest.approx(0.2, rel=1e-12)


def test_last_month_return_equals_previous_monthly_return():
    prices = prices_frame()[["A", "C"]]
    mask = all_true(DATES[2:], ("A", "C"))
    expected = calculate_monthly_returns(prices).shift(1).loc[DATES[2:]]
    pd.testing.assert_frame_equal(last_month_return_signal(prices, mask), expected, check_freq=False)


def test_last_month_return_is_blank_outside_the_mask():
    mask = all_true(DATES[14:])
    mask.loc[DATES[14], "B"] = False
    assert np.isnan(last_month_return_signal(prices_frame(), mask).loc[DATES[14], "B"])


def test_missing_signal_failures_lists_a_gap_at_t_minus_2():
    prices = prices_frame()
    prices.loc[DATES[12], "C"] = np.nan          # t-2 for row 14
    mask = all_true(DATES[14:])
    failures = missing_signal_failures(skip_month_signal(prices, mask), mask)
    assert failures == ["2021-03 C: usable for 12-1 but no finite signal (no price at t-2)"]


def test_missing_signal_failures_lists_an_infinite_signal():
    prices = prices_frame()
    prices.loc[DATES[1], "C"] = 0.0              # t-13 for row 14, so the ratio is infinite
    mask = all_true(DATES[14:])
    assert len(missing_signal_failures(skip_month_signal(prices, mask), mask)) == 1


def test_missing_signal_failures_is_empty_on_clean_data():
    mask = all_true(DATES[14:])
    assert missing_signal_failures(skip_month_signal(prices_frame(), mask), mask) == []


def test_signal_set_scales_each_leg_over_its_own_names_by_hand():
    """
    Momentum on A, B, C: 0.1, 0.2, 0.3, so z = -1, 0, 1.
    Value on A, B, C, D: -1, -2, -3, -4, mean -2.5, sample sd sqrt(5/3).
    Combined is the average of the two z-scores, and D, with no 12-1 value, is blank.
    """
    date = DATES[:1]
    momentum = pd.DataFrame({"A": [0.1], "B": [0.2], "C": [0.3], "D": [np.nan]}, index=date)
    value = pd.DataFrame({"A": [-1.0], "B": [-2.0], "C": [-3.0], "D": [-4.0]}, index=date)
    signals = skip_month_signal_set(momentum, value)
    sd = math.sqrt(5 / 3)
    expected = {"A": (-1 + 1.5 / sd) / 2, "B": (0 + 0.5 / sd) / 2, "C": (1 - 0.5 / sd) / 2}
    for ticker, value_expected in expected.items():
        assert signals[COMBINED_12_1].loc[date[0], ticker] == pytest.approx(value_expected, rel=1e-12)
    assert np.isnan(signals[COMBINED_12_1].loc[date[0], "D"])
    assert signals[VALUE] is value
    assert signals[MOMENTUM_12_1] is momentum


def test_signal_set_combined_is_blank_where_value_is_missing():
    date = DATES[:1]
    momentum = pd.DataFrame({"A": [0.1], "B": [0.2], "C": [0.3]}, index=date)
    value = pd.DataFrame({"A": [-1.0], "B": [-2.0], "C": [np.nan]}, index=date)
    assert np.isnan(skip_month_signal_set(momentum, value)[COMBINED_12_1].loc[date[0], "C"])


# ---------------------------------------------------------------------------
# Set check
# ---------------------------------------------------------------------------

def clean_set():
    """Three months, three names. The first month is empty for the new signals."""
    dates = DATES[:3]
    momentum = pd.DataFrame({"A": [np.nan, 0.1, 0.2], "B": [np.nan, 0.3, 0.1], "C": [np.nan, 0.2, 0.3]}, index=dates)
    value = pd.DataFrame({"A": [-1.0, -2.0, -3.0], "B": [-2.0, -1.0, -2.0], "C": [-3.0, -3.0, -1.0]}, index=dates)
    signals = skip_month_signal_set(momentum, value)
    signals[LAST_MONTH] = momentum * 0.5
    registered = pd.DataFrame(0.0, index=dates, columns=["A", "B", "C"])
    returns = pd.DataFrame(0.01, index=dates, columns=["A", "B", "C"])
    return signals, registered, returns


def test_set_check_passes_on_a_clean_set():
    signals, registered, returns = clean_set()
    assert skip_month_set_failures(signals, registered, returns, min_names=2) == []


def test_set_check_flags_too_few_names():
    signals, registered, returns = clean_set()
    failures = skip_month_set_failures(signals, registered, returns, min_names=4)
    assert "2020-02: Momentum 12-1 has 3 names, below 4" in failures
    assert "2020-02: Combined (12-1 leg) has 3 names, below 4" in failures


def test_set_check_flags_combined_on_other_names():
    signals, registered, returns = clean_set()
    signals[COMBINED_12_1].loc[DATES[1], "A"] = np.nan
    failures = skip_month_set_failures(signals, registered, returns, min_names=2)
    assert "2020-02: Combined names differ from the names with both legs" in failures


def test_set_check_flags_last_month_on_other_names():
    signals, registered, returns = clean_set()
    signals[LAST_MONTH].loc[DATES[2], "B"] = np.nan
    failures = skip_month_set_failures(signals, registered, returns, min_names=2)
    assert "2020-03: last-month return names differ from the 12-1 names" in failures


def test_set_check_flags_a_name_without_a_return():
    signals, registered, returns = clean_set()
    returns.loc[DATES[2], "B"] = np.nan
    failures = skip_month_set_failures(signals, registered, returns, min_names=2)
    assert "2020-03: Momentum 12-1 has 1 names with no return" in failures


def test_set_check_flags_a_name_outside_the_registered_set():
    signals, registered, returns = clean_set()
    registered.loc[DATES[1], "C"] = np.nan
    failures = skip_month_set_failures(signals, registered, returns, min_names=2)
    assert "2020-02: 12-1 names outside the registered Momentum set: ['C']" in failures


def test_set_check_flags_a_first_month_that_is_not_empty():
    signals, registered, returns = clean_set()
    signals[MOMENTUM_12_1].loc[DATES[0], "A"] = 0.1
    failures = skip_month_set_failures(signals, registered, returns, min_names=2)
    assert "2020-01: Momentum 12-1 has names, but this month has no price at t-13" in failures


# ---------------------------------------------------------------------------
# Reproduction and month checks
# ---------------------------------------------------------------------------

def test_months_failures_flags_a_wrong_count():
    summary = pd.DataFrame({"test": ["rank_ic"] * 3, "signal": [MOMENTUM_12_1] * 3,
                            "period": [NEW_TEST, RE_TEST, FULL_PERIOD], "months": [107, 68, 176]})
    assert months_failures(summary) == [f"rank_ic {MOMENTUM_12_1} {FULL_PERIOD}: 176 months, expected 175"]


def test_expected_months_are_the_registered_windows_without_2012_01():
    assert EXPECTED_MONTHS == {NEW_TEST: 107, RE_TEST: 68, FULL_PERIOD: 175}


def test_series_failures_matches_nan_with_nan_and_flags_a_difference():
    dates = DATES[:3]
    saved = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "signal": "Momentum", "rank_ic": [np.nan, 0.1, 0.2]})
    assert series_failures(pd.Series([np.nan, 0.1, 0.2], index=dates), saved, "Momentum", "rank_ic") == []
    failures = series_failures(pd.Series([np.nan, 0.1, 0.3], index=dates), saved, "Momentum", "rank_ic")
    assert len(failures) == 1 and failures[0].startswith("Momentum rank_ic 2020-03")


def test_series_failures_ignores_other_signals_in_the_saved_file():
    dates = DATES[:1]
    saved = pd.DataFrame({"date": ["2020-01-31", "2020-01-31"], "signal": ["Value", "Combined"], "rank_ic": [0.9, 0.1]})
    assert series_failures(pd.Series([0.1], index=dates), saved, "Combined", "rank_ic") == []


def summary_row(mean=0.01, months=107):
    return {"test": "rank_ic", "signal": "Momentum", "period": NEW_TEST, "months": months, "mean": mean,
            "ci_90_lower": -0.01, "ci_90_upper": 0.03}


def test_summary_failures_passes_on_identical_rows():
    frame = pd.DataFrame([summary_row()])
    assert summary_failures(frame, frame.copy()) == []


def test_summary_failures_flags_a_different_mean_and_a_missing_row():
    saved = pd.DataFrame([summary_row()])
    found = pd.DataFrame([summary_row(mean=0.02), {**summary_row(), "test": "quintile_spread"}])
    failures = summary_failures(found, saved)
    assert any("rank_ic Momentum" in f and "mean" in f for f in failures)
    assert f"quintile_spread Momentum {NEW_TEST}: not in the saved summary" in failures


# ---------------------------------------------------------------------------
# Series, summary and monthly frames
# ---------------------------------------------------------------------------

def small_cross_section():
    """Four months, five names, with the first month empty for the new signals."""
    dates = DATES[:4]
    tickers = list("ABCDE")
    momentum = pd.DataFrame([[np.nan] * 5, [0.1, 0.4, 0.2, 0.5, 0.3], [0.3, 0.1, 0.5, 0.2, 0.4],
                             [0.2, 0.5, 0.1, 0.4, 0.3]], index=dates, columns=tickers)
    value = pd.DataFrame([[-1.0, -2.0, -3.0, -4.0, -5.0], [-2.0, -1.0, -4.0, -3.0, -5.0],
                          [-5.0, -4.0, -1.0, -2.0, -3.0], [-3.0, -1.0, -2.0, -5.0, -4.0]], index=dates, columns=tickers)
    returns = pd.DataFrame([[0.01, 0.02, 0.03, 0.04, 0.05], [0.02, 0.05, 0.01, 0.04, 0.03],
                            [0.04, 0.01, 0.05, 0.02, 0.03], [0.03, 0.05, 0.02, 0.01, 0.04]], index=dates, columns=tickers)
    return skip_month_signal_set(momentum, value), momentum * -1, returns


def test_skip_month_series_has_the_ten_registered_series():
    signals, last, returns = small_cross_section()
    series = skip_month_series(signals, last, returns, min_names=3)
    assert set(series) == {
        (MOMENTUM_12_1, "rank_ic"), (MOMENTUM_12_1, "quintile_spread"), (MOMENTUM_12_1, "fama_macbeth_single"),
        (MOMENTUM_12_1, "fama_macbeth_joint"), (VALUE_JOINT_12_1, "fama_macbeth_joint"),
        (COMBINED_12_1, "rank_ic"), (COMBINED_12_1, "quintile_spread"), (COMBINED_12_1, "fama_macbeth_single"),
        (LAST_MONTH, "rank_ic"), (LAST_MONTH, "quintile_spread"),
    }
    assert np.isnan(series[(MOMENTUM_12_1, "rank_ic")].iloc[0])


def test_skip_month_series_joint_slopes_come_from_one_regression():
    signals, last, returns = small_cross_section()
    series = skip_month_series(signals, last, returns, min_names=3)
    joint = fama_macbeth_slopes({MOMENTUM_12_1: signals[MOMENTUM_12_1], VALUE: signals[VALUE]}, returns, 3)
    pd.testing.assert_series_equal(series[(VALUE_JOINT_12_1, "fama_macbeth_joint")], joint[VALUE], check_names=False)
    pd.testing.assert_series_equal(series[(MOMENTUM_12_1, "fama_macbeth_joint")], joint[MOMENTUM_12_1], check_names=False)


def test_skip_month_summary_layout_and_rows():
    signals, last, returns = small_cross_section()
    series = skip_month_series(signals, last, returns, min_names=3)
    periods = {"All": DATES[:4]}
    summary = skip_month_summary(series, periods, n_sims=50, seed=42)
    assert list(summary.columns) == SUMMARY_COLUMNS
    assert len(summary) == 10
    assert set(summary["signal"]) == {MOMENTUM_12_1, COMBINED_12_1, LAST_MONTH, VALUE_JOINT_12_1}
    assert (summary["months"] == 3).all()
    spread = summary[(summary["signal"] == LAST_MONTH) & (summary["test"] == "quintile_spread")].iloc[0]
    assert spread["annualised_mean"] == pytest.approx(spread["mean"] * 12, rel=1e-12)


def test_monthly_series_frame_keeps_the_empty_first_month():
    signals, last, returns = small_cross_section()
    series = skip_month_series(signals, last, returns, min_names=3)
    frame = monthly_series_frame(series, "rank_ic", "rank_ic")
    assert len(frame) == 12
    assert list(frame["signal"].unique()) == [MOMENTUM_12_1, COMBINED_12_1, LAST_MONTH]
    assert frame.groupby("signal")["rank_ic"].apply(lambda s: np.isnan(s.iloc[0])).all()


def test_counts_frame_by_hand():
    """
    Month 2: registered A, B, C; 12-1 A, B (C lost to t-13); Value B, C;
    Combined B only; A has no return.
    """
    dates = DATES[:2]
    registered = pd.DataFrame({"A": [0.1, 0.1], "B": [0.1, 0.1], "C": [0.1, 0.1]}, index=dates)
    momentum = pd.DataFrame({"A": [np.nan, 0.1], "B": [np.nan, 0.2], "C": [np.nan, np.nan]}, index=dates)
    value = pd.DataFrame({"A": [-1.0, np.nan], "B": [-2.0, -2.0], "C": [-3.0, -3.0]}, index=dates)
    signals = {MOMENTUM_12_1: momentum, VALUE: value, COMBINED_12_1: combined_signal(momentum, value)}
    returns = pd.DataFrame({"A": [0.01, np.nan], "B": [0.01, 0.01], "C": [0.01, 0.01]}, index=dates)
    coverage = pd.DataFrame({"month": ["2020-01", "2020-02"], "members": [500, 501]})
    frame = skip_month_counts_frame(registered, signals, returns, coverage)
    row = frame.iloc[1]
    assert row["universe_size"] == 501
    assert (row["usable_momentum_registered"], row["usable_momentum_12_1"], row["lost_no_price_t13"]) == (3, 2, 1)
    assert (row["usable_value_registered"], row["no_return_momentum_12_1"]) == (2, 1)
    assert frame.iloc[0]["usable_momentum_12_1"] == 0 and frame.iloc[0]["lost_no_price_t13"] == 3


# ---------------------------------------------------------------------------
# Printout helpers
# ---------------------------------------------------------------------------

def test_without_first_month_drops_only_the_first_evaluation_month():
    periods = {NEW_TEST: DATES[:3], RE_TEST: DATES[3:5], FULL_PERIOD: DATES[:5]}
    trimmed = without_first_month(periods)
    assert list(trimmed[NEW_TEST]) == list(DATES[1:3])
    assert list(trimmed[RE_TEST]) == list(DATES[3:5])
    assert list(trimmed[FULL_PERIOD]) == list(DATES[1:5])


def test_ic_correlation_by_hand():
    """Common months give x = 1, 2, 3 and y = 2, 4, 7: covariance sum 5, sums of squares 2 and 38/3."""
    dates = DATES[:4]
    registered = pd.Series([1.0, 2.0, 3.0, np.nan], index=dates)
    skip = pd.Series([2.0, 4.0, 7.0, 5.0], index=dates)
    table = ic_correlation(registered, skip, {"All": dates})
    assert table.iloc[0]["months"] == 3
    assert table.iloc[0]["pearson"] == pytest.approx(5 / math.sqrt(2 * 38 / 3), rel=1e-12)


def robustness_rows(rows):
    columns = ["test", "signal", "period", "iid_excludes_zero", "nw_excludes_zero", "block_excludes_zero"]
    return pd.DataFrame(rows, columns=columns)


def test_reading_rule_flags_a_new_interval_that_excludes_zero_when_the_registered_one_does_not():
    new = robustness_rows([["rank_ic", MOMENTUM_12_1, FULL_PERIOD, False, True, False],
                           ["rank_ic", COMBINED_12_1, FULL_PERIOD, True, True, True],
                           ["rank_ic", LAST_MONTH, FULL_PERIOD, True, True, True]])
    registered = robustness_rows([["rank_ic", "Momentum", FULL_PERIOD, False, False, False],
                                  ["rank_ic", "Combined", FULL_PERIOD, True, True, True]])
    flags = reading_rule_flags(new, registered)
    assert flags[["test", "signal", "period"]].values.tolist() == [["rank_ic", MOMENTUM_12_1, FULL_PERIOD]]


def test_reading_rule_flags_maps_the_joint_value_slope_to_registered_value():
    new = robustness_rows([["fama_macbeth_joint", VALUE_JOINT_12_1, NEW_TEST, True, False, False]])
    registered = robustness_rows([["fama_macbeth_joint", "Value", NEW_TEST, False, False, False]])
    assert len(reading_rule_flags(new, registered)) == 1


def test_reading_rule_flags_stops_on_a_row_with_no_registered_match():
    new = robustness_rows([["rank_ic", MOMENTUM_12_1, RE_TEST, True, True, True]])
    registered = robustness_rows([["rank_ic", "Momentum", FULL_PERIOD, False, False, False]])
    with pytest.raises(ValueError):
        reading_rule_flags(new, registered)


def test_skip_month_outputs_are_the_eight_registered_names():
    paths = skip_month_outputs(Path("results"))
    names = sorted(p.name for p in paths.values())
    assert names == sorted([
        "universe_study_monthly_counts_momentum_skip_month.csv",
        "universe_study_ic_monthly_momentum_skip_month.csv",
        "universe_study_spread_monthly_momentum_skip_month.csv",
        "universe_study_signal_summary_momentum_skip_month.csv",
        "universe_study_inference_robustness_momentum_skip_month.csv",
        "universe_study_portfolio_returns_momentum_skip_month.csv",
        "universe_study_portfolio_summary_momentum_skip_month.csv",
        "universe_study_survivorship_by_year.csv",
    ])
