"""
Unit tests for src/survivorship_by_year.py (Amendment 15, decision 7).

All inputs are small invented examples whose answers were worked out by
hand. No network, no real data.
"""
import numpy as np
import pandas as pd
import pytest

from src.risk import annualized_return, sharpe_ratio_tbill, bootstrap_sharpe_diff_tbill
from src.survivorship_by_year import (
    yearly_shares, share_tested_by_year, share_failures, yearly_mean_ic, period_ic_failures, strategy_and_benchmark,
    yearly_sharpe, period_sharpe_failures, diagnostic_failures, survivorship_by_year_table, yearly_total_failures,
    SIGNALS, UNIVERSE_SET, BENCHMARK, TABLE_COLUMNS, BY_YEAR_NOTE,
)
from src.universe_portfolio import MOMENTUM_BENCHMARK, VALUE_BENCHMARK

FULL = "Full period"
MONTHS = pd.date_range("2020-01-31", periods=20, freq="ME")   # 12 months of 2020 and 8 of 2021


def by_year_frame():
    rows = []
    for year, scale in ((2020, 1.0), (2021, 1.1)):
        for group, mom, val, mm in (("all", 0.70, 0.50, 200), ("removed", 0.40, 0.30, 50), ("stayed", 0.80, 0.57, 150)):
            rows.append({"year": year, "group": group, "share_usable_momentum": mom * scale,
                         "share_usable_value_combined": val * scale, "member_months": mm})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Shares
# ---------------------------------------------------------------------------

def test_yearly_shares_picks_the_column_for_each_group():
    shares = yearly_shares(by_year_frame(), "share_usable_value_combined")
    assert list(shares.columns) == ["share_usable_all", "share_usable_removed", "share_usable_stayed"]
    assert shares.loc[2020].tolist() == pytest.approx([0.50, 0.30, 0.57])
    assert shares.loc[2021, "share_usable_all"] == pytest.approx(0.55)


def test_tested_shares_by_hand():
    """2020: (40 + 60) / (100 + 100) = 0.5. 2021: 50 / 200 = 0.25."""
    counts = pd.DataFrame({"date": ["2020-01-31", "2020-02-29", "2021-01-31"], "universe_size": [100, 100, 200],
                           "usable_value_combined": [40, 60, 50]})
    shares = share_tested_by_year(counts, "usable_value_combined")
    assert shares.to_dict() == pytest.approx({2020: 0.5, 2021: 0.25})
    assert shares.name == "share_usable_tested"


def coverage_monthly():
    """Two reliable months of 2020 and one unreliable month with numbers that would break the shares."""
    return pd.DataFrame({"month": ["2020-01", "2020-02", "2020-03"], "reliable": [1, 1, 0],
                         "members": [100, 100, 999], "usable_momentum": [60, 80, 1], "usable_value_combined": [50, 50, 1]})


def coverage_by_year(momentum_all=0.7):
    rows = [{"year": 2020, "group": "all", "share_usable_momentum": momentum_all, "share_usable_value_combined": 0.5,
             "member_months": 200},
            {"year": 2020, "group": "removed", "share_usable_momentum": 0.4, "share_usable_value_combined": 0.3,
             "member_months": 50},
            {"year": 2020, "group": "stayed", "share_usable_momentum": 0.8, "share_usable_value_combined": 0.57,
             "member_months": 150}]
    return pd.DataFrame(rows)


def test_share_failures_passes_and_ignores_unreliable_months():
    """2020: momentum (60 + 80) / 200 = 0.7, value (50 + 50) / 200 = 0.5. March is unreliable."""
    assert share_failures(coverage_monthly(), coverage_by_year()) == []


def test_share_failures_flags_a_wrong_share_and_groups_that_do_not_add_up():
    assert len(share_failures(coverage_monthly(), coverage_by_year(momentum_all=0.71))) == 1
    frame = coverage_by_year()
    frame.loc[frame["group"] == "removed", "member_months"] = 49
    failures = share_failures(coverage_monthly(), frame)
    assert failures == ["2020: removed plus stayed member-months 199, all 200"]


# ---------------------------------------------------------------------------
# Rank IC
# ---------------------------------------------------------------------------

def ic_frame():
    return pd.DataFrame({"date": ["2020-01-31", "2020-02-29", "2020-03-31", "2021-01-31", "2020-01-31"],
                         "signal": ["Momentum"] * 4 + ["Value"], "rank_ic": [np.nan, 0.1, 0.3, 0.2, 0.9]})


def test_yearly_mean_ic_by_hand():
    """2020: three calendar months, two with an IC, mean (0.1 + 0.3) / 2 = 0.2. The Value row is ignored."""
    table = yearly_mean_ic(ic_frame(), "Momentum")
    assert table.loc[2020].tolist() == pytest.approx([3, 2, 0.2])
    assert table.loc[2021].tolist() == pytest.approx([1, 1, 0.2])


def test_period_ic_failures_passes_and_flags():
    periods = {FULL: pd.to_datetime(["2020-01-31", "2020-02-29", "2020-03-31", "2021-01-31"])}
    saved = pd.DataFrame({"test": ["rank_ic"], "signal": ["Momentum"], "period": [FULL], "months": [3], "mean": [0.2]})
    assert period_ic_failures(ic_frame(), saved, "Momentum", periods) == []
    assert len(period_ic_failures(ic_frame(), saved.assign(mean=0.21), "Momentum", periods)) == 1
    assert len(period_ic_failures(ic_frame(), saved.assign(months=4), "Momentum", periods)) == 1
    assert period_ic_failures(ic_frame(), saved, "Value", periods) == [f"Value {FULL}: no saved rank_ic row"]


# ---------------------------------------------------------------------------
# Sharpe
# ---------------------------------------------------------------------------

def series_values(k: int) -> list[float]:
    return [0.01 * (((t * 5 + k * 3) % 7) - 3) + 0.002 * k for t in range(len(MONTHS))]


def returns_long_frame():
    """Top-decile rows for each signal, a top-quintile row that must be ignored, and both benchmarks."""
    rows = []
    for k, (strategy, size) in enumerate([("Momentum", "top_decile"), ("Value", "top_decile"),
                                          ("Combined", "top_decile"), ("Momentum", "top_quintile"),
                                          (MOMENTUM_BENCHMARK, np.nan), (VALUE_BENCHMARK, np.nan)]):
        for date, value in zip(MONTHS, series_values(k)):
            rows.append({"date": date.strftime("%Y-%m-%d"), "strategy": strategy, "size": size, "gross": value,
                         "rf_monthly": 0.001})
    return pd.DataFrame(rows)


def test_strategy_and_benchmark_uses_top_decile_and_the_registered_benchmark():
    strategy, benchmark, rf = strategy_and_benchmark(returns_long_frame(), "Combined")
    assert strategy.tolist() == pytest.approx(series_values(2))
    assert benchmark.tolist() == pytest.approx(series_values(5))
    momentum, momentum_benchmark, _ = strategy_and_benchmark(returns_long_frame(), "Momentum")
    assert momentum.tolist() == pytest.approx(series_values(0))
    assert momentum_benchmark.tolist() == pytest.approx(series_values(4))
    assert (rf == 0.001).all()


def test_yearly_sharpe_levels_difference_and_interval_per_year():
    strategy, benchmark, rf = strategy_and_benchmark(returns_long_frame(), "Momentum")
    table = yearly_sharpe(strategy, benchmark, rf, n_sims=50, seed=42)
    assert list(table.index) == [2020, 2021]
    assert table.loc[2021, "top_decile_months"] == 8
    s, b, r = strategy[strategy.index.year == 2021], benchmark[benchmark.index.year == 2021], rf[rf.index.year == 2021]
    assert table.loc[2021, "top_decile_sharpe_tbill"] == pytest.approx(sharpe_ratio_tbill(s, r))
    assert table.loc[2021, "benchmark_annualized_return"] == pytest.approx(annualized_return(b))
    assert table.loc[2021, "sharpe_diff_tbill"] == pytest.approx(sharpe_ratio_tbill(s, r) - sharpe_ratio_tbill(b, r))
    expected = bootstrap_sharpe_diff_tbill(s, b, r, n_sims=50, seed=42)
    assert table.loc[2021, "ci_90_lower_tbill"] == pytest.approx(expected["lower"])
    assert table.loc[2021, "ci_90_upper_tbill"] == pytest.approx(expected["upper"])


def saved_portfolio_summary(returns_long, signal="Momentum", periods=None):
    strategy, benchmark, rf = strategy_and_benchmark(returns_long, signal)
    rows = []
    for period, dates in periods.items():
        s, b, r = strategy.loc[dates], benchmark.loc[dates], rf.loc[dates]
        rows.append({"period": period, "strategy": signal, "size": "top_decile", "basis": "gross", "months": len(s),
                     "sharpe_tbill": sharpe_ratio_tbill(s, r), "benchmark_sharpe_tbill": sharpe_ratio_tbill(b, r),
                     "sharpe_diff_tbill": sharpe_ratio_tbill(s, r) - sharpe_ratio_tbill(b, r)})
    return pd.DataFrame(rows)


def test_period_sharpe_failures_passes_and_flags():
    periods = {FULL: MONTHS}
    returns_long = returns_long_frame()
    saved = saved_portfolio_summary(returns_long, periods=periods)
    assert period_sharpe_failures(returns_long, saved, "Momentum", periods) == []
    changed = saved.assign(sharpe_tbill=saved["sharpe_tbill"] + 1e-6)
    assert len(period_sharpe_failures(returns_long, changed, "Momentum", periods)) == 1
    assert period_sharpe_failures(returns_long, saved, "Value", periods) == [f"Value {FULL}: no saved gross top-decile row"]


# ---------------------------------------------------------------------------
# Registered diagnostic
# ---------------------------------------------------------------------------

def diagnostic():
    return pd.DataFrame({"period": [FULL, FULL, FULL], "universe_set": ["Momentum usable"] * 3,
                         "group": ["removed", "stayed", "removed_minus_stayed"], "months": [20, 20, 20],
                         "months_empty": [0, 0, np.nan], "names_per_month_avg": [50.0, 300.0, np.nan],
                         "mean_monthly_return": [0.004, 0.012, -0.008], "annualised_mean": [0.048, 0.144, -0.096]})


def test_diagnostic_failures_matches_nan_with_nan_and_flags_a_change_and_a_missing_row():
    assert diagnostic_failures(diagnostic(), diagnostic()) == []
    changed = diagnostic()
    changed.loc[0, "mean_monthly_return"] = 0.0041
    assert len(diagnostic_failures(changed, diagnostic())) == 1
    assert len(diagnostic_failures(diagnostic().iloc[:2], diagnostic())) == 1


# ---------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------

def table_inputs():
    ic_rows = lambda signal, k: pd.DataFrame({"date": MONTHS.strftime("%Y-%m-%d"), "signal": signal,
                                              "rank_ic": [0.01 * ((t + k) % 5 - 2) for t in range(len(MONTHS))]})
    ic = {"Momentum": ic_rows("Momentum", 0), "Value": pd.concat([ic_rows("Value", 1), ic_rows("Combined", 2)]),
          "Combined": pd.concat([ic_rows("Value", 1), ic_rows("Combined", 2)])}
    tested = {"Momentum": pd.Series({2020: 0.70, 2021: 0.77}, name="share_usable_tested"),
              "Value": pd.Series({2020: 0.49, 2021: 0.54}, name="share_usable_tested"),
              "Combined": pd.Series({2020: 0.49, 2021: 0.54}, name="share_usable_tested")}
    return by_year_frame(), tested, ic, returns_long_frame()


def test_table_has_one_row_per_year_and_signal_in_the_registered_layout():
    table = survivorship_by_year_table(*table_inputs(), n_sims=20, seed=42)
    assert list(table.columns) == TABLE_COLUMNS
    assert len(table) == 6
    assert table[["year", "signal"]].values.tolist() == [[y, s] for s in SIGNALS for y in (2020, 2021)]
    assert table.loc[table["year"] == 2021, "partial_year"].all()
    assert not table.loc[table["year"] == 2020, "partial_year"].any()
    assert (table["months"] == table["top_decile_months"]).all()


def test_table_maps_each_signal_to_its_share_column_and_benchmark():
    table = survivorship_by_year_table(*table_inputs(), n_sims=20, seed=42).set_index(["signal", "year"])
    assert table.loc[("Momentum", 2020), "share_usable_all"] == pytest.approx(0.70)
    assert table.loc[("Value", 2020), "share_usable_all"] == pytest.approx(0.50)
    assert table.loc[("Combined", 2021), "share_usable_stayed"] == pytest.approx(0.57 * 1.1)
    assert table.loc[("Value", 2021), "share_usable_tested"] == pytest.approx(0.54)
    assert table.loc[("Momentum", 2020), "benchmark"] == MOMENTUM_BENCHMARK
    assert table.loc[("Combined", 2020), "benchmark"] == VALUE_BENCHMARK
    assert table.loc[("Combined", 2020), "universe_set"] == UNIVERSE_SET["Combined"]
    assert set(table["basis"]) == {"gross"}


def test_table_note_says_registered_signals_and_descriptive():
    table = survivorship_by_year_table(*table_inputs(), n_sims=20, seed=42)
    assert set(table["universe_note"]) == {BY_YEAR_NOTE}
    assert "registered Momentum, Value and Combined" in BY_YEAR_NOTE
    assert "not the 12-1 sensitivity" in BY_YEAR_NOTE
    assert "Descriptive" in BY_YEAR_NOTE
    assert "—" not in BY_YEAR_NOTE


def test_benchmarks_are_the_registered_ones():
    assert BENCHMARK == {"Momentum": MOMENTUM_BENCHMARK, "Value": VALUE_BENCHMARK, "Combined": VALUE_BENCHMARK}
    assert UNIVERSE_SET == {"Momentum": "Momentum usable", "Value": "Value and Combined usable",
                            "Combined": "Value and Combined usable"}


def test_yearly_total_failures_passes_and_flags():
    table = survivorship_by_year_table(*table_inputs(), n_sims=20, seed=42)
    signal_summary = pd.DataFrame({"test": "rank_ic", "signal": list(SIGNALS), "period": FULL, "months": 20})
    portfolio_summary = pd.DataFrame({"strategy": list(SIGNALS), "size": "top_decile", "basis": "gross",
                                      "period": FULL, "months": 20})
    assert yearly_total_failures(table, signal_summary, portfolio_summary, FULL) == []
    wrong = portfolio_summary.assign(months=[20, 19, 20])
    assert yearly_total_failures(table, signal_summary, wrong, FULL) == [
        "Value: yearly top-decile months add up to 20, saved full period [19]"]
