"""
Unit tests for the turnover and transaction cost logic in
src/backtest.py. These are pure functions of a weights DataFrame, so
we build small, hand-checkable synthetic portfolios rather than
touching real market data.
"""
import pandas as pd
import pytest

from src.backtest import calculate_turnover, apply_transaction_costs


def test_turnover_first_month_is_full_weight_not_half():
    """
    The first month has no prior portfolio to compare against -- the
    strategy starts from cash, so the whole position is pure buying,
    not a buy-and-sell rebalance. Turnover should be the FULL invested
    weight (1.0 for a fully-invested portfolio), not half of it.
    """
    dates = pd.date_range("2021-01-31", periods=1, freq="ME")
    weights = pd.DataFrame({"A": [0.2], "B": [0.2], "C": [0.2], "D": [0.2], "E": [0.2]}, index=dates)
    turnover = calculate_turnover(weights)
    assert turnover.iloc[0] == pytest.approx(1.0)


def test_turnover_unchanged_portfolio_is_zero_after_first_month():
    """
    A portfolio that holds the exact same weights month over month
    should show zero turnover after the initial purchase -- nothing
    is being bought or sold in a month where nothing changes.
    """
    dates = pd.date_range("2021-01-31", periods=3, freq="ME")
    weights = pd.DataFrame({"A": [0.2] * 3, "B": [0.2] * 3, "C": [0.2] * 3,
                             "D": [0.2] * 3, "E": [0.2] * 3}, index=dates)
    turnover = calculate_turnover(weights)
    assert turnover.iloc[1] == pytest.approx(0.0)
    assert turnover.iloc[2] == pytest.approx(0.0)


def test_turnover_partial_replacement():
    """
    Replacing 1 of 5 equally-weighted holdings (20% of the book) with a
    new one should show turnover of exactly 0.2, not 0.4 -- selling one
    20% position and buying a different 20% position is one
    re-positioning of a fifth of the portfolio, not two separate moves.
    """
    dates = pd.date_range("2021-01-31", periods=2, freq="ME")
    weights = pd.DataFrame({
        "A": [0.2, 0.2], "B": [0.2, 0.2], "C": [0.2, 0.2],
        "D": [0.2, 0.2], "E": [0.2, 0.0], "F": [0.0, 0.2],
    }, index=dates)
    turnover = calculate_turnover(weights)
    assert turnover.iloc[1] == pytest.approx(0.2)


def test_apply_transaction_costs_known_case():
    """
    A 0.2 turnover month with a 10bps one-way cost should cost exactly
    2 * 0.2 * 0.001 = 0.0004 (4bps) of return -- 10bps to sell the
    departing position, 10bps to buy the new one, each applied to the
    20% of the portfolio that actually changed hands.
    """
    returns = pd.Series([0.02])
    turnover = pd.Series([0.2])
    net = apply_transaction_costs(returns, turnover, cost_bps=10)
    assert net.iloc[0] == pytest.approx(0.02 - 0.0004)


def test_apply_transaction_costs_zero_turnover_no_cost():
    """A month with zero turnover should have its return completely untouched."""
    returns = pd.Series([0.05])
    turnover = pd.Series([0.0])
    net = apply_transaction_costs(returns, turnover, cost_bps=10)
    assert net.iloc[0] == pytest.approx(0.05)