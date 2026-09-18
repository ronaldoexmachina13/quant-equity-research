"""
Unit tests for src/risk.py.

These functions are pure math -- given the same returns series, they
always produce the same answer -- so we can check them against numbers
worked out by hand, with no database or network involved.
"""
import pandas as pd
import pytest

from src.risk import annualized_return, annualized_volatility, max_drawdown, sharpe_ratio, bootstrap_sharpe_diff


def test_annualized_return_constant_monthly_return():
    """
    12 months of a flat 1% monthly return should compound to
    (1.01)^12 - 1 ≈ 12.68% annualized -- a textbook compounding check,
    independent of the function's own implementation.
    """
    returns = pd.Series([0.01] * 12)
    expected = 1.01 ** 12 - 1
    assert annualized_return(returns) == pytest.approx(expected, rel=1e-6)


def test_annualized_return_zero_return_is_zero():
    """12 months of exactly 0% return should annualize to 0%, not NaN or an error."""
    returns = pd.Series([0.0] * 12)
    assert annualized_return(returns) == pytest.approx(0.0, abs=1e-9)


def test_annualized_volatility_scales_with_sqrt_12():
    """
    annualized_volatility should equal monthly std * sqrt(12) -- this
    tests the actual annualization convention the function claims to use,
    not just "does it run."
    """
    returns = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02, -0.03,
                          0.01, 0.00, 0.02, -0.01, 0.01, -0.02])
    expected = returns.std() * (12 ** 0.5)
    assert annualized_volatility(returns) == pytest.approx(expected, rel=1e-9)


def test_sharpe_ratio_higher_return_gives_higher_sharpe():
    """
    Holding volatility roughly comparable, a strategy with a clearly
    higher return should score a higher Sharpe ratio than one with a
    lower return -- a basic sanity/ordering check rather than an exact
    number, since Sharpe depends on annualized_return and
    annualized_volatility, which are tested separately above.
    """
    high_return = pd.Series([0.02, 0.01, 0.03, 0.015, 0.025, 0.02,
                              0.01, 0.02, 0.015, 0.03, 0.01, 0.02])
    low_return = pd.Series([0.005, -0.005, 0.01, 0.0, 0.005, 0.01,
                             -0.01, 0.005, 0.0, 0.01, -0.005, 0.005])
    assert sharpe_ratio(high_return) > sharpe_ratio(low_return)


def test_max_drawdown_known_case():
    """
    A cumulative value that goes 100 -> 120 -> 90 -> 110 has a peak-to-
    trough decline of exactly (90 - 120) / 120 = -25%, worked out by
    hand, then expressed as monthly returns for the function to consume.
    """
    returns = pd.Series([0.20, (90 / 120) - 1, (110 / 90) - 1])
    assert max_drawdown(returns) == pytest.approx(-0.25, rel=1e-6)


def test_max_drawdown_always_non_positive():
    """
    Max drawdown should never be reported as a positive number, even for
    a strategy that only ever went up -- it should be exactly 0 in that
    case, not a negative-of-a-negative sign error.
    """
    always_up = pd.Series([0.01, 0.02, 0.01, 0.03, 0.01])
    assert max_drawdown(always_up) <= 0
    assert max_drawdown(always_up) == pytest.approx(0.0, abs=1e-9)


def test_bootstrap_sharpe_diff_detects_real_advantage():
    """
    A strategy with a large, consistent advantage over a benchmark
    should produce a confidence interval that excludes zero -- the
    bootstrap should correctly detect a real difference when one exists.
    """
    rng = pd.Series([0.01, 0.02, -0.01, 0.03, 0.01, 0.02, 0.00, 0.02, 0.01, 0.03,
                      0.02, 0.01, 0.03, 0.02, 0.01, 0.02, 0.03, 0.01, 0.02, 0.03,
                      0.02, 0.01, 0.03, 0.02, 0.01, 0.02, 0.03, 0.02, 0.01, 0.03,
                      0.02, 0.01, 0.02, 0.03, 0.02, 0.01, 0.03, 0.02, 0.01, 0.02,
                      0.03, 0.02, 0.01, 0.03, 0.02, 0.01, 0.02, 0.03])
    benchmark = pd.Series([0.001, -0.001] * (len(rng) // 2))
    result = bootstrap_sharpe_diff(rng, benchmark, n_sims=2000, seed=1)
    assert result["significant"] is True
    assert result["lower"] > 0


def test_bootstrap_sharpe_diff_no_false_positive_on_identical_series():
    """
    Comparing a return series against an exact copy of itself must never
    show a significant difference -- there is, by construction, no
    difference to detect.
    """
    returns = pd.Series([0.01, -0.02, 0.03, 0.00, 0.02, -0.01, 0.01, 0.02,
                          -0.03, 0.01, 0.02, 0.00] * 4)
    result = bootstrap_sharpe_diff(returns, returns.copy(), n_sims=1000, seed=2)
    assert result["significant"] is False
    assert result["point_diff"] == 0