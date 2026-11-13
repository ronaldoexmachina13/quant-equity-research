"""
Benchmark regression and reference-factor check (LIMITATIONS_PLAN.md, Amendment 16).
Both are exploratory and post-results, and change no registered figure.

Why a regression. The registered test compares the Sharpe ratio of a top-decile
portfolio with that of the equal-weight benchmark. A top decile can be riskier
than the benchmark for reasons that have nothing to do with the signal, for
example a heavy weight in one sector. Regressing the portfolio's monthly excess
return on the benchmark's separates two things: beta, how much benchmark risk
the portfolio carries, and alpha, the average return left over after that beta.

Why a reference check. Kenneth French publishes monthly Momentum (UMD) and
value (HML) factors built from all US stocks. The long-short spreads of this
study are built from a smaller index universe, so they should not match those
factors exactly. They should move in the same direction, and a near-zero or
negative correlation would point to an error in the pipeline.
"""
import math

import numpy as np
import pandas as pd
from scipy.stats import norm, spearmanr

from src.signal_extras import newey_west_lags

MONTHS_PER_YEAR = 12


def regress_on_benchmark(excess: pd.Series, benchmark_excess: pd.Series, lags: int | None = None,
                         ci: float = 0.90) -> dict:
    """
    OLS of the portfolio's monthly excess return on the benchmark's monthly excess
    return, excess_t = alpha + beta * benchmark_t + error_t. Standard errors are
    Newey-West (Bartlett kernel, no small-sample correction), with lags from
    newey_west_lags(n) unless given. Only months present in both series are used.
    """
    # sort_index(): the Newey-West lags pair each month with the months just before it, so the rows
    # must be in date order. concat does not reorder inputs that already share an index, and pandas 4
    # will not sort a union of dates either, so the order is set here. sort=True keeps today's behaviour.
    both = pd.concat([excess, benchmark_excess], axis=1, keys=["y", "x"], sort=True).dropna().sort_index()
    n = len(both)
    if n < 10:
        raise ValueError(f"only {n} common months; at least 10 are needed")
    y = both["y"].to_numpy(dtype=float)
    X = np.column_stack([np.ones(n), both["x"].to_numpy(dtype=float)])
    lags = newey_west_lags(n) if lags is None else lags
    xtx_inv = np.linalg.inv(X.T @ X)
    coef = xtx_inv @ X.T @ y
    residual = y - X @ coef
    scores = X * residual[:, None]            # row t is x_t * u_t
    S = scores.T @ scores
    for j in range(1, min(lags, n - 1) + 1):
        weight = 1 - j / (lags + 1)
        gamma = scores[j:].T @ scores[:-j]
        S += weight * (gamma + gamma.T)
    covariance = xtx_inv @ S @ xtx_inv
    se = np.sqrt(np.diag(covariance))
    z = float(norm.ppf((1 + ci) / 2))
    total = ((y - y.mean()) ** 2).sum()
    r_squared = 1 - (residual ** 2).sum() / total if total > 0 else float("nan")
    return {"months": n, "lags": lags, "alpha": float(coef[0]), "alpha_se": float(se[0]),
            "alpha_t": float(coef[0] / se[0]) if se[0] > 0 else float("nan"),
            "alpha_lower": float(coef[0] - z * se[0]), "alpha_upper": float(coef[0] + z * se[0]),
            "beta": float(coef[1]), "beta_se": float(se[1]), "r_squared": float(r_squared)}


def regress_on_factors(excess: pd.Series, factors: pd.DataFrame, lags: int | None = None, ci: float = 0.90) -> dict:
    """
    OLS of a monthly excess return on several factor columns (Amendment 18):
    excess_t = alpha + sum_k beta_k * factor_k,t + error_t. The standard errors are Newey-West exactly as in
    regress_on_benchmark (Bartlett kernel, no small-sample correction, lags from newey_west_lags(n) unless given).
    Only months present in the return and in every factor are used. The result holds alpha with its
    interval and, for each factor, its loading and standard error.
    """
    both = pd.concat([excess.rename("__y__"), factors], axis=1, sort=True).dropna().sort_index()  # date order, as above
    n = len(both)
    k = factors.shape[1]
    if n < 10 + k:
        raise ValueError(f"only {n} common months; at least {10 + k} are needed")
    y = both["__y__"].to_numpy(dtype=float)
    X = np.column_stack([np.ones(n), both[list(factors.columns)].to_numpy(dtype=float)])
    lags = newey_west_lags(n) if lags is None else lags
    xtx_inv = np.linalg.inv(X.T @ X)
    coef = xtx_inv @ X.T @ y
    residual = y - X @ coef
    scores = X * residual[:, None]
    S = scores.T @ scores
    for j in range(1, min(lags, n - 1) + 1):
        weight = 1 - j / (lags + 1)
        gamma = scores[j:].T @ scores[:-j]
        S += weight * (gamma + gamma.T)
    se = np.sqrt(np.diag(xtx_inv @ S @ xtx_inv))
    z = float(norm.ppf((1 + ci) / 2))
    total = ((y - y.mean()) ** 2).sum()
    out = {"months": n, "lags": lags, "alpha": float(coef[0]), "alpha_se": float(se[0]),
           "alpha_t": float(coef[0] / se[0]) if se[0] > 0 else float("nan"),
           "alpha_lower": float(coef[0] - z * se[0]), "alpha_upper": float(coef[0] + z * se[0]),
           "r_squared": float(1 - (residual ** 2).sum() / total) if total > 0 else float("nan")}
    for i, name in enumerate(factors.columns, start=1):
        out[f"beta_{name}"] = float(coef[i])
        out[f"beta_{name}_se"] = float(se[i])
    return out


def annualise_alpha(alpha_monthly: float) -> float:
    """Monthly alpha times 12. A simple scaling, not compounding, as the regression is in monthly arithmetic returns."""
    return alpha_monthly * MONTHS_PER_YEAR


def correlation_with_reference(series: pd.Series, reference: pd.Series, ci: float = 0.90) -> dict:
    """
    Pearson and Spearman correlation over the months both series have. The
    interval is the Fisher z interval for Pearson, which treats months as
    independent and is therefore only indicative.
    """
    both = pd.concat([series, reference], axis=1, keys=["a", "b"]).dropna()
    n = len(both)
    if n < 10:
        raise ValueError(f"only {n} common months; at least 10 are needed")
    r = float(np.corrcoef(both["a"], both["b"])[0, 1])
    z = math.atanh(r)
    half = float(norm.ppf((1 + ci) / 2)) / math.sqrt(n - 3)
    rho = float(spearmanr(both["a"], both["b"])[0])
    return {"months": n, "pearson": r, "pearson_lower": math.tanh(z - half), "pearson_upper": math.tanh(z + half),
            "spearman": rho}


def read_french(path: str, columns: list[str]) -> pd.DataFrame:
    """
    Read a French monthly file stored without a header (YYYYMM, then the columns). Values are percent and are
    returned as decimals. The index is the month end date, to match the study files.
    """
    frame = pd.read_csv(path, header=None, names=["yyyymm"] + columns, dtype={"yyyymm": str})
    frame.index = pd.to_datetime(frame.pop("yyyymm"), format="%Y%m") + pd.offsets.MonthEnd(0)
    return frame / 100.0
