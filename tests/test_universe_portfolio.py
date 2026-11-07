"""
Unit tests for src/universe_portfolio.py (Phase 4, Stage 4, portfolio tests).

All inputs are small invented examples whose answers were worked out by
hand. No network, no real data.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.backtest import run_backtest
from src.risk import max_drawdown, sharpe_ratio
from src.universe_portfolio import (
    top_group_weights, universe_weights, held_returns, held_without_return, portfolio_series, top_group_changes,
    max_drawdown_from_start, period_metrics, strategy_summary, reference_summary, returns_frame,
    survivorship_monthly, survivorship_summary, spy_month_end_returns, spy_overlap_failures, stage3_count_failures,
    portfolio_outputs, BASES, GROSS, NET_DRIFT, NET_EXISTING, COST_BPS, SIZES,
)

FLAT_2PCT_MONTHLY = 1.02 ** (1 / 12) - 1
JAN, FEB, MAR = pd.to_datetime(["2012-01-31", "2012-02-29", "2012-03-31"])


def frame(rows: dict, dates) -> pd.DataFrame:
    return pd.DataFrame(rows, index=pd.DatetimeIndex(dates))


# --- Sizes and weights ---

def test_registered_sizes_and_cost():
    assert SIZES == {"top_decile": 10, "top_quintile": 5}
    assert COST_BPS == 10


def test_top_quintile_of_ten_names_holds_the_top_two():
    """ceil(rank x 5 / 10): rank 9 gives ceil(4.5) = 5, rank 8 gives 4. So ranks 9 and 10 are held at 1/2."""
    signal = frame({f"N{i}": [float(i)] for i in range(1, 11)}, [JAN])
    weights = top_group_weights(signal, 5)
    assert list(weights.columns[weights.loc[JAN] > 0]) == ["N9", "N10"]
    assert weights.loc[JAN, "N9"] == 0.5 and weights.loc[JAN].sum() == pytest.approx(1.0)


def test_top_group_tie_on_the_boundary_is_held_together():
    """
    Values 1..7, 8, 8, 10: the two 8s share rank 8.5, ceil(8.5 x 5 / 10) =
    ceil(4.25) = 5, so both join the top group with the 10. Three names at 1/3.
    """
    values = [1, 2, 3, 4, 5, 6, 7, 8, 8, 10]
    signal = frame({f"N{i}": [float(v)] for i, v in enumerate(values)}, [JAN])
    weights = top_group_weights(signal, 5)
    assert sorted(weights.columns[weights.loc[JAN] > 0]) == ["N7", "N8", "N9"]
    assert weights.loc[JAN, "N7"] == pytest.approx(1 / 3)


def test_top_group_size_varies_with_the_number_of_names():
    """
    January has 10 names (top quintile = 2). February has 15: ceil(13 x 5 / 15)
    = ceil(4.33) = 5 and ceil(12 x 5 / 15) = 4, so 3 names at 1/3.
    """
    signal = frame({f"N{i}": [float(i) if i <= 10 else np.nan, float(i)] for i in range(1, 16)}, [JAN, FEB])
    weights = top_group_weights(signal, 5)
    assert (weights.loc[JAN] > 0).sum() == 2
    assert sorted(weights.columns[weights.loc[FEB] > 0]) == ["N13", "N14", "N15"]
    assert weights.loc[FEB, "N13"] == pytest.approx(1 / 3)


def test_top_decile_of_twenty_names_holds_two():
    signal = frame({f"N{i}": [float(i)] for i in range(1, 21)}, [JAN])
    weights = top_group_weights(signal, 10)
    assert list(weights.columns[weights.loc[JAN] > 0]) == ["N19", "N20"]


def test_nan_names_get_no_weight_and_do_not_count_in_n():
    """
    Five names with a signal and five NaN. N = 5, so the top quintile is the
    single highest name. A row with no signal at all holds nothing.
    """
    signal = frame({**{f"N{i}": [float(i), np.nan] for i in range(1, 6)},
                    **{f"X{i}": [np.nan, np.nan] for i in range(1, 6)}}, [JAN, FEB])
    weights = top_group_weights(signal, 5)
    assert list(weights.columns[weights.loc[JAN] > 0]) == ["N5"]
    assert weights.loc[JAN, "N5"] == 1.0
    assert weights.loc[FEB].sum() == 0


def test_universe_weights_equal_over_usable_names():
    mask = frame({"A": [True, True], "B": [True, False], "C": [False, False]}, [JAN, FEB])
    weights = universe_weights(mask)
    assert list(weights.loc[JAN]) == [0.5, 0.5, 0.0]
    assert list(weights.loc[FEB]) == [1.0, 0.0, 0.0]


def test_top_group_changes_lists_months_that_differ():
    a = frame({"A": [1.0, 1.0], "B": [2.0, 2.0]}, [JAN, FEB])
    b = frame({"A": [1.0, 3.0], "B": [2.0, 2.0]}, [JAN, FEB])
    assert top_group_changes(a, b, 2) == ["2012-02"]
    assert top_group_changes(a, a.copy(), 2) == []


# --- Returns, turnover and costs ---

def test_held_name_with_no_return_is_dropped_and_the_rest_rescaled():
    """A and B at 1/2 each. A has no return, B earns 10%: the month's return is 10%, not 5%."""
    weights = frame({"A": [0.5], "B": [0.5]}, [JAN])
    returns = frame({"A": [np.nan], "B": [0.10]}, [JAN])
    assert held_returns(weights, returns).loc[JAN] == pytest.approx(0.10)
    assert held_without_return(weights, returns).loc[JAN] == 1


def test_held_returns_equal_run_backtest_when_every_holding_has_a_return():
    weights = frame({"A": [0.5, 0.0], "B": [0.5, 1.0], "C": [0.0, 0.0]}, [JAN, FEB])
    returns = frame({"A": [0.02, -0.01], "B": [0.04, 0.03], "C": [np.nan, 0.5]}, [JAN, FEB])
    pd.testing.assert_series_equal(held_returns(weights, returns), run_backtest(weights, returns), check_names=False)


def test_held_returns_nan_when_no_holding_has_a_return():
    weights = frame({"A": [1.0]}, [JAN])
    returns = frame({"A": [np.nan]}, [JAN])
    assert np.isnan(held_returns(weights, returns).loc[JAN])


def test_first_month_is_a_purchase_from_cash_on_both_bases():
    """
    January 2012 buys the whole book: turnover 1 on both bases, so the cost is
    1 x 0.001 x 2 = 0.002 off the gross return (Amendment 13, decision 9).
    """
    weights = frame({"A": [0.5, 0.5], "B": [0.5, 0.5]}, [JAN, FEB])
    returns = frame({"A": [0.01, 0.0], "B": [0.03, 0.0]}, [JAN, FEB])
    series = portfolio_series(weights, returns)
    assert series.loc[JAN, "turnover_existing"] == 1.0
    assert series.loc[JAN, "turnover_drift"] == 1.0
    assert series.loc[JAN, GROSS] == pytest.approx(0.02)
    assert series.loc[JAN, NET_EXISTING] == pytest.approx(0.018)
    assert series.loc[JAN, NET_DRIFT] == pytest.approx(0.018)


def test_name_without_return_is_sold_at_its_last_weight_in_drift_turnover():
    """
    Amendment 13, decision 10. January: A and B at 1/2; A has no return, B
    earns 10%. The January return is 10%. Entering February, A counts as 0.5
    (return taken as 0) and B as 0.55, so pre-trade weights are 0.5/1.05 and
    0.55/1.05. February holds B only: drift turnover = 0.5 x (0.5/1.05 +
    (1 - 0.55/1.05)) = 0.5/1.05. Target-weight turnover is 0.5.
    """
    weights = frame({"A": [0.5, 0.0], "B": [0.5, 1.0]}, [JAN, FEB])
    returns = frame({"A": [np.nan, np.nan], "B": [0.10, 0.02]}, [JAN, FEB])
    series = portfolio_series(weights, returns)
    assert series.loc[JAN, GROSS] == pytest.approx(0.10)
    assert series.loc[FEB, "turnover_drift"] == pytest.approx(0.5 / 1.05)
    assert series.loc[FEB, "turnover_existing"] == pytest.approx(0.5)
    assert series.loc[FEB, NET_DRIFT] == pytest.approx(0.02 - 0.5 / 1.05 * 0.002)
    assert series.loc[JAN, "names_without_return"] == 1


# --- Period metrics and tests ---

def test_max_drawdown_counts_a_first_month_loss_from_1():
    """-10% then +5%: from 1.0 the trough is 0.9, a 10% drawdown. max_drawdown() starts at 0.9 and shows 0."""
    returns = pd.Series([-0.10, 0.05], index=[JAN, FEB])
    assert max_drawdown_from_start(returns) == pytest.approx(-0.10)
    assert max_drawdown(returns) == pytest.approx(0.0)


def test_period_metrics_at_constant_2pct_match_the_flat_sharpe():
    returns = pd.Series([0.01, -0.02, 0.03], index=[JAN, FEB, MAR])
    rf = pd.Series(FLAT_2PCT_MONTHLY, index=returns.index)
    metrics = period_metrics(returns, rf)
    assert metrics["months"] == 3
    assert metrics["sharpe_tbill"] == pytest.approx(metrics["sharpe_flat_2pct"], abs=1e-12)
    assert metrics["sharpe_flat_2pct"] == pytest.approx(sharpe_ratio(returns))


def test_bases_charge_the_benchmark_on_drift_in_every_net_test():
    assert BASES == {GROSS: (GROSS, GROSS), NET_DRIFT: (NET_DRIFT, NET_DRIFT), NET_EXISTING: (NET_EXISTING, NET_DRIFT)}


def _two_series(dates):
    rng = np.random.default_rng(0)
    def one():
        gross = pd.Series(rng.normal(0.01, 0.04, len(dates)), index=dates)
        return pd.DataFrame({"names_held": 3, GROSS: gross, "turnover_existing": 0.2, "turnover_drift": 0.3,
                             NET_EXISTING: gross - 0.0004, NET_DRIFT: gross - 0.0006})
    return one(), one()


def test_strategy_summary_rows_bases_and_headline_flag():
    dates = pd.period_range("2012-01", "2013-12", freq="M").to_timestamp(how="end").normalize()
    strategy, benchmark = _two_series(dates)
    rf = pd.Series(0.001, index=dates)
    periods = {"first": dates[:12], "all": dates}
    summary = strategy_summary("Value", "top_decile", strategy, benchmark, "Bench", rf, periods, n_sims=50, seed=42)
    assert len(summary) == 2 * 3
    assert list(summary.loc[summary["headline_test"], "basis"].unique()) == [GROSS]
    existing = summary[(summary["basis"] == NET_EXISTING) & (summary["period"] == "all")].iloc[0]
    assert existing["benchmark_basis"] == NET_DRIFT
    expected = (existing["sharpe_tbill"] - existing["benchmark_sharpe_tbill"])
    assert existing["sharpe_diff_tbill"] == pytest.approx(expected, rel=1e-12)
    assert existing["avg_turnover_existing"] == pytest.approx(0.2)
    first = summary[summary["period"] == "first"].iloc[0]
    assert first["months"] == 12


def test_reference_summary_for_spy_has_no_turnover_or_test():
    dates = pd.DatetimeIndex([JAN, FEB, MAR])
    spy = pd.DataFrame({GROSS: [0.01, 0.02, -0.01]}, index=dates)
    rows = reference_summary("SPY", spy, [GROSS], pd.Series(0.001, index=dates), {"all": dates})
    assert len(rows) == 1
    assert "avg_turnover_drift" not in rows.columns and "sharpe_diff_tbill" not in rows.columns
    assert rows.loc[0, "headline_test"] == False  # noqa: E712


def test_returns_frame_keeps_every_column_and_the_rate():
    dates = pd.DatetimeIndex([JAN, FEB])
    series = pd.DataFrame({GROSS: [0.01, 0.02], "turnover_drift": [1.0, 0.1]}, index=dates)
    out = returns_frame("Momentum", "top_quintile", series, pd.Series([0.001, 0.002], index=dates))
    assert list(out.columns) == ["date", "period", "strategy", "size", GROSS, "turnover_drift", "rf_monthly"]
    assert list(out["rf_monthly"]) == [0.001, 0.002]


# --- Survivorship ---

def test_survivorship_means_with_an_empty_group_month():
    """
    A is removed, B and C stayed. January: A 4%, B 1%, C 3%. February: A is
    not usable, B 2%, C 0%. Removed mean = 4% over 1 month, with 1 empty
    month; stayed mean = average of 2% and 1% = 1.5%. Difference 2.5%.
    """
    mask = frame({"A": [True, False], "B": [True, True], "C": [True, True]}, [JAN, FEB])
    returns = frame({"A": [0.04, 0.09], "B": [0.01, 0.02], "C": [0.03, 0.0]}, [JAN, FEB])
    groups = pd.Series({"A": "removed", "B": "stayed", "C": "stayed"})
    monthly = survivorship_monthly(mask, returns, groups)
    summary = survivorship_summary(monthly, {"all": pd.DatetimeIndex([JAN, FEB])}, "Momentum usable").set_index("group")
    assert summary.loc["removed", "months_empty"] == 1
    assert summary.loc["removed", "mean_monthly_return"] == pytest.approx(0.04)
    assert summary.loc["removed", "names_per_month_avg"] == pytest.approx(0.5)
    assert summary.loc["stayed", "mean_monthly_return"] == pytest.approx(0.015)
    assert summary.loc["removed_minus_stayed", "mean_monthly_return"] == pytest.approx(0.025)
    assert summary.loc["removed_minus_stayed", "annualised_mean"] == pytest.approx(0.30)
    assert (summary["universe_set"] == "Momentum usable").all()


def test_survivorship_leaves_out_usable_names_without_a_return():
    mask = frame({"A": [True], "B": [True]}, [JAN])
    returns = frame({"A": [np.nan], "B": [0.02]}, [JAN])
    monthly = survivorship_monthly(mask, returns, pd.Series({"A": "stayed", "B": "stayed"}))
    assert monthly.loc[JAN, "stayed_names"] == 1
    assert monthly.loc[JAN, "stayed_mean"] == pytest.approx(0.02)


# --- SPY ---

def test_spy_month_end_returns_use_the_last_trading_day():
    """Daily closes; only the calendar's last trading days count. 100 -> 110 -> 99 gives +10% and -10%."""
    daily = pd.DataFrame({"Adj Close": [105.0, 100.0, 110.0, 50.0, 99.0]},
                         index=pd.to_datetime(["2012-01-30", "2012-01-31", "2012-02-28", "2012-03-29", "2012-03-30"]))
    calendar = pd.Series(pd.to_datetime(["2012-01-31", "2012-02-28", "2012-03-30"]),
                         index=["2012-01", "2012-02", "2012-03"])
    returns = spy_month_end_returns(daily, calendar)
    assert list(returns.index) == [JAN, FEB, MAR]
    assert np.isnan(returns.loc[JAN])
    assert returns.loc[FEB] == pytest.approx(0.10)
    assert returns.loc[MAR] == pytest.approx(-0.10)


def test_spy_overlap_passes_within_tolerance_and_fails_outside():
    saved = pd.Series([0.01, 0.02], index=[JAN, FEB])
    assert spy_overlap_failures(saved + 5e-7, saved) == []
    failures = spy_overlap_failures(pd.Series([0.01, 0.02 + 2e-6], index=[JAN, FEB]), saved)
    assert len(failures) == 1 and failures[0].startswith("2012-02")


def test_spy_overlap_fails_on_a_missing_month_or_empty_saved_series():
    saved = pd.Series([0.01, 0.02], index=[JAN, FEB])
    assert len(spy_overlap_failures(pd.Series([0.01], index=[JAN]), saved)) == 1
    assert len(spy_overlap_failures(pd.Series([0.01, np.nan], index=[JAN, FEB]), saved)) == 1
    assert spy_overlap_failures(saved, pd.Series(dtype=float)) == ["the saved SPY series is empty"]


# --- Checks and outputs ---

def test_stage3_count_failures_exact_match_and_missing_month():
    stage3 = pd.DataFrame({"date": ["2012-01-31", "2012-02-29"], "usable_momentum": [353, 354]})
    assert stage3_count_failures(pd.Series([353, 354], index=[JAN, FEB]), stage3, "usable_momentum", "M") == []
    assert len(stage3_count_failures(pd.Series([353, 355], index=[JAN, FEB]), stage3, "usable_momentum", "M")) == 1
    assert len(stage3_count_failures(pd.Series([353], index=[JAN]), stage3, "usable_momentum", "M")) == 1


def test_portfolio_outputs_registered_names_and_suffixes():
    paths = {key: Path(p).name for key, p in portfolio_outputs(Path("results")).items()}
    assert paths[("headline", "portfolio_returns")] == "universe_study_portfolio_returns.csv"
    assert paths[("headline", "portfolio_summary")] == "universe_study_portfolio_summary.csv"
    assert paths[("headline", "survivorship")] == "universe_study_survivorship.csv"
    assert paths[("excl_24", "portfolio_summary")] == "universe_study_portfolio_summary_excl_24.csv"
    assert paths[("excl_37", "portfolio_returns")] == "universe_study_portfolio_returns_excl_37.csv"
    assert len(paths) == 7
    assert ("excl_24", "survivorship") not in paths
