"""
Unit tests for src/signal_eval.py (Phase 4, reproduction gate 3).

All inputs are small invented examples whose answers were worked out by
hand; the working is in each test's comment. No network, no real data.
"""
import math

import numpy as np
import pandas as pd
import pytest

from src.risk import bootstrap_statistic_ci
from src.signal_eval import (
    rank_ic, assign_quintiles, quintile_spread, standardise, cross_section_slopes,
    monthly_cross_section, monthly_statistic, monthly_counts, fama_macbeth_slopes,
    series_summary, summarize_signal,
    MIN_NAMES_PER_MONTH,
)

NAMES = list("abcdefghij")


def series(values, names=NAMES):
    return pd.Series(values, index=names[:len(values)], dtype=float)


# ---------------------------------------------------------------------------
# Rank IC
# ---------------------------------------------------------------------------

def test_rank_ic_no_ties():
    # Return ranks 1,3,2,5,4 against signal ranks 1..5: sum d^2 = 4,
    # so rho = 1 - 6*4/(5*24) = 0.8.
    assert rank_ic(series([1, 2, 3, 4, 5]), series([.01, .03, .02, .05, .04])) == pytest.approx(0.8)


def test_rank_ic_is_negative_one_for_a_reversed_order():
    assert rank_ic(series([1, 2, 3, 4]), series([.4, .3, .2, .1])) == pytest.approx(-1.0)


def test_rank_ic_ties_share_the_average_rank():
    # Signal ranks 1, 2.5, 2.5, 4 against return ranks 1, 2, 3, 4.
    # Sxy = 4.5, Sxx = 4.5, Syy = 5, so r = 4.5 / sqrt(22.5) = 3 / sqrt(10).
    assert rank_ic(series([1, 2, 2, 3]), series([.1, .2, .3, .4])) == pytest.approx(3 / math.sqrt(10))


def test_rank_ic_drops_a_name_with_no_return_or_no_signal():
    # Same as the no-ties case once f (no return) and g (no signal) are dropped.
    signal = series([1, 2, 3, 4, 5, 100, np.nan])
    returns = series([.01, .03, .02, .05, .04, np.nan, 9.0])
    assert rank_ic(signal, returns) == pytest.approx(0.8)


def test_rank_ic_is_nan_when_undefined():
    assert np.isnan(rank_ic(series([2, 2, 2]), series([.1, .2, .3])))
    assert np.isnan(rank_ic(series([1, 2, 3]), series([.1, .1, .1])))
    assert np.isnan(rank_ic(series([1]), series([.1])))


# ---------------------------------------------------------------------------
# Quintile assignment
# ---------------------------------------------------------------------------

def test_assign_quintiles_even_split():
    # ceil(rank * 5 / 10) = ceil(rank / 2).
    assert assign_quintiles(series(range(1, 11))).tolist() == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]


def test_assign_quintiles_with_fewer_names():
    # N = 7: rank*5/7 = 0.71, 1.43, 2.14, 2.86, 3.57, 4.29, 5.
    assert assign_quintiles(series(range(1, 8))).tolist() == [1, 2, 3, 3, 4, 5, 5]


def test_assign_quintiles_tie_inside_a_group():
    # Values 5, 5 take rank 5.5 each, 5.5 / 2 = 2.75, so both are in group 3.
    values = [1, 2, 3, 4, 5, 5, 7, 8, 9, 10]
    assert assign_quintiles(series(values)).tolist() == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]


def test_assign_quintiles_tie_on_a_boundary_stays_together():
    # Values 4, 4 take rank 4.5 each, 4.5 / 2 = 2.25, so both are in group 3,
    # although rank 4 alone would be in group 2. Group 2 has one name, group 3 three.
    values = [1, 2, 3, 4, 4, 6, 7, 8, 9, 10]
    assert assign_quintiles(series(values)).tolist() == [1, 1, 2, 3, 3, 3, 4, 4, 5, 5]


def test_assign_quintiles_all_tied_share_one_group():
    # Rank 2.5 each: 2.5 * 5 / 4 = 3.125, group 4.
    assert assign_quintiles(series([7, 7, 7, 7])).tolist() == [4, 4, 4, 4]


def test_assign_quintiles_ignores_names_with_no_signal():
    # c has no signal and does not count in N: the other four are ranks 1..4,
    # N = 4, rank*5/4 = 1.25, 2.5, 3.75, 5.
    groups = assign_quintiles(series([1, 2, np.nan, 3, 4]))
    assert np.isnan(groups["c"])
    assert groups.drop("c").tolist() == [2, 3, 4, 5]


def test_assign_quintiles_with_q_ten_gives_the_top_decile():
    # 20 names: ceil(rank / 2), so ranks 19 and 20 are in group 10.
    names = [f"n{i}" for i in range(20)]
    groups = assign_quintiles(series(range(1, 21), names), q=10)
    assert groups[groups == 10].index.tolist() == ["n18", "n19"]


# ---------------------------------------------------------------------------
# Quintile spread
# ---------------------------------------------------------------------------

def test_quintile_spread():
    # Bottom (a, b) average 0.02, top (i, j) average 0.06.
    returns = series([.01, .03, 9, 9, 9, 9, 9, 9, .05, .07])
    assert quintile_spread(series(range(1, 11)), returns) == pytest.approx(0.04)


def test_quintile_spread_groups_are_set_before_returns_are_looked_at():
    # j, the top name, has no return. With all 10 names the top group is (i, j),
    # so only i counts: 0.05 - 0.02 = 0.03. Dropping j first would give N = 9
    # and a top group of (h, i), an average of 0.075 and a spread of 0.055.
    returns = series([.01, .03, 9, 9, 9, 9, 9, .10, .05, np.nan])
    assert quintile_spread(series(range(1, 11)), returns) == pytest.approx(0.03)


def test_quintile_spread_is_nan_if_a_group_has_no_return():
    returns = series([.01, .03, 9, 9, 9, 9, 9, 9, np.nan, np.nan])
    assert np.isnan(quintile_spread(series(range(1, 11)), returns))


# ---------------------------------------------------------------------------
# Cross-sectional regression
# ---------------------------------------------------------------------------

def test_standardise():
    # Mean 3, sample variance 10 / 4 = 2.5.
    z = standardise(series([1, 2, 3, 4, 5]))
    assert z.tolist() == pytest.approx([k / math.sqrt(2.5) for k in (-2, -1, 0, 1, 2)])


def test_single_signal_slope():
    # Return = 0.01 * (signal - 3), so the slope per unit of signal is 0.01 and
    # per standard deviation (sqrt 2.5) it is 0.01 * sqrt(2.5).
    signals = pd.DataFrame({"s": series([1, 2, 3, 4, 5])})
    slopes = cross_section_slopes(signals, series([-.02, -.01, 0, .01, .02]))
    assert slopes["s"] == pytest.approx(0.01 * math.sqrt(2.5))


def test_slope_standardises_over_names_with_no_return_too():
    # f has signal 11 and no return. Over all six names the mean is 26/6 and the
    # sample variance is (190/3) / 5 = 38/3. The fit on a to e still has slope
    # 0.01 per unit, so per standard deviation it is 0.01 * sqrt(38/3).
    signals = pd.DataFrame({"s": series([1, 2, 3, 4, 5, 11])})
    slopes = cross_section_slopes(signals, series([-.02, -.01, 0, .01, .02, np.nan]))
    assert slopes["s"] == pytest.approx(0.01 * math.sqrt(38 / 3))


def test_two_signal_slopes_use_only_names_with_both():
    # x1 = -3,-1,1,3 and x2 = 1,-1,-1,1 are uncorrelated with mean zero, and
    # return = 0.01*x1 + 0.03*x2. Sample sds are sqrt(20/3) and sqrt(4/3), so
    # the slopes per sd are 0.01*sqrt(20/3) and 0.03*sqrt(4/3). e has no x2 and
    # is left out of both the z-scores and the fit.
    signals = pd.DataFrame({"x1": series([-3, -1, 1, 3, 50]), "x2": series([1, -1, -1, 1, np.nan])})
    slopes = cross_section_slopes(signals, series([0, -.04, -.02, .06, 9]))
    assert slopes["x1"] == pytest.approx(0.01 * math.sqrt(20 / 3))
    assert slopes["x2"] == pytest.approx(0.03 * math.sqrt(4 / 3))


def test_slopes_are_nan_when_they_cannot_be_estimated():
    returns = series([.01, .02, .03, .04])
    constant = pd.DataFrame({"s": series([2, 2, 2, 2])})
    collinear = pd.DataFrame({"x1": series([1, 2, 3, 5]), "x2": series([2, 4, 6, 10])})
    too_few = pd.DataFrame({"s": series([1, 2])})
    assert cross_section_slopes(constant, returns).isna().all()
    assert cross_section_slopes(collinear, returns).isna().all()
    assert cross_section_slopes(too_few, returns).isna().all()


# ---------------------------------------------------------------------------
# Monthly series
# ---------------------------------------------------------------------------

DATES = pd.to_datetime(["2012-01-31", "2012-02-29"])


def monthly_frames():
    """January has three usable names; in February only a and b have a signal, c has no return."""
    signal = pd.DataFrame({"a": [1.0, 2.0], "b": [2.0, 1.0], "c": [3.0, np.nan], "d": [np.nan, np.nan]}, index=DATES)
    returns = pd.DataFrame({"a": [.01, .05], "b": [.02, .06], "c": [np.nan, .07], "d": [.5, .5]}, index=DATES)
    return signal, returns


def test_registered_minimum_is_100_names():
    assert MIN_NAMES_PER_MONTH == 100


def test_monthly_cross_section_pairs_rows_with_the_same_date():
    signal, returns = monthly_frames()
    names, month_returns = monthly_cross_section(signal, returns, DATES[1], min_names=2)
    assert names.to_dict() == {"a": 2.0, "b": 1.0}
    assert month_returns.to_dict() == {"a": .05, "b": .06}


def test_monthly_cross_section_keeps_a_name_with_no_return_as_nan():
    signal, returns = monthly_frames()
    names, month_returns = monthly_cross_section(signal, returns, DATES[0], min_names=2)
    assert names.index.tolist() == ["a", "b", "c"]
    assert np.isnan(month_returns["c"])


def test_monthly_cross_section_is_empty_below_the_minimum():
    signal, returns = monthly_frames()
    names, _ = monthly_cross_section(signal, returns, DATES[1], min_names=3)
    assert names.empty


def test_monthly_statistic_is_nan_in_a_month_below_the_minimum():
    # January: a and b have returns, in the same order as the signal, so IC = 1.
    # February has two names, below the minimum of three.
    signal, returns = monthly_frames()
    result = monthly_statistic(signal, returns, rank_ic, min_names=3)
    assert result.index.equals(signal.index)
    assert result.iloc[0] == pytest.approx(1.0)
    assert np.isnan(result.iloc[1])


def test_monthly_statistic_handles_a_month_with_no_return_row():
    signal, returns = monthly_frames()
    result = monthly_statistic(signal, returns.iloc[:1], rank_ic, min_names=2)
    assert np.isnan(result.iloc[1])


def test_monthly_counts():
    # January: a, b, c usable, c has no return. February: a, b usable. A name
    # with a return and no signal (d) is not counted.
    signal, returns = monthly_frames()
    counts = monthly_counts(signal, returns)
    assert counts["usable"].tolist() == [3, 2]
    assert counts["no_return"].tolist() == [1, 0]


def test_fama_macbeth_single_signal_month_by_month():
    # January uses the worked case of test_single_signal_slope; in February
    # the returns double, so the slope doubles. The third row has too few names.
    dates = pd.to_datetime(["2012-01-31", "2012-02-29", "2012-03-31"])
    signal = pd.DataFrame([[1.0, 2, 3, 4, 5], [1.0, 2, 3, 4, 5], [1.0, 2, np.nan, np.nan, np.nan]],
                          index=dates, columns=list("abcde"))
    returns = pd.DataFrame([[-.02, -.01, 0, .01, .02], [-.04, -.02, 0, .02, .04], [0, 0, 0, 0, 0]],
                           index=dates, columns=list("abcde"))
    slopes = fama_macbeth_slopes({"s": signal}, returns, min_names=3)
    assert slopes["s"].iloc[0] == pytest.approx(0.01 * math.sqrt(2.5))
    assert slopes["s"].iloc[1] == pytest.approx(0.02 * math.sqrt(2.5))
    assert np.isnan(slopes["s"].iloc[2])


def test_fama_macbeth_two_signals_count_names_with_both_for_the_minimum():
    # Five names have x1 and four have both, so a minimum of 5 leaves the month
    # unused and a minimum of 4 gives the worked case of the two-signal test.
    dates = pd.to_datetime(["2012-01-31"])
    x1 = pd.DataFrame([[-3.0, -1, 1, 3, 50]], index=dates, columns=list("abcde"))
    x2 = pd.DataFrame([[1.0, -1, -1, 1, np.nan]], index=dates, columns=list("abcde"))
    returns = pd.DataFrame([[0, -.04, -.02, .06, 9]], index=dates, columns=list("abcde"))
    assert fama_macbeth_slopes({"x1": x1, "x2": x2}, returns, min_names=5).isna().all(axis=None)
    slopes = fama_macbeth_slopes({"x1": x1, "x2": x2}, returns, min_names=4)
    assert slopes["x1"].iloc[0] == pytest.approx(0.01 * math.sqrt(20 / 3))
    assert slopes["x2"].iloc[0] == pytest.approx(0.03 * math.sqrt(4 / 3))


# ---------------------------------------------------------------------------
# Period summaries
# ---------------------------------------------------------------------------

def test_series_summary_mean_share_and_months():
    # Mean of .02, -.01, 0, .03 is .01; two of four are strictly positive.
    summary = series_summary(pd.Series([.02, -.01, 0.0, .03]), n_sims=100, seed=42)
    assert summary["mean"] == pytest.approx(.01)
    assert summary["share_positive"] == .5
    assert summary["months"] == 4


def test_series_summary_uses_the_project_bootstrap():
    series = pd.Series([.02, -.01, 0.0, .03, .01, .04])
    expected = bootstrap_statistic_ci(series, lambda s: s.mean(), n_sims=100, ci=0.90, seed=42)
    summary = series_summary(series, n_sims=100, seed=42)
    assert summary["ci_90_lower"] == expected["lower"]
    assert summary["ci_90_upper"] == expected["upper"]


def test_series_summary_drops_unused_months():
    summary = series_summary(pd.Series([.02, np.nan, .04]), n_sims=100, seed=42)
    assert summary["months"] == 2
    assert summary["mean"] == pytest.approx(.03)


def test_series_summary_flags_an_interval_that_excludes_zero():
    # Every value is positive, so every resampled mean is too.
    assert series_summary(pd.Series([.01, .02, .03, .04]), n_sims=100, seed=42)["excludes_zero"]
    # Symmetric around zero: the interval straddles it.
    assert not series_summary(pd.Series([-.02, -.01, .01, .02] * 3), n_sims=100, seed=42)["excludes_zero"]


def test_summarize_signal_rows_and_annualised_spread():
    dates = pd.date_range("2012-01-31", periods=6, freq="ME")
    ic = pd.Series([.1, .2, .3, .1, .2, .3], index=dates)
    spread = pd.Series([.01, .02, .03, .01, .02, .03], index=dates)
    slopes = pd.Series([.001, .002, .003, .001, .002, .003], index=dates)
    periods = {"First": (dates[:3]), "All": dates}
    table = summarize_signal("Momentum", ic, spread, {"fama_macbeth_single": slopes}, periods, n_sims=100, seed=42)

    assert len(table) == 6
    assert table[["signal"]].eq("Momentum").all(axis=None)
    row = table[(table["test"] == "quintile_spread") & (table["period"] == "First")].iloc[0]
    # Mean of .01, .02, .03 is .02, times 12 is .24; the interval scales the same way.
    assert row["mean"] == pytest.approx(.02)
    assert row["annualised_mean"] == pytest.approx(.24)
    assert row["annualised_ci_90_lower"] == pytest.approx(12 * row["ci_90_lower"])
    assert row["annualised_ci_90_upper"] == pytest.approx(12 * row["ci_90_upper"])
    assert row["months"] == 3


def test_summarize_signal_annualises_only_the_spread():
    dates = pd.date_range("2012-01-31", periods=3, freq="ME")
    series = pd.Series([.1, .2, .3], index=dates)
    table = summarize_signal("Momentum", series, series, {"fama_macbeth_single": series}, {"All": dates},
                             n_sims=100, seed=42)
    others = table[table["test"] != "quintile_spread"]
    assert others["annualised_mean"].isna().all()
