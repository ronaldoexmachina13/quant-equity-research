"""
Tests for functions that feed published numbers and had no test of their own.

Each one was found by deliberately breaking the function (a mutation test) and
seeing the whole suite still pass. Inputs are small and invented, and every
expected value is worked out by hand in the test.
"""
import math

import numpy as np
import pandas as pd
import pytest

import src.database as database
import src.fundamentals as fundamentals
from scripts.first_study.run_rf_sensitivity import rf_on_return_dates
from src.backtest import calculate_benchmark_returns, calculate_cumulative
from src.factor_check import correlation_with_reference
from src.factors import load_prices
from src.risk import summarize_risk, total_return
from src.signal_extras import block_bootstrap_ci
from src.universe import survivor_group


# ---------------------------------------------------------------------------
# Return arithmetic
# ---------------------------------------------------------------------------

def test_total_return_compounds_the_months():
    """+10%, +10%, -10% is 1.1 x 1.1 x 0.9 = 1.089, a gain of 8.9%. Adding the returns would say 10%."""
    assert total_return(pd.Series([0.10, 0.10, -0.10])) == pytest.approx(0.089)


def test_cumulative_return_compounds_the_months():
    """After each month: 10%, then 1.1 x 1.1 - 1 = 21%, then 1.089 - 1 = 8.9%. A running sum would give 10%, 20%, 10%."""
    cumulative = calculate_cumulative(pd.Series([0.10, 0.10, -0.10]))
    assert cumulative.tolist() == pytest.approx([0.10, 0.21, 0.089])


def test_benchmark_is_the_equal_weight_mean_of_the_names_with_a_return():
    """
    January: A +10%, B +20%, C has no return, so the benchmark holds A and B
    and earns 15%. February: three names earn 0%, 0% and 6%, so 2%. Summing
    the returns would give 30% and 6%.
    """
    returns = pd.DataFrame({"A": [0.10, 0.00], "B": [0.20, 0.00], "C": [np.nan, 0.06]},
                           index=pd.to_datetime(["2021-01-31", "2021-02-28"]))
    assert calculate_benchmark_returns(returns).tolist() == pytest.approx([0.15, 0.02])


def test_summarize_risk_with_a_benchmark_reports_beta_and_alpha_in_their_own_columns():
    """
    The strategy earns exactly twice the benchmark every month, so beta is 2.
    Alpha is mean(r - rf) - 2 x mean(b - rf) = (2b - rf) - 2(b - rf) = rf for
    every month, so annual alpha is 12 times the monthly risk-free rate,
    12 x (1.02^(1/12) - 1). Without a benchmark both are blank.
    """
    index = pd.date_range("2021-01-31", periods=6, freq="ME")
    benchmark = pd.Series([0.02, -0.01, 0.03, 0.00, 0.01, -0.02], index=index)
    with_benchmark = summarize_risk(2 * benchmark, "double", benchmark)
    assert with_benchmark["beta"] == pytest.approx(2.0)
    assert with_benchmark["alpha"] == pytest.approx(12 * (1.02 ** (1 / 12) - 1), abs=1e-12)
    alone = summarize_risk(2 * benchmark, "double")
    assert math.isnan(alone["beta"]) and math.isnan(alone["alpha"])


# ---------------------------------------------------------------------------
# Treasury bill alignment (first-study script that the 500-stock portfolios also use)
# ---------------------------------------------------------------------------

def test_the_bill_rate_of_month_t_is_paired_with_the_return_of_month_t():
    """
    FRED dates each month on its first day; returns are dated at the month
    end. February's return must be charged February's rate (2% a year), not
    January's (1%). A rate that is one month late would still look plausible.
    """
    yields = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2021-01-01", "2021-02-01", "2021-03-01"]))
    dates = pd.to_datetime(["2021-01-31", "2021-02-28", "2021-03-31"])
    rf = rf_on_return_dates(yields, dates)
    assert rf.tolist() == pytest.approx([1.01 ** (1 / 12) - 1, 1.02 ** (1 / 12) - 1, 1.03 ** (1 / 12) - 1])


def test_a_month_without_a_bill_rate_stops_the_run():
    yields = pd.Series([1.0], index=pd.to_datetime(["2021-01-01"]))
    with pytest.raises(ValueError, match="TB3MS has no value"):
        rf_on_return_dates(yields, pd.to_datetime(["2021-01-31", "2021-02-28"]))


# ---------------------------------------------------------------------------
# Survivorship grouping, block bootstrap, Fisher interval
# ---------------------------------------------------------------------------

def test_survivor_group_removed_means_an_interval_ended_before_the_window_end():
    """
    The window ends on 2026-08-31. A name whose last day as a member is the
    30th left before the window closed; one whose last day is the 31st was
    still in the index at the end. A current member (no end date) stayed. A
    name removed once and added again later counts as removed.
    """
    intervals = pd.DataFrame({
        "ticker": ["X", "Y", "Z", "W", "W"],
        "end_date": ["2026-08-30", "2026-08-31", None, "2015-01-01", None],
    })
    assert survivor_group(intervals, "X") == "removed"
    assert survivor_group(intervals, "Y") == "stayed"
    assert survivor_group(intervals, "Z") == "stayed"
    assert survivor_group(intervals, "W") == "removed"


class _AlwaysStartAtZero:
    """A stand-in random generator whose every block starts at month 0."""

    def integers(self, low, high=None, size=None):
        return np.zeros(size, dtype=int)


def test_block_bootstrap_joins_enough_blocks_to_rebuild_the_whole_series(monkeypatch):
    """
    Four months [12, 0, 0, 0] with blocks of 3 need 2 blocks (ceil(4/3)). If
    every block starts at month 0 the resample is months 0,1,2 then 0, cut to
    4 months: [12, 0, 0, 12], mean 6. One block would give only 3 months and
    a mean of 4, so the interval would be built on a shorter series.
    """
    monkeypatch.setattr(np.random, "default_rng", lambda seed=None: _AlwaysStartAtZero())
    result = block_bootstrap_ci(pd.Series([12.0, 0.0, 0.0, 0.0]), block_length=3, n_sims=10, seed=1)
    assert result["lower"] == pytest.approx(6.0)
    assert result["upper"] == pytest.approx(6.0)


def test_fisher_interval_uses_n_minus_3():
    """
    The Fisher z interval for a correlation has standard error 1/sqrt(n - 3).
    With 12 months that is 1/3, so the 90% half-width in z units is
    1.6448536 / 3, and the limits are tanh(atanh(r) -/+ that half-width).
    """
    x = pd.Series(range(1, 13), index=pd.date_range("2021-01-31", periods=12, freq="ME"), dtype=float)
    y = pd.Series([2, 1, 4, 3, 6, 5, 8, 7, 10, 9, 12, 11], index=x.index, dtype=float)
    out = correlation_with_reference(x, y)
    r = np.corrcoef(x, y)[0, 1]
    half = 1.6448536269514722 / 3
    assert out["months"] == 12
    assert out["pearson"] == pytest.approx(r)
    assert out["pearson_lower"] == pytest.approx(math.tanh(math.atanh(r) - half))
    assert out["pearson_upper"] == pytest.approx(math.tanh(math.atanh(r) + half))


# ---------------------------------------------------------------------------
# First-study book value from SEC facts (no network: the facts are written by hand)
# ---------------------------------------------------------------------------

def _facts(equity_rows, share_rows):
    def entries(rows):
        return [{"end": end, "filed": filed, "val": value} for end, filed, value in rows]
    return {"facts": {
        "us-gaap": {"StockholdersEquity": {"units": {"USD": entries(equity_rows)}}},
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": entries(share_rows)}}},
    }}


def test_book_value_becomes_known_when_both_equity_and_share_count_are_filed(monkeypatch):
    """
    Equity of 1,000 for the quarter ended 31 March was filed on 5 May. The share
    count of 100 (cover page, as of 30 April) was filed on 7 May. Book value per
    share is 10, and it is usable from 7 May, the later date, because before
    then the share count was not public. The June equity of 1,100 has no share
    count within 45 days (30 April is 61 days away), so it gets no record.
    """
    facts = _facts(equity_rows=[("2021-03-31", "2021-05-05", 1000.0), ("2021-06-30", "2021-08-04", 1100.0)],
                   share_rows=[("2021-04-30", "2021-05-07", 100.0)])
    monkeypatch.setattr(fundamentals, "get_company_facts", lambda ticker: facts)
    records = fundamentals.get_book_value_per_share("TEST")
    assert len(records) == 1
    row = records.iloc[0]
    assert row["end_date"] == pd.Timestamp("2021-03-31")
    assert row["filed_date"] == pd.Timestamp("2021-05-07")
    assert row["book_value_per_share"] == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# SQLite round trip (first-study storage)
# ---------------------------------------------------------------------------

def test_prices_and_book_value_survive_a_round_trip_through_sqlite(tmp_path, monkeypatch):
    """
    Missing prices are not stored, a second save with a new value replaces the
    row instead of adding one, and the wide frame that comes back has dated,
    sorted rows and a gap where the price was missing.
    """
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "round_trip.db"))
    database.create_tables()
    dates = pd.to_datetime(["2021-01-29", "2021-02-26", "2021-03-31"])
    prices = pd.DataFrame({"AAA": [10.0, 11.0, 12.0], "BBB": [20.0, np.nan, 22.0]}, index=dates)
    prices.index.name = "Date"
    database.save_prices(prices)

    loaded = load_prices()
    assert list(loaded.index) == list(dates)
    assert loaded.loc["2021-02-26", "AAA"] == pytest.approx(11.0)
    assert np.isnan(loaded.loc["2021-02-26", "BBB"])

    prices.loc["2021-02-26", "AAA"] = 11.5
    database.save_prices(prices)
    again = load_prices()
    assert again.loc["2021-02-26", "AAA"] == pytest.approx(11.5)
    assert again.notna().sum().sum() == 5          # 6 cells, one missing, and no duplicate rows

    book = pd.DataFrame({"AAA": [4.0, 4.0, 5.0]}, index=pd.to_datetime(["2021-01-31", "2021-02-28", "2021-03-31"]))
    book.index.name = "date"
    database.save_book_value(book)
    stored = database.load_book_value()
    assert stored["AAA"].tolist() == pytest.approx([4.0, 4.0, 5.0])
