import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import norm

TRADING_PERIODS_PER_YEAR = 12  # we're working in monthly returns


def total_return(returns: pd.Series) -> float:
    """
    Compound return over the whole period, uncompounded to a yearly rate.
    E.g. 0.477 means the strategy grew by 47.7% from start to end of the
    period, regardless of how many months that took.
    """
    return (1 + returns).prod() - 1


def annualized_return(returns: pd.Series) -> float:
    """Compound monthly returns into an annualized rate."""
    compounded = (1 + returns).prod()
    n_years = len(returns) / TRADING_PERIODS_PER_YEAR
    return compounded ** (1 / n_years) - 1


def annualized_volatility(returns: pd.Series) -> float:
    """Annualize monthly return volatility."""
    return returns.std() * np.sqrt(TRADING_PERIODS_PER_YEAR)


def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.02) -> float:
    """
    Sharpe ratio using a simple constant annual risk-free rate assumption.
    """
    ann_return = annualized_return(returns)
    ann_vol = annualized_volatility(returns)
    return (ann_return - risk_free_rate) / ann_vol


def max_drawdown(returns: pd.Series) -> float:
    """
    Largest peak-to-trough decline in cumulative value.
    Returns a negative number (e.g. -0.25 = a 25% drawdown).
    """
    cumulative = (1 + returns).cumprod()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    return drawdown.min()


def rolling_volatility(returns: pd.Series, window: int = 12) -> pd.Series:
    """
    Trailing N-month annualized volatility, recomputed at every point.
    The first (window - 1) entries are NaN -- there isn't enough history
    yet to compute a trailing window there.
    """
    return returns.rolling(window).std() * np.sqrt(TRADING_PERIODS_PER_YEAR)


def rolling_sharpe(returns: pd.Series, window: int = 12, risk_free_rate: float = 0.02) -> pd.Series:
    """
    Trailing N-month Sharpe ratio, recomputed at every point. When the
    window is exactly 12 months, the "annualized return" for that window
    is simply the window's own compounded return (12 months = 1 year,
    so no further annualization is needed) -- this only generalizes
    correctly for window=12; a different window size would need a
    different exponent.
    """
    rolling_compounded = returns.rolling(window).apply(lambda r: (1 + r).prod() - 1, raw=True)
    vol = rolling_volatility(returns, window)
    return (rolling_compounded - risk_free_rate) / vol


def bootstrap_sharpe_ci(returns: pd.Series, risk_free_rate: float = 0.02, n_sims: int = 5000, ci: float = 0.90, seed: int | None = None) -> dict:
    """
    Bootstrap confidence interval around a single strategy's own Sharpe
    ratio. Resamples the return series with replacement n_sims times and
    recomputes Sharpe each time, giving a distribution of plausible
    Sharpe values instead of trusting one single point estimate.
    """
    rng = np.random.default_rng(seed)
    n = len(returns)
    vals = returns.values
    sharpes = np.empty(n_sims)
    for i in range(n_sims):
        idx = rng.integers(0, n, size=n)
        sharpes[i] = sharpe_ratio(pd.Series(vals[idx]), risk_free_rate)
    lower = float(np.percentile(sharpes, (1 - ci) / 2 * 100))
    upper = float(np.percentile(sharpes, (1 + ci) / 2 * 100))
    return {
        "point": sharpe_ratio(returns, risk_free_rate),
        "lower": lower,
        "upper": upper,
        "ci": ci,
        "n_sims": n_sims,
    }


def bootstrap_sharpe_diff(returns_a: pd.Series, returns_b: pd.Series, risk_free_rate: float = 0.02, n_sims: int = 5000, ci: float = 0.90, seed: int | None = None) -> dict:
    """
    Paired bootstrap confidence interval on the DIFFERENCE in Sharpe
    ratio between two return series measured over the same dates.

    Resamples the same set of month positions for BOTH series in each
    simulation (not independently), which preserves the real
    correlation between them. Strategies built from an overlapping
    universe in the same months are not independent, so resampling
    them separately would overstate how uncertain the difference
    between them really is -- comparing two independently-computed
    confidence intervals by eye is a known statistical trap for
    exactly this reason.

    Returns a dict including "significant": True if the confidence
    interval for (Sharpe_a - Sharpe_b) excludes zero.
    """
    if len(returns_a) != len(returns_b):
        raise ValueError("returns_a and returns_b must be the same length (same dates).")
    rng = np.random.default_rng(seed)
    n = len(returns_a)
    a_vals = returns_a.values
    b_vals = returns_b.values
    diffs = np.empty(n_sims)
    for i in range(n_sims):
        idx = rng.integers(0, n, size=n)
        diffs[i] = sharpe_ratio(pd.Series(a_vals[idx]), risk_free_rate) - sharpe_ratio(pd.Series(b_vals[idx]), risk_free_rate)
    lower = float(np.percentile(diffs, (1 - ci) / 2 * 100))
    upper = float(np.percentile(diffs, (1 + ci) / 2 * 100))
    point = sharpe_ratio(returns_a, risk_free_rate) - sharpe_ratio(returns_b, risk_free_rate)
    return {
        "point_diff": point,
        "lower": lower,
        "upper": upper,
        "ci": ci,
        "n_sims": n_sims,
        "significant": not (lower <= 0 <= upper),
    }


def summarize_risk(returns: pd.Series, label: str, benchmark_returns: pd.Series = None) -> dict:
    """
    Standard risk summary for one return series. Beta and alpha need a
    benchmark to compare against, so they are only calculated when
    benchmark_returns is passed in; otherwise they are NaN. Existing
    callers that pass only (returns, label) are unaffected.
    """
    has_benchmark = benchmark_returns is not None
    return {
        "label": label,
        "total_return": total_return(returns),
        "annualized_return": annualized_return(returns),
        "annualized_volatility": annualized_volatility(returns),
        "sharpe_ratio": sharpe_ratio(returns),
        "sortino_ratio": sortino_ratio(returns),
        "max_drawdown": max_drawdown(returns),
        "beta": beta(returns, benchmark_returns) if has_benchmark else np.nan,
        "alpha": alpha(returns, benchmark_returns) if has_benchmark else np.nan,
    }

def downside_deviation(returns: pd.Series, target_annual: float = 0.02) -> float:
    """
    Annualized downside deviation: the volatility of returns *below* a
    target, ignoring returns above it. Months above the target count as
    zero shortfall but still count in the average (the standard
    Sortino-Price definition); averaging only over losing months would
    overstate downside risk.
    """
    target_monthly = (1 + target_annual) ** (1 / TRADING_PERIODS_PER_YEAR) - 1
    shortfall = np.minimum(returns - target_monthly, 0)
    return np.sqrt((shortfall ** 2).mean()) * np.sqrt(TRADING_PERIODS_PER_YEAR)


def sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.02) -> float:
    """
    Like Sharpe, but divides excess return by downside deviation instead
    of total volatility, so upside swings are not penalized. Returns NaN
    if the series never falls below the target (ratio undefined).
    """
    downside = downside_deviation(returns, target_annual=risk_free_rate)
    if downside == 0:
        return np.nan
    return (annualized_return(returns) - risk_free_rate) / downside

def beta(returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """
    Sensitivity of a strategy to its benchmark: covariance of the two
    monthly return series divided by the benchmark's variance (the slope
    of a regression of strategy returns on benchmark returns). Series are
    aligned on date first, so only months present in both are used.
    """
    aligned = pd.concat([returns, benchmark_returns], axis=1).dropna()
    r, b = aligned.iloc[:, 0], aligned.iloc[:, 1]
    return r.cov(b) / b.var()


def alpha(returns: pd.Series, benchmark_returns: pd.Series, risk_free_rate: float = 0.02) -> float:
    """
    Annualized Jensen's alpha: the average monthly excess return not
    explained by beta times the benchmark's excess return, multiplied by
    12. Uses arithmetic monthly means, the standard convention for a
    regression intercept, so it is not directly comparable to the
    compounded annualized returns elsewhere in this module.
    """
    aligned = pd.concat([returns, benchmark_returns], axis=1).dropna()
    r, b = aligned.iloc[:, 0], aligned.iloc[:, 1]
    rf_monthly = (1 + risk_free_rate) ** (1 / TRADING_PERIODS_PER_YEAR) - 1
    monthly_alpha = (r - rf_monthly).mean() - beta(r, b) * (b - rf_monthly).mean()
    return monthly_alpha * TRADING_PERIODS_PER_YEAR


def alpha_regression(returns: pd.Series, benchmark_returns: pd.Series, risk_free_rate: float = 0.02) -> dict:
    """
    Estimate alpha and beta by OLS regression of the strategy's monthly
    excess return on the benchmark's monthly excess return:

        (r - rf) = alpha + beta * (b - rf) + error

    Returns the annualized alpha (monthly intercept x 12), its t-statistic
    and p-value, beta and R-squared. The alpha matches alpha() above; what
    the regression adds is a standard error, so we can ask whether alpha
    is distinguishable from zero on this sample size.
    """
    aligned = pd.concat([returns, benchmark_returns], axis=1).dropna()
    rf_monthly = (1 + risk_free_rate) ** (1 / TRADING_PERIODS_PER_YEAR) - 1
    y = aligned.iloc[:, 0] - rf_monthly
    x = sm.add_constant(aligned.iloc[:, 1] - rf_monthly)
    model = sm.OLS(y, x).fit()
    return {
        "alpha": model.params.iloc[0] * TRADING_PERIODS_PER_YEAR,
        "alpha_tstat": model.tvalues.iloc[0],
        "alpha_pvalue": model.pvalues.iloc[0],
        "beta": model.params.iloc[1],
        "r_squared": model.rsquared,
    }


# ---------------------------------------------------------------------------
# Time-varying risk-free rate (LIMITATIONS_PLAN.md, Phase 1A).
#
# The functions above take one constant annual rate. The versions below take
# a monthly risk-free series instead (one rate per month, as a decimal), so a
# T-bill rate can be charged month by month. They are separate functions so
# that the published flat-2% figures keep coming from unchanged code. With a
# constant series equal to (1.02)^(1/12) - 1 they reproduce the functions
# above, which tests/test_risk.py checks.
# ---------------------------------------------------------------------------

def tbill_yield_to_monthly(yield_pct: pd.Series) -> pd.Series:
    """
    Convert an annual yield quoted in percent (e.g. 5.0 for 5%) to a
    monthly decimal rate: (1 + y/100)^(1/12) - 1. Same compounding
    convention as the flat rate in sharpe_ratio() and alpha() above.
    """
    return (1 + yield_pct / 100) ** (1 / TRADING_PERIODS_PER_YEAR) - 1


def align_risk_free(returns: pd.Series, rf_monthly: pd.Series) -> pd.Series:
    """
    The monthly risk-free rate for exactly the dates in `returns`. Raises
    instead of silently dropping or filling months, because a missing rate
    would change which months the ratio is measured over.
    """
    rf = rf_monthly.reindex(returns.index)
    if rf.isna().any():
        missing = list(returns.index[rf.isna()])
        raise ValueError(f"No risk-free rate for {len(missing)} return date(s), e.g. {missing[:3]}")
    return rf


def annualized_risk_free(rf_monthly: pd.Series) -> float:
    """
    Compound the monthly risk-free rates into one annual rate, with the
    same convention as annualized_return(), so the two can be subtracted.
    """
    return annualized_return(rf_monthly)


def sharpe_ratio_tbill(returns: pd.Series, rf_monthly: pd.Series) -> float:
    """
    Sharpe ratio against a monthly risk-free series: the strategy's
    annualized return minus the compounded annualized risk-free return over
    the same months, divided by the annualized volatility of the strategy's
    own returns (LIMITATIONS_PLAN.md, Amendment 1, item 3).
    """
    rf = align_risk_free(returns, rf_monthly)
    return (annualized_return(returns) - annualized_risk_free(rf)) / annualized_volatility(returns)


def downside_deviation_tbill(returns: pd.Series, rf_monthly: pd.Series) -> float:
    """
    Annualized downside deviation with month t's risk-free rate as month
    t's target. Otherwise identical to downside_deviation(): months above
    the target count as zero shortfall but stay in the average.
    """
    rf = align_risk_free(returns, rf_monthly)
    shortfall = np.minimum(returns - rf, 0)
    return np.sqrt((shortfall ** 2).mean()) * np.sqrt(TRADING_PERIODS_PER_YEAR)


def sortino_ratio_tbill(returns: pd.Series, rf_monthly: pd.Series) -> float:
    """
    Sortino ratio against a monthly risk-free series, built the same way
    as sharpe_ratio_tbill(). Returns NaN if the series never falls below
    the target (ratio undefined).
    """
    downside = downside_deviation_tbill(returns, rf_monthly)
    if downside == 0:
        return np.nan
    rf = align_risk_free(returns, rf_monthly)
    return (annualized_return(returns) - annualized_risk_free(rf)) / downside


def alpha_regression_tbill(returns: pd.Series, benchmark_returns: pd.Series, rf_monthly: pd.Series) -> dict:
    """
    Same OLS as alpha_regression(), but month t's risk-free rate is
    deducted from both the strategy's and the benchmark's month-t return:

        (r_t - rf_t) = alpha + beta * (b_t - rf_t) + error
    """
    aligned = pd.concat([returns, benchmark_returns], axis=1).dropna()
    rf = align_risk_free(aligned.iloc[:, 0], rf_monthly)
    y = aligned.iloc[:, 0] - rf
    x = sm.add_constant(aligned.iloc[:, 1] - rf)
    model = sm.OLS(y, x).fit()
    return {
        "alpha": model.params.iloc[0] * TRADING_PERIODS_PER_YEAR,
        "alpha_tstat": model.tvalues.iloc[0],
        "alpha_pvalue": model.pvalues.iloc[0],
        "beta": model.params.iloc[1],
        "r_squared": model.rsquared,
    }


# ---------------------------------------------------------------------------
# Statistical power (LIMITATIONS_PLAN.md, Phase 1C, Amendments 1 and 3).
#
# These describe a test of a mean return against zero, using the standard
# two-sided normal approximation (z_alpha + z_power), which ignores the far
# tail. They are not the beta-adjusted alpha regression above.
# ---------------------------------------------------------------------------

def power_z_values(alpha_two_sided: float, power: float) -> tuple[float, float]:
    """
    Critical values for a two-sided test at level alpha_two_sided with the
    given power: z_alpha = Phi^-1(1 - alpha/2), z_power = Phi^-1(power).
    E.g. (0.10, 0.80) -> (1.645, 0.842).
    """
    return float(norm.ppf(1 - alpha_two_sided / 2)), float(norm.ppf(power))


def minimum_detectable_effect(sd: float, n: int, z_alpha: float, z_power: float) -> float:
    """
    Smallest true mean that a sample of n observations with standard
    deviation sd would detect at the given level and power:
    (z_alpha + z_power) * sd / sqrt(n). Same units as sd (monthly in,
    monthly out).
    """
    if n < 2:
        raise ValueError("n must be at least 2.")
    if sd < 0:
        raise ValueError("sd cannot be negative.")
    return (z_alpha + z_power) * sd / np.sqrt(n)


def months_needed_to_detect(mean: float, sd: float, z_alpha: float, z_power: float) -> dict:
    """
    Number of observations needed for a mean of this size to be detected:
    ((z_alpha + z_power) * sd / |mean|)^2, rounded up to a whole month.

    The value is rounded to 9 decimals before rounding up, so that an exact
    answer such as 100 is not pushed to 101 by floating-point error. A zero
    mean has no answer (NaN). A negative mean is detectable as
    underperformance under a two-sided test, so |mean| is used and the
    direction is reported.

    Returns {"months": int or NaN, "direction": str, "note": str}.
    """
    if mean == 0:
        return {"months": np.nan, "direction": "none",
                "note": "mean active return is zero: not detectable at any sample length"}
    raw = ((z_alpha + z_power) * sd / abs(mean)) ** 2
    months = int(np.ceil(round(raw, 9)))
    if mean < 0:
        return {"months": months, "direction": "underperformance",
                "note": "negative mean: months needed to detect underperformance, not outperformance"}
    return {"months": months, "direction": "outperformance", "note": ""}


# ---------------------------------------------------------------------------
# Risk diagnostics (LIMITATIONS_PLAN.md, Phase 2B detailed design).
# Descriptive measures on monthly returns; no test between strategies.
# ---------------------------------------------------------------------------

def _tail_percentile(returns: pd.Series, level: float) -> float:
    """
    The (1 - level) percentile of the returns, with numpy's linear
    interpolation. The percentile is rounded to 10 decimals first so that,
    e.g., level 0.95 asks for exactly the 5th percentile rather than
    5.000000000000004 from floating-point subtraction.
    """
    return float(np.percentile(returns.values, round((1 - level) * 100, 10), method="linear"))


def historical_var(returns: pd.Series, level: float = 0.95) -> float:
    """
    Historical Value at Risk: the return at the (1 - level) percentile,
    reported as a positive loss. 0.06 means that in (1 - level) of months the
    return was -6% or worse. Not clipped: if even the tail month is a gain,
    the figure is negative.
    """
    return -_tail_percentile(returns, level)


def expected_shortfall(returns: pd.Series, level: float = 0.95) -> float:
    """
    Historical Expected Shortfall: the average return over the months at or
    below the (1 - level) percentile, reported as a positive loss.
    """
    cutoff = _tail_percentile(returns, level)
    return -float(returns[returns <= cutoff].mean())


def bootstrap_statistic_ci(returns: pd.Series, statistic, n_sims: int = 5000, ci: float = 0.90, seed: int | None = None) -> dict:
    """
    Bootstrap confidence interval for any statistic of one return series,
    in the same style as bootstrap_sharpe_ci(): resample the months with
    replacement n_sims times, recompute the statistic, take percentiles.

    The resampled month positions depend only on the seed and the series
    length, not on the values. So with the same seed (42 in the scripts),
    every series of the same length gets the same resampled month indices,
    and the intervals are paired across strategies: each resample draws the
    same months for all of them.
    """
    rng = np.random.default_rng(seed)
    n = len(returns)
    vals = returns.values
    stats = np.empty(n_sims)
    for i in range(n_sims):
        idx = rng.integers(0, n, size=n)
        stats[i] = statistic(pd.Series(vals[idx]))
    lower = float(np.percentile(stats, (1 - ci) / 2 * 100))
    upper = float(np.percentile(stats, (1 + ci) / 2 * 100))
    return {
        "point": statistic(returns),
        "lower": lower,
        "upper": upper,
        "ci": ci,
        "n_sims": n_sims,
    }


def hit_rate(returns: pd.Series) -> float:
    """Share of months with a positive return. A month of exactly 0 is not positive."""
    return float((returns > 0).mean())


def hit_rate_vs_benchmark(returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """
    Share of months in which the strategy's return was strictly above the
    benchmark's. A tie does not count. The two series must cover the same
    dates.
    """
    if not returns.index.equals(benchmark_returns.index):
        raise ValueError("returns and benchmark_returns must cover the same dates.")
    return float((returns > benchmark_returns).mean())


def drawdown_series(returns: pd.Series, start_date) -> pd.DataFrame:
    """
    Underwater curve: cumulative value divided by its running maximum,
    minus 1, month by month, with a starting value of 1.0 at start_date
    (the month-end before the first return).

    Same formula as max_drawdown() above. The only difference is the 1.0
    starting point: max_drawdown() starts its running maximum at the value
    after the first month, so a first-month loss that is never recovered
    before the deepest trough would make this series' minimum deeper.

    The monthly_return column holds the input returns and is blank (NaN) on
    the starting row, which is a starting value, not a month of return.
    """
    start = pd.Timestamp(start_date)
    if start >= returns.index[0]:
        raise ValueError("start_date must be before the first return date.")
    cumulative = pd.concat([pd.Series([1.0], index=[start]), (1 + returns).cumprod()])
    running_peak = cumulative.cummax()
    return pd.DataFrame({
        "monthly_return": pd.concat([pd.Series([np.nan], index=[start]), returns.astype(float)]),
        "cumulative_value": cumulative,
        "running_peak": running_peak,
        "drawdown": (cumulative - running_peak) / running_peak,
    })