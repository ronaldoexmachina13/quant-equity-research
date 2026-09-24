"""
Unit tests for the factor-construction logic in src/factors.py and
src/portfolio.py. These are pure functions of a price/book-value
DataFrame -- no database or network involved -- so we build small,
hand-checkable synthetic inputs rather than touching real market data.
"""
import pandas as pd
import pytest

from src.factors import calculate_momentum, calculate_value_score, calculate_combined_score
from src.portfolio import build_portfolio


def test_calculate_momentum_matches_formula_by_hand():
    """
    14 months of a single ticker rising by a fixed $2/month: price[i] = 100 + 2*i.
    With the default lookback=12, skip=1:
        momentum[13] = price[12] / price[1] - 1 = 124 / 102 - 1
    checked here against the value worked out by hand, not just "is it a number."
    """
    dates = pd.date_range("2020-01-31", periods=14, freq="ME")
    prices = pd.DataFrame({"A": [100 + 2 * i for i in range(14)]}, index=dates)

    momentum = calculate_momentum(prices)

    expected = 124 / 102 - 1
    assert momentum["A"].iloc[13] == pytest.approx(expected, rel=1e-9)


def test_calculate_momentum_skips_most_recent_month():
    """
    The whole point of the skip-month convention is that momentum should
    NOT be affected by the single most recent month's price move --
    changing only the final month's price should leave momentum[13]
    unchanged, since it's built from shift(1) and shift(12), not shift(0).
    """
    dates = pd.date_range("2020-01-31", periods=14, freq="ME")
    prices_a = pd.DataFrame({"A": [100 + 2 * i for i in range(14)]}, index=dates)
    prices_b = prices_a.copy()
    prices_b.loc[dates[13], "A"] = 9999  # blow up the most recent month only

    momentum_a = calculate_momentum(prices_a)
    momentum_b = calculate_momentum(prices_b)

    assert momentum_a["A"].iloc[13] == pytest.approx(momentum_b["A"].iloc[13], rel=1e-9)


def test_calculate_value_score_lower_pb_scores_higher():
    """
    Value's whole premise: a cheaper stock (lower Price/Book) should get
    the HIGHER (less negative) score, since build_portfolio() always
    picks the highest scores. Ticker A is priced at 2x book, ticker B at
    10x book -- A is "cheaper" and must score higher.
    """
    dates = pd.date_range("2020-01-31", periods=2, freq="ME")
    prices = pd.DataFrame({"A": [100, 100], "B": [100, 100]}, index=dates)
    book_value = pd.DataFrame({"A": [50, 50], "B": [10, 10]}, index=dates)

    value_score = calculate_value_score(prices, book_value)

    # The first month has no previous month to lag from, so it is NaN by design.
    assert (value_score["A"].iloc[1:] > value_score["B"].iloc[1:]).all()


def test_calculate_value_score_uses_previous_month_price():
    """
    The value score dated month t must use P/B from the end of month t-1,
    because the weights dated t earn the return during month t. Here the
    price jumps from 100 to 400 at the end of month 2; the score dated
    month 2 must still reflect the month-1 price (P/B = 100 / 50 = 2),
    not the month-2 price the portfolio could not have known in advance.
    """
    dates = pd.date_range("2020-01-31", periods=3, freq="ME")
    prices = pd.DataFrame({"A": [100, 400, 400]}, index=dates)
    book_value = pd.DataFrame({"A": [50, 50, 50]}, index=dates)

    value_score = calculate_value_score(prices, book_value)

    assert pd.isna(value_score["A"].iloc[0])
    assert value_score["A"].iloc[1] == pytest.approx(-2.0)
    assert value_score["A"].iloc[2] == pytest.approx(-8.0)


def test_calculate_combined_score_nan_when_either_factor_missing():
    """
    A ticker with no book value coverage (like V in the real project)
    should end up NaN in the combined score, not silently treated as
    zero or dropped from one factor only -- otherwise build_portfolio()
    could select a stock based on momentum alone while believing it had
    a real combined signal.
    """
    dates = pd.date_range("2020-01-31", periods=2, freq="ME")
    momentum = pd.DataFrame({"A": [0.1, 0.1], "B": [0.2, 0.2]}, index=dates)
    value_score = pd.DataFrame({"A": [-2.0, -2.0]}, index=dates)  # B missing entirely

    combined = calculate_combined_score(momentum, value_score)

    assert combined["B"].isna().all()


def test_build_portfolio_selects_correct_top_n():
    """
    Given clear, distinct scores, build_portfolio(top_n=2) should select
    exactly the 2 highest-scoring tickers and weight them 1/2 each,
    leaving everyone else at 0.
    """
    dates = pd.date_range("2020-01-31", periods=1, freq="ME")
    scores = pd.DataFrame({"A": [0.05], "B": [0.20], "C": [0.10], "D": [-0.05]}, index=dates)

    weights = build_portfolio(scores, top_n=2)
    held = weights.loc[dates[0]]

    assert held["B"] == pytest.approx(0.5)
    assert held["C"] == pytest.approx(0.5)
    assert held["A"] == 0.0
    assert held["D"] == 0.0


def test_build_portfolio_skips_dates_with_insufficient_scores():
    """
    If fewer than top_n tickers have a valid (non-NaN) score on a given
    date, build_portfolio() should leave that date at all-zero weights
    rather than holding a smaller, non-equal-weighted portfolio silently.
    """
    dates = pd.date_range("2020-01-31", periods=1, freq="ME")
    scores = pd.DataFrame({"A": [0.05], "B": [None]}, index=dates)

    weights = build_portfolio(scores, top_n=2)

    assert (weights.loc[dates[0]] == 0.0).all()