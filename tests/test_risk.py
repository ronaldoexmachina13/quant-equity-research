"""
Unit tests for src/risk.py.

These functions are pure math -- given the same returns series, they
always produce the same answer -- so we can check them against numbers
worked out by hand, with no database or network involved.
"""
import numpy as np
import pandas as pd
import pytest

from src.risk import annualized_return, annualized_volatility, max_drawdown, sharpe_ratio, bootstrap_sharpe_diff, downside_deviation, sortino_ratio, beta, alpha, alpha_regression
from src.risk import tbill_yield_to_monthly, align_risk_free, annualized_risk_free, sharpe_ratio_tbill, downside_deviation_tbill, sortino_ratio_tbill, alpha_regression_tbill
from src.risk import power_z_values, minimum_detectable_effect, months_needed_to_detect


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


def test_downside_deviation_known_case():
    """
    With a 0% target, shortfalls are 0, -0.02, 0, -0.04. Squares sum to
    0.002; averaged over all 4 months (not just the 2 losing ones) gives
    0.0005; sqrt = 0.022361; annualized * sqrt(12) = 0.077460.
    """
    returns = pd.Series([0.03, -0.02, 0.01, -0.04])
    assert downside_deviation(returns, target_annual=0.0) == pytest.approx(0.077460, rel=1e-4)


def test_sortino_undefined_when_no_downside():
    """
    If every month beats the target there is no downside deviation, so
    the ratio is undefined and should return NaN rather than divide by zero.
    """
    returns = pd.Series([0.02] * 12)
    assert pd.isna(sortino_ratio(returns))


def test_sortino_ignores_upside_volatility():
    """
    Two series with identical losing months, but one has much larger
    winning months. Sharpe penalizes the bigger upside swings; Sortino
    should not, so the more volatile-upside series scores higher on Sortino.
    """
    steady = pd.Series([0.01, -0.02, 0.01, -0.02, 0.01, 0.01] * 2)
    big_upside = pd.Series([0.05, -0.02, 0.05, -0.02, 0.05, 0.05] * 2)
    assert downside_deviation(steady) == pytest.approx(downside_deviation(big_upside), rel=1e-9)
    assert sortino_ratio(big_upside) > sortino_ratio(steady)


def test_beta_and_alpha_exact_multiple_of_benchmark():
    """
    A strategy that is exactly 2x the benchmark every month must have
    beta = 2. With a 0% risk-free rate, beta explains all of its return,
    so alpha must be 0.
    """
    bench = pd.Series([0.01, -0.005, 0.015, 0.0, 0.02, -0.01])
    strat = 2 * bench
    assert beta(strat, bench) == pytest.approx(2.0, rel=1e-9)
    assert alpha(strat, bench, risk_free_rate=0.0) == pytest.approx(0.0, abs=1e-12)


def test_alpha_captures_constant_outperformance():
    """
    A strategy that moves one-for-one with the benchmark (beta = 1) but
    earns an extra 0.5% every month should show alpha of 0.5% x 12 = 6%
    a year. With beta = 1 the risk-free rate cancels out, so the answer
    holds at the default 2% rate as well.
    """
    bench = pd.Series([0.01, -0.005, 0.015, 0.0, 0.02, -0.01])
    strat = bench + 0.005
    assert beta(strat, bench) == pytest.approx(1.0, rel=1e-9)
    assert alpha(strat, bench) == pytest.approx(0.06, rel=1e-9)


def test_alpha_regression_matches_alpha_and_detects_real_outperformance():
    """
    The regression intercept must equal Jensen's alpha from alpha(), since
    both are the same OLS estimate. And a strategy that beats a beta-1.1
    version of the benchmark by 0.5% every month, with only small noise,
    should show a large, clearly significant alpha t-statistic.
    """
    bench = pd.Series([0.01, -0.005, 0.015, 0.0, 0.02, -0.01, 0.012, -0.004, 0.008, 0.003, -0.012, 0.018])
    noise = pd.Series([0.001, -0.001, 0.0005, -0.0005, 0.0, 0.0008, -0.0008, 0.0003, -0.0003, 0.0006, -0.0006, 0.0])
    strat = 1.1 * bench + 0.005 + noise
    result = alpha_regression(strat, bench)
    assert result["alpha"] == pytest.approx(alpha(strat, bench), rel=1e-9)
    assert result["beta"] == pytest.approx(beta(strat, bench), rel=1e-9)
    assert result["alpha_tstat"] > 3
    assert result["alpha_pvalue"] < 0.01


# --- Time-varying risk-free rate (LIMITATIONS_PLAN.md, Phase 1A) ---

# Same expression the flat-rate functions use internally for 2% a year,
# so the equivalence test below compares like with like.
FLAT_2PCT_MONTHLY = (1 + 0.02) ** (1 / 12) - 1

RETURNS_12M = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02, -0.03,
                         0.01, 0.00, 0.02, -0.01, 0.01, -0.02])
BENCH_12M = pd.Series([0.01, -0.005, 0.015, 0.0, 0.02, -0.01,
                       0.012, -0.004, 0.008, 0.003, -0.012, 0.018])


def test_tbill_yield_to_monthly_converts_5_percent():
    """
    A 5% annual yield is (1.05)^(1/12) - 1 a month, and twelve such
    months must compound back to exactly 5%.
    """
    monthly = tbill_yield_to_monthly(pd.Series([5.0]))
    assert monthly.iloc[0] == pytest.approx(1.05 ** (1 / 12) - 1, rel=1e-12)
    assert (1 + monthly.iloc[0]) ** 12 - 1 == pytest.approx(0.05, rel=1e-12)


def test_annualized_risk_free_of_constant_rate():
    """Twelve months at a constant 3%-a-year monthly rate annualize to 3%."""
    rf = pd.Series([1.03 ** (1 / 12) - 1] * 12)
    assert annualized_risk_free(rf) == pytest.approx(0.03, rel=1e-12)


def test_tbill_functions_match_flat_functions_at_constant_2pct():
    """
    With a constant series equal to the flat 2% monthly rate, every
    T-bill function must give the same answer as its flat-rate
    counterpart. This is the reproduction check of Amendment 1, item 3.
    """
    rf = pd.Series([FLAT_2PCT_MONTHLY] * 12)
    assert sharpe_ratio_tbill(RETURNS_12M, rf) == pytest.approx(sharpe_ratio(RETURNS_12M), rel=1e-12)
    assert downside_deviation_tbill(RETURNS_12M, rf) == pytest.approx(downside_deviation(RETURNS_12M), rel=1e-12)
    assert sortino_ratio_tbill(RETURNS_12M, rf) == pytest.approx(sortino_ratio(RETURNS_12M), rel=1e-12)
    flat = alpha_regression(RETURNS_12M, BENCH_12M)
    tbill = alpha_regression_tbill(RETURNS_12M, BENCH_12M, rf)
    for key in ["alpha", "alpha_tstat", "alpha_pvalue", "beta", "r_squared"]:
        assert tbill[key] == pytest.approx(flat[key], rel=1e-12)


def test_sharpe_ratio_tbill_with_varying_rate():
    """
    Six months at 0.1% and six at 0.3%: over 12 months the risk-free leg
    compounds to 1.001^6 x 1.003^6 - 1, which is subtracted from the
    strategy's 12-month return; volatility is the strategy's own.
    """
    rf = pd.Series([0.001] * 6 + [0.003] * 6)
    rf_annual = 1.001 ** 6 * 1.003 ** 6 - 1
    expected = ((1 + RETURNS_12M).prod() - 1 - rf_annual) / (RETURNS_12M.std() * 12 ** 0.5)
    assert sharpe_ratio_tbill(RETURNS_12M, rf) == pytest.approx(expected, rel=1e-12)


def test_downside_deviation_tbill_uses_each_months_rate():
    """
    Returns of 1% and 0% against targets of 0.5% and 0.2%: only the
    second month falls short, by 0.2%, so the downside deviation is
    sqrt((0 + 0.002^2) / 2) x sqrt(12).
    """
    returns = pd.Series([0.01, 0.0])
    rf = pd.Series([0.005, 0.002])
    expected = (0.002 ** 2 / 2) ** 0.5 * 12 ** 0.5
    assert downside_deviation_tbill(returns, rf) == pytest.approx(expected, rel=1e-12)


def test_alpha_regression_tbill_deducts_each_months_rate():
    """
    A strategy built so that its excess return is exactly 2x the
    benchmark's excess return in every month, (r - rf) = 2 (b - rf), must
    show beta = 2 and alpha = 0 when rf varies month to month. This only
    holds if the rate is deducted month by month, not as an average.
    """
    rf = pd.Series([0.000, 0.001, 0.002, 0.003, 0.004, 0.005,
                    0.004, 0.003, 0.002, 0.001, 0.000, 0.002])
    strat = 2 * BENCH_12M - rf
    result = alpha_regression_tbill(strat, BENCH_12M, rf)
    assert result["beta"] == pytest.approx(2.0, rel=1e-9)
    assert result["alpha"] == pytest.approx(0.0, abs=1e-12)


def test_alpha_regression_tbill_constant_outperformance():
    """
    Beta-1 strategy earning 0.5% a month above the benchmark: the rate
    cancels out, so alpha is 6% a year whatever the risk-free path.
    """
    rf = pd.Series([0.000, 0.001, 0.002, 0.003, 0.004, 0.005,
                    0.004, 0.003, 0.002, 0.001, 0.000, 0.002])
    result = alpha_regression_tbill(BENCH_12M + 0.005, BENCH_12M, rf)
    assert result["beta"] == pytest.approx(1.0, rel=1e-9)
    assert result["alpha"] == pytest.approx(0.06, rel=1e-9)


def test_align_risk_free_raises_on_missing_month():
    """A return date with no risk-free rate must raise, not be dropped or filled."""
    dates = pd.to_datetime(["2025-01-31", "2025-02-28", "2025-03-31"])
    returns = pd.Series([0.01, 0.02, 0.03], index=dates)
    rf = pd.Series([0.003, 0.003], index=dates[:2])
    with pytest.raises(ValueError):
        align_risk_free(returns, rf)


# --- Statistical power (LIMITATIONS_PLAN.md, Phase 1C) ---

def test_power_z_values_match_standard_tables():
    """10% two-sided -> 1.6449, 5% two-sided -> 1.9600, 80% power -> 0.8416."""
    z_alpha, z_power = power_z_values(0.10, 0.80)
    assert z_alpha == pytest.approx(1.6449, abs=1e-4)
    assert z_power == pytest.approx(0.8416, abs=1e-4)
    assert power_z_values(0.05, 0.80)[0] == pytest.approx(1.9600, abs=1e-4)


def test_minimum_detectable_effect_hand_worked():
    """
    sd 2% a month, 100 months, z_alpha + z_power = 2.5:
    2.5 x 0.02 / sqrt(100) = 0.005 a month, or 12 x 0.005 = 6% a year.
    """
    mde = minimum_detectable_effect(0.02, 100, 2.0, 0.5)
    assert mde == pytest.approx(0.005, rel=1e-12)
    assert 12 * mde == pytest.approx(0.06, rel=1e-12)


def test_minimum_detectable_effect_rejects_bad_inputs():
    with pytest.raises(ValueError):
        minimum_detectable_effect(0.02, 1, 2.0, 0.5)
    with pytest.raises(ValueError):
        minimum_detectable_effect(-0.02, 100, 2.0, 0.5)


def test_months_needed_exact_answer_is_not_pushed_up_by_rounding():
    """(2.5 x 0.02 / 0.005)^2 = 100 exactly, so the answer is 100, not 101."""
    result = months_needed_to_detect(0.005, 0.02, 2.0, 0.5)
    assert result["months"] == 100
    assert result["direction"] == "outperformance"


def test_months_needed_rounds_up_non_integer_answer():
    """(2.5 x 0.02 / 0.004)^2 = 156.25, which needs 157 whole months."""
    assert months_needed_to_detect(0.004, 0.02, 2.0, 0.5)["months"] == 157


def test_months_needed_negative_mean_is_underperformance():
    """A two-sided test detects a -0.5% mean as easily as +0.5%: 100 months."""
    result = months_needed_to_detect(-0.005, 0.02, 2.0, 0.5)
    assert result["months"] == 100
    assert result["direction"] == "underperformance"
    assert "underperformance" in result["note"]


def test_months_needed_zero_mean_is_reported_not_raised():
    result = months_needed_to_detect(0.0, 0.02, 2.0, 0.5)
    assert np.isnan(result["months"])
    assert result["direction"] == "none"
    assert "not detectable" in result["note"]


def test_months_needed_round_trip_with_minimum_detectable_effect():
    """
    At the months needed, the minimum detectable effect is at or below the
    mean; one month fewer, it is still above it.
    """
    mean, sd, z_alpha, z_power = 0.003, 0.025, 1.6449, 0.8416
    n = months_needed_to_detect(mean, sd, z_alpha, z_power)["months"]
    assert minimum_detectable_effect(sd, n, z_alpha, z_power) <= mean
    assert minimum_detectable_effect(sd, n - 1, z_alpha, z_power) > mean