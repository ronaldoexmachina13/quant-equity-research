"""
Unit tests for src/signal_extras.py (LIMITATIONS_PLAN.md, Amendment 14).

All inputs are small invented examples whose answers were worked out by
hand; the working is in each test's comment. No network, no real data.
"""
import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from src.risk import bootstrap_statistic_ci
from src.signal_extras import (
    quintile_group_returns, monthly_quintile_returns, quintile_monotonicity, quintile_return_summary,
    newey_west_lags, block_length_rule, lag_autocorrelation, newey_west_se, newey_west_interval,
    block_bootstrap_ci, inference_robustness_row,
)

NAMES = list("abcdefghij")
Z90 = float(norm.ppf(0.95))


def series(values, names=NAMES):
    return pd.Series(values, index=names[:len(values)], dtype=float)


# ---------------------------------------------------------------------------
# Quintile mean returns
# ---------------------------------------------------------------------------

RETURNS = [.01, .03, .02, .04, .05, .07, .06, .08, .10, .12]


def test_group_returns_are_the_mean_of_each_pair():
    # Ten names, signal 1..10: groups are (a,b), (c,d), (e,f), (g,h), (i,j).
    # Means: (.01+.03)/2 = .02, (.02+.04)/2 = .03, (.05+.07)/2 = .06, (.06+.08)/2 = .07, (.10+.12)/2 = .11.
    result = quintile_group_returns(series(range(1, 11)), series(RETURNS))
    assert result.index.tolist() == [1, 2, 3, 4, 5]
    assert result.tolist() == pytest.approx([.02, .03, .06, .07, .11])


def test_group_returns_leave_out_names_with_no_return_but_keep_their_group():
    # b has no return: group 1 is a alone (.01). Groups are not reassigned.
    returns = series(RETURNS)
    returns["b"] = np.nan
    result = quintile_group_returns(series(range(1, 11)), returns)
    assert result.tolist() == pytest.approx([.01, .03, .06, .07, .11])


def test_a_group_with_no_returns_is_nan():
    returns = series(RETURNS)
    returns[["i", "j"]] = np.nan
    result = quintile_group_returns(series(range(1, 11)), returns)
    assert np.isnan(result[5]) and result[1] == pytest.approx(.02)


def test_the_top_minus_bottom_group_is_the_quintile_spread():
    result = quintile_group_returns(series(range(1, 11)), series(RETURNS))
    assert result[5] - result[1] == pytest.approx(.09)


def test_monthly_quintile_returns_marks_a_thin_month_as_nan():
    dates = pd.to_datetime(["2020-01-31", "2020-02-29"])
    signal = pd.DataFrame(np.nan, index=dates, columns=NAMES)
    signal.loc[dates[0]] = range(1, 11)
    signal.loc[dates[1], ["a", "b", "c"]] = [1, 2, 3]  # three names, below min_names=5
    returns = pd.DataFrame([RETURNS, RETURNS], index=dates, columns=NAMES)
    result = monthly_quintile_returns(signal, returns, min_names=5)
    assert result.loc[dates[0]].tolist() == pytest.approx([.02, .03, .06, .07, .11])
    assert result.loc[dates[1]].isna().all()
    assert result.columns.tolist() == [1, 2, 3, 4, 5]


def test_monotonicity_is_one_for_a_rising_order_and_minus_one_for_a_falling_one():
    assert quintile_monotonicity(pd.Series([1, 2, 3, 4, 5], index=range(1, 6))) == pytest.approx(1.0)
    assert quintile_monotonicity(pd.Series([5, 4, 3, 2, 1], index=range(1, 6))) == pytest.approx(-1.0)


def test_monotonicity_with_one_adjacent_pair_out_of_order():
    # Ranks 1,3,2,4,5 against 1..5: sum d^2 = 2, so rho = 1 - 6*2/(5*24) = 0.9.
    assert quintile_monotonicity(pd.Series([1, 3, 2, 4, 5], index=range(1, 6))) == pytest.approx(0.9)


def test_return_summary_means_annualised_and_months():
    dates = pd.to_datetime(["2020-01-31", "2020-02-29", "2020-03-31"])
    monthly = pd.DataFrame([[.01, .02, .03, .04, .05], [.03, .02, .01, .04, .07], [np.nan] * 5],
                           index=dates, columns=range(1, 6))
    summary = quintile_return_summary(monthly, {"first two": dates[:2], "all": dates})
    first = summary[summary["period"] == "first two"].set_index("quintile")
    # Group means over the two months: .02, .02, .02, .04, .06. The first three tie and share rank 2, so the
    # ranks are 2, 2, 2, 4, 5 against 1..5. Deviations from 3: (-2,-1,0,1,2) and (-1,-1,-1,1,2); cross-products
    # sum to 8, squares to 10 and 8, so rho = 8 / sqrt(80) = 0.894427.
    assert first["mean_monthly"].tolist() == pytest.approx([.02, .02, .02, .04, .06])
    assert first["mean_annualised"].tolist() == pytest.approx([.24, .24, .24, .48, .72])
    assert first["months"].tolist() == [2] * 5
    assert first["monotonicity"].iloc[0] == pytest.approx(8 / np.sqrt(80))
    assert summary[summary["period"] == "all"]["months"].tolist() == [2] * 5  # the all-NaN month is not counted


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def test_lag_rule():
    # 4 * (n/100)^(2/9): n=108 gives 4.07, n=68 gives 3.67, n=176 gives 4.54, n=25 gives 2.94, n=100 gives 4.
    assert [newey_west_lags(n) for n in (108, 68, 176, 25, 100)] == [4, 3, 4, 2, 4]


def test_block_length_rule():
    # n^(1/3): 108 gives 4.76, 68 gives 4.08, 176 gives 5.60.
    assert [block_length_rule(n) for n in (108, 68, 176)] == [5, 5, 6]


# ---------------------------------------------------------------------------
# Newey-West
# ---------------------------------------------------------------------------

ALTERNATING = [1, -1, 1, -1]
RUNS = [1, 1, -1, -1]


def test_lag_one_autocorrelation_of_an_alternating_series():
    # Deviations equal the values. Products of neighbours: -1, -1, -1 = -3, over the sum of squares 4.
    assert lag_autocorrelation(ALTERNATING, 1) == pytest.approx(-0.75)


def test_newey_west_with_no_lags_is_the_population_deviation_over_root_n():
    # gamma_0 = 4/4 = 1, so se = sqrt(1/4) = 0.5.
    assert newey_west_se(ALTERNATING, 0) == pytest.approx(0.5)


def test_newey_west_one_lag_on_an_alternating_series():
    # gamma_1 = -3/4, weight 1 - 1/2. Long-run variance 1 + 2 * 0.5 * (-0.75) = 0.25, se = sqrt(0.25 / 4) = 0.25.
    assert newey_west_se(ALTERNATING, 1) == pytest.approx(0.25)


def test_newey_west_two_lags_on_an_alternating_series():
    # gamma_2 = (1*1 + (-1)*(-1)) / 4 = 0.5. Weights 2/3 and 1/3.
    # Long-run variance 1 + 2*(2/3)*(-0.75) + 2*(1/3)*0.5 = 1/3, se = sqrt((1/3) / 4) = 0.288675.
    assert newey_west_se(ALTERNATING, 2) == pytest.approx(0.288675, abs=1e-6)


def test_newey_west_is_larger_when_months_come_in_runs():
    # gamma_1 = (1*1 + 1*(-1) + (-1)*(-1)) / 4 = 0.25. Long-run variance 1 + 2 * 0.5 * 0.25 = 1.25,
    # se = sqrt(1.25 / 4) = 0.559017, against 0.5 with no lags.
    assert newey_west_se(RUNS, 1) == pytest.approx(0.559017, abs=1e-6)
    assert newey_west_se(RUNS, 1) > newey_west_se(RUNS, 0)


def test_newey_west_interval_uses_the_normal_quantile():
    result = newey_west_interval(pd.Series(ALTERNATING), lags=1)
    assert result["point"] == pytest.approx(0.0)
    assert result["se"] == pytest.approx(0.25)
    assert result["lower"] == pytest.approx(-0.25 * Z90) and result["upper"] == pytest.approx(0.25 * Z90)
    assert result["t_stat"] == pytest.approx(0.0)


def test_newey_west_interval_drops_missing_months_and_defaults_the_lag_rule():
    values = pd.Series([np.nan] + [1.0, -1.0] * 54)
    result = newey_west_interval(values)
    assert result["lags"] == newey_west_lags(108) == 4


# ---------------------------------------------------------------------------
# Block bootstrap
# ---------------------------------------------------------------------------

def test_block_bootstrap_of_a_constant_series_is_that_constant():
    result = block_bootstrap_ci(pd.Series([0.02] * 20), block_length=3, n_sims=200, seed=1)
    assert result["lower"] == pytest.approx(0.02) and result["upper"] == pytest.approx(0.02)


def test_one_block_as_long_as_the_series_always_gives_the_sample_mean():
    # A circular block of length n is a rotation of the whole series, so every resample has the same mean.
    values = pd.Series([1.0, 2.0, 4.0, 9.0])
    result = block_bootstrap_ci(values, block_length=4, n_sims=100, seed=3)
    assert result["lower"] == pytest.approx(4.0) and result["upper"] == pytest.approx(4.0)


def test_block_length_one_is_the_ordinary_bootstrap():
    values = pd.Series(np.random.default_rng(0).normal(0.01, 0.03, 60))
    block = block_bootstrap_ci(values, block_length=1, n_sims=500, ci=0.90, seed=42)
    plain = bootstrap_statistic_ci(values, lambda s: s.mean(), n_sims=500, ci=0.90, seed=42)
    assert block["lower"] == pytest.approx(plain["lower"]) and block["upper"] == pytest.approx(plain["upper"])


def test_block_bootstrap_is_reproducible_and_defaults_the_block_rule():
    values = pd.Series(np.random.default_rng(1).normal(0, 1, 108))
    first = block_bootstrap_ci(values, n_sims=300, seed=42)
    second = block_bootstrap_ci(values, n_sims=300, seed=42)
    assert first == second and first["block_length"] == 5


def test_blocks_widen_the_interval_for_a_series_in_long_runs():
    runs = pd.Series([1.0] * 10 + [-1.0] * 10)
    plain = block_bootstrap_ci(runs, block_length=1, n_sims=2000, seed=42)
    blocked = block_bootstrap_ci(runs, block_length=10, n_sims=2000, seed=42)
    assert blocked["upper"] - blocked["lower"] > plain["upper"] - plain["lower"]


# ---------------------------------------------------------------------------
# One row
# ---------------------------------------------------------------------------

def test_robustness_row_for_a_series_that_is_clearly_positive():
    values = pd.Series([0.02, 0.03, 0.01, 0.025, 0.015] * 12)
    row = inference_robustness_row(values, n_sims=500, seed=42)
    assert row["months"] == 60 and row["mean"] == pytest.approx(0.02)
    assert row["nw_lags"] == newey_west_lags(60) and row["block_length"] == block_length_rule(60)
    assert row["nw_excludes_zero"] and row["block_excludes_zero"]


def test_robustness_row_for_a_series_centred_on_zero():
    row = inference_robustness_row(pd.Series([1.0, -1.0] * 30), n_sims=500, seed=42)
    assert row["mean"] == pytest.approx(0.0)
    assert not row["nw_excludes_zero"] and not row["block_excludes_zero"]
    assert row["autocorrelation_lag1"] < 0
