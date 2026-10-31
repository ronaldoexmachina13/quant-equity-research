"""
Signal evaluation for Phase 4 (LIMITATIONS_PLAN.md, Phase 4 detailed design).

Timing: every signal frame follows the convention of src/factors.py, where
the row dated t holds a score built only from information up to the end of
t-1. That row is paired with the return dated t, the return earned during
month t. No further lag is applied here.

Usable names: a name is in a month's cross-section if it has a signal value.
Callers mask a signal to the usable names (NaN elsewhere) before calling these
functions. A name with a signal and no return in month t keeps its place in
the cross-section, because whether it would have a return was not known at
t-1, and it is dropped only from the return calculation.
"""
import math

import numpy as np
import pandas as pd

MIN_NAMES_PER_MONTH = 100  # Phase 3 rule 1: a month is used for a signal only with at least 100 usable names


# ---------------------------------------------------------------------------
# One month's cross-section
# ---------------------------------------------------------------------------

def rank_ic(signal: pd.Series, returns: pd.Series) -> float:
    """
    Rank information coefficient: the Spearman correlation between the signal
    and the return, over names with both. Tied values share their average
    rank. NaN if fewer than two names remain or either side has no variation.
    """
    pairs = pd.concat([signal, returns], axis=1, keys=["signal", "return"]).dropna()
    if len(pairs) < 2:
        return np.nan
    ranks = pairs.rank(method="average")
    if ranks["signal"].nunique() < 2 or ranks["return"].nunique() < 2:
        return np.nan
    return float(ranks["signal"].corr(ranks["return"]))


def assign_quintiles(signal: pd.Series, q: int = 5) -> pd.Series:
    """
    Group of each name by signal, from 1 (lowest) to q (highest), using
    ceil(rank * q / N) on average ranks, where N counts the names with a
    signal. Tied names share a group, so group sizes can differ by more than
    one when a tie sits on a boundary. Names with no signal get NaN.
    """
    ranks = signal.rank(method="average")
    n_names = signal.notna().sum()
    return ranks.map(lambda rank: float(math.ceil(rank * q / n_names)), na_action="ignore")


def quintile_spread(signal: pd.Series, returns: pd.Series, q: int = 5) -> float:
    """
    Equal-weight return of the top group minus that of the bottom group.
    Groups are assigned on all names with a signal, before any return is
    looked at; names with no return are then left out of the averages. NaN if
    either group has no return.
    """
    groups = assign_quintiles(signal, q)
    aligned = returns.reindex(groups.index)
    return float(aligned[groups == q].mean() - aligned[groups == 1].mean())


def standardise(signal: pd.Series) -> pd.Series:
    """Cross-sectional z-score with the sample standard deviation, as in calculate_combined_score()."""
    return (signal - signal.mean()) / signal.std()


def cross_section_slopes(signals: pd.DataFrame, returns: pd.Series) -> pd.Series:
    """
    Slopes of one month's OLS of return on the standardised signals, with an
    intercept. Each slope is the return associated with one standard deviation
    of that signal.

    The names are those with every signal. The z-scores are computed over all
    of them, and the regression then runs on the ones with a return. All slopes
    are NaN if there are too few names to estimate, or the signals are
    constant or collinear.
    """
    no_estimate = pd.Series(np.nan, index=signals.columns)
    complete = signals.dropna()
    if len(complete) < 2:
        return no_estimate
    z_scores = complete.apply(standardise)
    y = returns.reindex(z_scores.index).dropna()
    x = np.column_stack([np.ones(len(y)), z_scores.loc[y.index].values])
    if len(y) <= x.shape[1] or not np.isfinite(x).all() or np.linalg.matrix_rank(x) < x.shape[1]:
        return no_estimate
    coefficients = np.linalg.lstsq(x, y.values, rcond=None)[0]
    return pd.Series(coefficients[1:], index=signals.columns)


# ---------------------------------------------------------------------------
# Monthly series
# ---------------------------------------------------------------------------

def monthly_cross_section(signal: pd.DataFrame, returns: pd.DataFrame, date,
                          min_names: int = MIN_NAMES_PER_MONTH) -> tuple[pd.Series, pd.Series]:
    """
    The usable names' signals and returns for one month, signal row and return
    row both dated `date`. A name with no return comes back as NaN. The signal
    is empty if fewer than min_names names have one (the month is not used).
    """
    names = signal.loc[date].dropna()
    if len(names) < min_names:
        names = names.iloc[:0]
    row = returns.loc[date] if date in returns.index else pd.Series(dtype=float)
    return names, row.reindex(names.index)


def monthly_statistic(signal: pd.DataFrame, returns: pd.DataFrame, statistic,
                      min_names: int = MIN_NAMES_PER_MONTH) -> pd.Series:
    """statistic(signal, returns) for each month, NaN in months with too few usable names."""
    values = {}
    for date in signal.index:
        names, month_returns = monthly_cross_section(signal, returns, date, min_names)
        values[date] = statistic(names, month_returns) if len(names) else np.nan
    return pd.Series(values, index=signal.index, dtype=float)


def monthly_counts(signal: pd.DataFrame, returns: pd.DataFrame) -> pd.DataFrame:
    """Per month, the number of usable names and how many of them have no return."""
    aligned = returns.reindex(index=signal.index, columns=signal.columns)
    usable = signal.notna()
    return pd.DataFrame({"usable": usable.sum(axis=1), "no_return": (usable & aligned.isna()).sum(axis=1)})


def fama_macbeth_slopes(signals: dict, returns: pd.DataFrame,
                        min_names: int = MIN_NAMES_PER_MONTH) -> pd.DataFrame:
    """
    Fama-MacBeth first step: one cross-sectional regression per month, on one
    signal or on several together. Returns one row per month and one column
    per signal; the slopes are averaged over a period by the caller.

    Parameters
    ----------
    signals : {name: wide signal frame}, all with the same dates.
    returns : wide monthly returns.
    min_names : a month is used only if this many names have every signal.
    """
    names = list(signals)
    dates = signals[names[0]].index
    rows = {}
    for date in dates:
        row = pd.DataFrame({name: signals[name].loc[date] for name in names})
        if len(row.dropna()) < min_names:
            rows[date] = pd.Series(np.nan, index=names)
            continue
        month_returns = returns.loc[date] if date in returns.index else pd.Series(dtype=float)
        rows[date] = cross_section_slopes(row, month_returns)
    return pd.DataFrame.from_dict(rows, orient="index", columns=names).reindex(dates)
