import numpy as np
import pandas as pd

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


def summarize_risk(returns: pd.Series, label: str) -> dict:
    return {
        "label": label,
        "total_return": total_return(returns),
        "annualized_return": annualized_return(returns),
        "annualized_volatility": annualized_volatility(returns),
        "sharpe_ratio": sharpe_ratio(returns),
        "max_drawdown": max_drawdown(returns),
    }