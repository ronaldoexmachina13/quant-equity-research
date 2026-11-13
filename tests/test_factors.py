"""
Unit tests for the factor-construction logic in src/factors.py and
src/portfolio.py. These are pure functions of a price/book-value
DataFrame -- no database or network involved -- so we build small,
hand-checkable synthetic inputs rather than touching real market data.
"""
import pandas as pd
import pytest

from src.factors import (
    calculate_momentum, calculate_momentum_skip_month, calculate_value_score, calculate_combined_score,
)
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
    Look-ahead guard: the score dated t must not use the price at t itself.
    Changing only the final month's price should leave momentum[13]
    unchanged, since it is built from shift(1) and shift(12), not shift(0).
    This is not a reversal skip: the window ends at t-1 and no month inside
    it is dropped.
    """
    dates = pd.date_range("2020-01-31", periods=14, freq="ME")
    prices_a = pd.DataFrame({"A": [100 + 2 * i for i in range(14)]}, index=dates)
    prices_b = prices_a.copy()
    prices_b.loc[dates[13], "A"] = 9999  # blow up the most recent month only

    momentum_a = calculate_momentum(prices_a)
    momentum_b = calculate_momentum(prices_b)

    assert momentum_a["A"].iloc[13] == pytest.approx(momentum_b["A"].iloc[13], rel=1e-9)


def skip_month_prices() -> pd.DataFrame:
    """
    15 month-end prices, rows 0 to 14, with t = row 14. The rows that matter:
    t-14 = 70, t-13 = 80, t-12 = 125, t-2 = 100, t-1 = 200, t = 50. The other
    rows are distinct values that none of the checked windows use.
    """
    dates = pd.date_range("2020-01-31", periods=15, freq="ME")
    values = [70, 80, 125, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 200, 50]
    return pd.DataFrame({"A": values}, index=dates)


def test_calculate_momentum_skip_month_matches_formula_by_hand():
    """
    Row 14 must be price[t-2] / price[t-13] - 1 = 100 / 80 - 1 = +0.25.
    A wrong end point gives 200 / 80 - 1 = +1.5 (t-1) or 50 / 80 - 1 = -0.375 (t),
    and a wrong start point gives 100 / 125 - 1 = -0.2 (t-12).
    """
    momentum = calculate_momentum_skip_month(skip_month_prices())
    assert momentum["A"].iloc[14] == pytest.approx(100 / 80 - 1, rel=1e-12)


def test_calculate_momentum_skip_month_ignores_price_at_t():
    prices = skip_month_prices()
    changed = prices.copy()
    changed.iloc[14, 0] = 9999
    assert calculate_momentum_skip_month(changed)["A"].iloc[14] == pytest.approx(
        calculate_momentum_skip_month(prices)["A"].iloc[14], rel=1e-12)


def test_calculate_momentum_skip_month_ignores_price_at_t_minus_1():
    """This is the difference from the registered signal, which ends at t-1."""
    prices = skip_month_prices()
    changed = prices.copy()
    changed.iloc[13, 0] = 9999
    assert calculate_momentum_skip_month(changed)["A"].iloc[14] == pytest.approx(
        calculate_momentum_skip_month(prices)["A"].iloc[14], rel=1e-12)


def test_calculate_momentum_skip_month_uses_t_minus_2_and_t_minus_13():
    """Changing t-2 or t-13 moves row 14. Changing t-14 does not."""
    prices = skip_month_prices()
    base = calculate_momentum_skip_month(prices)["A"].iloc[14]
    for row, should_change in [(12, True), (1, True), (0, False)]:
        changed = prices.copy()
        changed.iloc[row, 0] = 9999
        value = calculate_momentum_skip_month(changed)["A"].iloc[14]
        assert (value != pytest.approx(base, rel=1e-12)) is should_change, f"row {row}"


def test_calculate_momentum_skip_month_needs_13_months_of_history():
    momentum = calculate_momentum_skip_month(skip_month_prices())["A"]
    assert momentum.iloc[:13].isna().all()
    assert momentum.iloc[13:].notna().all()


def test_calculate_momentum_skip_month_is_registered_signal_one_month_later():
    """With no gaps in the prices, the 12-1 row dated t is the registered row dated t-1."""
    prices = skip_month_prices()
    pd.testing.assert_frame_equal(calculate_momentum_skip_month(prices), calculate_momentum(prices).shift(1))


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