"""
Unit tests for the turnover and transaction cost logic in
src/backtest.py. These are pure functions of a weights DataFrame, so
we build small, hand-checkable synthetic portfolios rather than
touching real market data.
"""
import pandas as pd
import pytest

from src.backtest import calculate_turnover, apply_transaction_costs
from src.backtest import calculate_monthly_returns, run_backtest, equal_weight_targets, calculate_turnover_with_drift, find_break_even_cost


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


# --- Cost sensitivity (LIMITATIONS_PLAN.md, Phase 1B and Amendment 2) ---

def test_equal_weight_targets_skips_missing_tickers():
    """
    Three tickers with returns gives 1/3 each; a month where one ticker
    has no return gives 1/2 to the other two and 0 to the missing one.
    """
    dates = pd.date_range("2021-01-31", periods=2, freq="ME")
    returns = pd.DataFrame({"A": [0.01, 0.02], "B": [0.03, None], "C": [-0.01, 0.0]}, index=dates)
    targets = equal_weight_targets(returns)
    assert list(targets.iloc[0]) == pytest.approx([1 / 3, 1 / 3, 1 / 3])
    assert list(targets.iloc[1]) == pytest.approx([0.5, 0.0, 0.5])


def test_drift_turnover_two_assets_hand_worked():
    """
    50/50 in month 1; during month 1, A gains 10% and B loses 10%, so the
    book enters month 2 at 0.55/0.45. Back to 50/50 means selling 5% of
    A and buying 5% of B: turnover 0.05. Month 1 is a purchase from cash.
    """
    dates = pd.date_range("2021-01-31", periods=2, freq="ME")
    weights = pd.DataFrame({"A": [0.5, 0.5], "B": [0.5, 0.5]}, index=dates)
    returns = pd.DataFrame({"A": [0.10, 0.0], "B": [-0.10, 0.0]}, index=dates)
    turnover = calculate_turnover_with_drift(weights, returns)
    assert turnover.iloc[0] == pytest.approx(1.0)
    assert turnover.iloc[1] == pytest.approx(0.05)


def test_drift_turnover_follows_run_backtest_alignment():
    """
    Uses the real date alignment: returns come from calculate_monthly_returns()
    on hand-made prices, and the expected pre-trade weights are built from
    run_backtest()'s own output. run_backtest() applies weights dated t to the
    return dated t, so the book entering month t is the month t-1 holdings
    grown by the month t-1 returns, divided by (1 + portfolio return in t-1).

    Prices: A +10% in Jan, -10% in Feb, +10% in Mar; B flat, +10%, flat;
    C +5%, flat, about +4.8%. Targets: A/B 50/50 in Jan and Feb, B/C 50/50
    in Mar.
    """
    price_dates = pd.to_datetime(["2023-12-15", "2023-12-29", "2024-01-16", "2024-01-31",
                                  "2024-02-14", "2024-02-29", "2024-03-15", "2024-03-28"])
    prices = pd.DataFrame({
        "A": [101.0, 100.0, 104.0, 110.0, 105.0, 99.0, 103.0, 108.9],
        "B": [49.0, 50.0, 51.0, 50.0, 52.0, 55.0, 54.0, 55.0],
        "C": [19.5, 20.0, 20.5, 21.0, 21.2, 21.0, 21.5, 22.0],
    }, index=price_dates)
    returns = calculate_monthly_returns(prices).dropna()
    weights = pd.DataFrame({"A": [0.5, 0.5, 0.0], "B": [0.5, 0.5, 0.5], "C": [0.0, 0.0, 0.5]},
                           index=returns.index)

    portfolio = run_backtest(weights, returns)
    turnover = calculate_turnover_with_drift(weights, returns)

    for t in range(1, len(weights)):
        prev = weights.index[t - 1]
        pre_trade = weights.loc[prev] * (1 + returns.loc[prev]) / (1 + portfolio.loc[prev])
        expected = 0.5 * (weights.iloc[t] - pre_trade).abs().sum()
        assert turnover.iloc[t] == pytest.approx(expected, rel=1e-12)

    # February by hand: A grew 10% and B was flat in January, so the book
    # entered February at 0.55/1.05 and 0.50/1.05; back to 50/50 is 1/42.
    assert turnover.iloc[1] == pytest.approx(1 / 42, rel=1e-12)

    # An off-by-one (drifting by February's own returns, -10% / +10%)
    # would give 0.05 instead, so the test would catch it.
    wrong_pre = weights.iloc[0] * (1 + returns.iloc[1]) / (1 + (weights.iloc[0] * returns.iloc[1]).sum())
    wrong = 0.5 * (weights.iloc[1] - wrong_pre).abs().sum()
    assert wrong == pytest.approx(0.05, rel=1e-12)
    assert turnover.iloc[1] != pytest.approx(wrong)


def test_drift_turnover_equals_existing_turnover_when_prices_do_not_move():
    """With zero returns there is no drift, so both turnover measures agree."""
    dates = pd.date_range("2021-01-31", periods=3, freq="ME")
    weights = pd.DataFrame({
        "A": [0.2, 0.2, 0.0], "B": [0.2, 0.2, 0.2], "C": [0.2, 0.0, 0.2],
        "D": [0.2, 0.2, 0.2], "E": [0.2, 0.2, 0.2], "F": [0.0, 0.2, 0.2],
    }, index=dates)
    returns = pd.DataFrame(0.0, index=dates, columns=weights.columns)
    drift = calculate_turnover_with_drift(weights, returns)
    existing = calculate_turnover(weights)
    assert list(drift) == pytest.approx(list(existing))


BENCH_GROSS = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02, -0.03,
                         0.01, 0.00, 0.02, -0.01, 0.01, -0.02])
TURNOVER_STRAT = pd.Series([0.25] * 12)
TURNOVER_BENCH = pd.Series([0.05] * 12)


def test_break_even_cost_known_answer():
    """
    Strategy = benchmark + 0.1% a month, so both have the same volatility,
    and their Sharpes are equal when the net monthly series are equal:
    0.001 = 2c(0.25 - 0.05), so c = 0.0025 = 25 bps.
    """
    result = find_break_even_cost(BENCH_GROSS + 0.001, TURNOVER_STRAT, BENCH_GROSS, TURNOVER_BENCH)
    assert len(result["crossings_bps"]) == 1
    assert result["crossings_bps"][0] == pytest.approx(25.0, abs=1e-6)
    assert "falls to" in result["note"]


def test_break_even_cost_below_benchmark_at_zero():
    """Lower return and more trading: the strategy never reaches the benchmark."""
    result = find_break_even_cost(BENCH_GROSS - 0.001, TURNOVER_STRAT, BENCH_GROSS, TURNOVER_BENCH)
    assert result["crossings_bps"] == []
    assert result["note"] == "below benchmark at 0 bps"


def test_break_even_cost_above_benchmark_at_50():
    """
    A 1% monthly edge would only be used up at 0.01 / 0.4 = 250 bps, so
    within 0 to 50 bps the strategy stays ahead.
    """
    result = find_break_even_cost(BENCH_GROSS + 0.01, TURNOVER_STRAT, BENCH_GROSS, TURNOVER_BENCH)
    assert result["crossings_bps"] == []
    assert result["note"] == "above benchmark at 50 bps"