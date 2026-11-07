"""
Additions to the signal tests (LIMITATIONS_PLAN.md, Amendment 14). They are
exploratory and post-results, and change no registered figure.

Two things are added:
- quintile mean returns: what each of the five groups earned, not only the
  top minus the bottom, to show whether the return rises step by step;
- two further intervals for a monthly mean, Newey-West and a circular block
  bootstrap, which allow for months that are not independent of each other.

The registered intervals (src/risk.py, bootstrap_statistic_ci) resample single
months. If a series is autocorrelated, for example because the same stocks
stay in the top group from one month to the next, that interval is too narrow.
"""
import math

import numpy as np
import pandas as pd
from scipy.stats import norm

from src.signal_eval import MIN_NAMES_PER_MONTH, MONTHS_PER_YEAR, assign_quintiles, monthly_cross_section


# ---------------------------------------------------------------------------
# Quintile mean returns
# ---------------------------------------------------------------------------

def quintile_group_returns(signal: pd.Series, returns: pd.Series, q: int = 5) -> pd.Series:
    """
    Equal-weight mean return of each group 1 (lowest signal) to q (highest) for
    one month. Groups are assigned as in quintile_spread(): on all names with a
    signal, before any return is looked at; names with no return are then left
    out of the averages. A group with no return is NaN.
    """
    groups = assign_quintiles(signal, q)
    aligned = returns.reindex(groups.index)
    return pd.Series({k: aligned[groups == k].mean() for k in range(1, q + 1)}, dtype=float)


def monthly_quintile_returns(signal: pd.DataFrame, returns: pd.DataFrame, q: int = 5,
                             min_names: int = MIN_NAMES_PER_MONTH) -> pd.DataFrame:
    """One row per month and one column per group. NaN in months with too few usable names."""
    rows = {}
    for date in signal.index:
        names, month_returns = monthly_cross_section(signal, returns, date, min_names)
        rows[date] = quintile_group_returns(names, month_returns, q) if len(names) else pd.Series(np.nan, index=range(1, q + 1))
    return pd.DataFrame.from_dict(rows, orient="index").reindex(signal.index)


def quintile_monotonicity(group_means: pd.Series) -> float:
    """
    Spearman correlation between the group number and the group's mean return:
    1 if the mean rises with every step, -1 if it falls with every step. With
    five groups, a value of 0.9 or more allows one adjacent pair out of order.
    """
    return float(pd.Series(group_means.index, index=group_means.index, dtype=float).corr(group_means, method="spearman"))


def quintile_return_summary(monthly: pd.DataFrame, periods: dict) -> pd.DataFrame:
    """
    One row per period and group: months used, mean monthly return, and the
    mean times 12. The monotonicity figure of the period is repeated on its rows.
    """
    rows = []
    for period, dates in periods.items():
        window = monthly.reindex(dates)
        means = window.mean()
        monotonicity = quintile_monotonicity(means)
        for group in monthly.columns:
            rows.append({"period": period, "quintile": int(group), "months": int(window[group].notna().sum()),
                         "mean_monthly": means[group], "mean_annualised": means[group] * MONTHS_PER_YEAR,
                         "monotonicity": monotonicity})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Intervals that allow for autocorrelation
# ---------------------------------------------------------------------------

def newey_west_lags(n: int) -> int:
    """floor(4 * (n / 100)^(2/9)), the rule of Newey and West (1994). 108 months give 4, 68 give 3, 176 give 4."""
    return int(math.floor(4 * (n / 100) ** (2 / 9)))


def block_length_rule(n: int) -> int:
    """ceil(n^(1/3)) months per block. 108 months give 5, 68 give 5, 176 give 6."""
    return int(math.ceil(n ** (1 / 3)))


def lag_autocorrelation(values, lag: int = 1) -> float:
    """Autocorrelation at `lag`, with the sample mean removed and the full-sample variance in the denominator."""
    x = np.asarray(values, dtype=float)
    d = x - x.mean()
    denominator = d @ d
    if len(x) <= lag or denominator == 0:
        return float("nan")
    return float(d[lag:] @ d[:-lag] / denominator)


def newey_west_se(values, lags: int) -> float:
    """
    Standard error of the mean with a Bartlett kernel. The long-run variance is
    gamma_0 + 2 * sum over j=1..lags of (1 - j / (lags + 1)) * gamma_j, where
    gamma_j is the sum of products of deviations j months apart, divided by n.
    The standard error is sqrt(long-run variance / n). With lags = 0 it is the
    population standard deviation over sqrt(n).
    """
    x = np.asarray(values, dtype=float)
    n = len(x)
    d = x - x.mean()
    long_run_variance = d @ d / n
    for j in range(1, min(lags, n - 1) + 1):
        weight = 1 - j / (lags + 1)
        long_run_variance += 2 * weight * (d[j:] @ d[:-j]) / n
    return math.sqrt(max(long_run_variance, 0.0) / n)


def newey_west_interval(series: pd.Series, lags: int | None = None, ci: float = 0.90) -> dict:
    """Mean with a normal interval from the Newey-West standard error. `lags` defaults to newey_west_lags(n)."""
    used = series.dropna()
    n = len(used)
    lags = newey_west_lags(n) if lags is None else lags
    mean = float(used.mean())
    se = newey_west_se(used.values, lags)
    z = float(norm.ppf((1 + ci) / 2))
    return {"point": mean, "lags": lags, "se": se, "t_stat": mean / se if se > 0 else float("nan"),
            "lower": mean - z * se, "upper": mean + z * se, "ci": ci}


def block_bootstrap_ci(series: pd.Series, block_length: int | None = None, n_sims: int = 5000,
                       ci: float = 0.90, seed: int | None = None) -> dict:
    """
    Circular block bootstrap interval for the mean. Each resample joins blocks
    of `block_length` consecutive months, each starting at a random month and
    wrapping round the end, until it has as many months as the series. With a
    block length of 1 this is the ordinary bootstrap of
    risk.bootstrap_statistic_ci() with the same draws.
    """
    values = series.dropna().to_numpy(dtype=float)
    n = len(values)
    block_length = block_length_rule(n) if block_length is None else block_length
    rng = np.random.default_rng(seed)
    n_blocks = math.ceil(n / block_length)
    offsets = np.arange(block_length)
    means = np.empty(n_sims)
    for i in range(n_sims):
        starts = rng.integers(0, n, size=n_blocks)
        positions = ((starts[:, None] + offsets[None, :]) % n).ravel()[:n]
        means[i] = values[positions].mean()
    return {"point": float(values.mean()), "block_length": block_length,
            "lower": float(np.percentile(means, (1 - ci) / 2 * 100)),
            "upper": float(np.percentile(means, (1 + ci) / 2 * 100)), "ci": ci, "n_sims": n_sims}


def interval_excludes_zero(lower: float, upper: float) -> bool:
    return not (lower <= 0 <= upper)


def inference_robustness_row(series: pd.Series, n_sims: int = 5000, seed: int = 42, ci: float = 0.90) -> dict:
    """The mean of a monthly series with its Newey-West and block-bootstrap intervals, over the months used."""
    used = series.dropna()
    nw = newey_west_interval(used, ci=ci)
    block = block_bootstrap_ci(used, n_sims=n_sims, ci=ci, seed=seed)
    return {
        "months": len(used), "mean": nw["point"], "autocorrelation_lag1": lag_autocorrelation(used.values, 1),
        "nw_lags": nw["lags"], "nw_se": nw["se"], "nw_t_stat": nw["t_stat"],
        "nw_ci_90_lower": nw["lower"], "nw_ci_90_upper": nw["upper"],
        "block_length": block["block_length"], "block_ci_90_lower": block["lower"], "block_ci_90_upper": block["upper"],
        "nw_excludes_zero": interval_excludes_zero(nw["lower"], nw["upper"]),
        "block_excludes_zero": interval_excludes_zero(block["lower"], block["upper"]),
    }
