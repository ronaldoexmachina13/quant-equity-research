"""
Portfolio tests for Phase 4, Stage 4 (LIMITATIONS_PLAN.md, Phase 4 detailed
design, Amendments 8 to 12, and Amendment 13).

Each month the usable names are ranked by signal, and the top decile or top
quintile is held at equal weight for one month. Groups use assign_quintiles()
from src/signal_eval.py, the ceil(rank x q / N) rule on average ranks, so tied
names share a group and the number held varies (Amendment 8, reading 4). A
signal row dated t uses data up to the end of t-1 and is paired with the
return dated t (reading 1).

A held name with no return in month t is dropped and the month's return is
the mean of the remaining holdings (reading 5). In the drift-inclusive
turnover such a name is treated as sold at its last available weight
(Amendment 13, decision 10), which is what calculate_turnover_with_drift()
does when it counts a missing return as 0.

Costs are the published 10 bps one-way, on both turnover bases of Amendment 2.
The first month of a run is a purchase from cash on both bases (decision 9).
"""
from pathlib import Path

import pandas as pd

from src.backtest import calculate_turnover, calculate_turnover_with_drift, apply_transaction_costs
from src.risk import (
    total_return, annualized_return, annualized_volatility, sharpe_ratio, sharpe_ratio_tbill, drawdown_series,
    bootstrap_sharpe_diff, bootstrap_sharpe_diff_tbill,
)
from src.signal_eval import assign_quintiles, MONTHS_PER_YEAR
from src.universe import cache_dir
from src.universe_study import monthly_frame
from src.universe_value import HEADLINE, EXCLUDING_24, EXCLUDING_37

COST_BPS = 10                  # published one-way cost
FLAT_RF = 0.02                 # flat rate of the published study, for comparison only
SPY_TOLERANCE = 1e-6           # Amendment 13, decision 7: SPY against the saved 2021 to 2026 series
SIZES = {"top_decile": 10, "top_quintile": 5}

GROSS, NET_DRIFT, NET_EXISTING = "gross", "net_drift", "net_existing"
# basis: (strategy column, benchmark column). The benchmark is always charged
# on the drift-inclusive basis (Amendment 2; Amendment 13, decision 1).
BASES = {GROSS: (GROSS, GROSS), NET_DRIFT: (NET_DRIFT, NET_DRIFT), NET_EXISTING: (NET_EXISTING, NET_DRIFT)}
HEADLINE_BASIS = GROSS

MOMENTUM_BENCHMARK = "Benchmark (Momentum usable)"
VALUE_BENCHMARK = "Benchmark (Value and Combined usable)"
SPY_LABEL = "SPY (reference)"
REMOVED, STAYED = "removed", "stayed"

PORTFOLIO_SETS = [HEADLINE, EXCLUDING_24, EXCLUDING_37]
HEADLINE_PARTS = ["portfolio_returns", "portfolio_summary", "survivorship"]
SENSITIVITY_PARTS = ["portfolio_returns", "portfolio_summary"]
RESULTS_DIR = Path("results")


# ---------------------------------------------------------------------------
# Weights and monthly series
# ---------------------------------------------------------------------------

def top_group_weights(signal: pd.DataFrame, q: int) -> pd.DataFrame:
    """Equal weight across the names in the top group (group q) each month, 0 elsewhere. A row with no signal holds nothing."""
    weights = pd.DataFrame(0.0, index=signal.index, columns=signal.columns)
    for date, row in signal.iterrows():
        if row.notna().sum() == 0:
            continue
        held = assign_quintiles(row, q) == q
        if held.any():
            weights.loc[date, held] = 1.0 / held.sum()
    return weights


def universe_weights(mask: pd.DataFrame) -> pd.DataFrame:
    """The equal-weight benchmark: 1/N across the names marked True each month."""
    flags = mask.astype(float)
    return flags.div(flags.sum(axis=1), axis=0).fillna(0.0)


def held_returns(weights: pd.DataFrame, returns: pd.DataFrame) -> pd.Series:
    """
    Weighted return of the holdings that have a return in the month, with the
    weights rescaled over those names (reading 5). NaN if no holding has one.
    Equal to run_backtest() when every holding has a return.
    """
    r = returns.reindex(index=weights.index, columns=weights.columns)
    has_return = (weights > 0) & r.notna()
    invested = weights.where(has_return, 0.0).sum(axis=1)
    return (weights * r).where(has_return, 0.0).sum(axis=1) / invested


def held_without_return(weights: pd.DataFrame, returns: pd.DataFrame) -> pd.Series:
    """Number of held names with no return in each month."""
    r = returns.reindex(index=weights.index, columns=weights.columns)
    return ((weights > 0) & r.isna()).sum(axis=1)


def portfolio_series(weights: pd.DataFrame, returns: pd.DataFrame, cost_bps: float = COST_BPS) -> pd.DataFrame:
    """Names held, gross return, turnover on both bases and the two net returns, one row per month."""
    gross = held_returns(weights, returns)
    existing = calculate_turnover(weights)
    drift = calculate_turnover_with_drift(weights, returns)
    return pd.DataFrame({
        "names_held": (weights > 0).sum(axis=1),
        "names_without_return": held_without_return(weights, returns),
        GROSS: gross,
        "turnover_existing": existing,
        "turnover_drift": drift,
        NET_EXISTING: apply_transaction_costs(gross, existing, cost_bps),
        NET_DRIFT: apply_transaction_costs(gross, drift, cost_bps),
    })


def top_group_changes(signal_a: pd.DataFrame, signal_b: pd.DataFrame, q: int) -> list[str]:
    """Months in which the top group differs between two signals (Amendment 13, decision 6). Report only."""
    held_a, held_b = top_group_weights(signal_a, q) > 0, top_group_weights(signal_b, q) > 0
    differs = (held_a != held_b).any(axis=1)
    return list(differs.index[differs].strftime("%Y-%m"))


# ---------------------------------------------------------------------------
# Period metrics and paired tests
# ---------------------------------------------------------------------------

def max_drawdown_from_start(returns: pd.Series) -> float:
    """Deepest point of drawdown_series(), starting at 1.0 at the month end before the first return."""
    start = returns.index[0] - pd.offsets.MonthEnd(1)
    return float(drawdown_series(returns, start)["drawdown"].min())


def period_metrics(returns: pd.Series, rf_monthly: pd.Series) -> dict:
    return {
        "months": len(returns),
        "total_return": total_return(returns),
        "annualized_return": annualized_return(returns),
        "annualized_volatility": annualized_volatility(returns),
        "sharpe_tbill": sharpe_ratio_tbill(returns, rf_monthly),
        "sharpe_flat_2pct": sharpe_ratio(returns, FLAT_RF),
        "max_drawdown": max_drawdown_from_start(returns),
    }


def sharpe_difference(strategy: pd.Series, benchmark: pd.Series, rf_monthly: pd.Series,
                      n_sims: int = 5000, seed: int = 42) -> dict:
    """Paired 90% intervals with the T-bill rate and, for comparison only, the flat 2% (Amendment 13, decision 1)."""
    tbill = bootstrap_sharpe_diff_tbill(strategy, benchmark, rf_monthly, n_sims=n_sims, seed=seed)
    flat = bootstrap_sharpe_diff(strategy, benchmark, FLAT_RF, n_sims=n_sims, seed=seed)
    return {
        "sharpe_diff_tbill": tbill["point_diff"], "ci_90_lower_tbill": tbill["lower"],
        "ci_90_upper_tbill": tbill["upper"], "significant_tbill": tbill["significant"],
        "sharpe_diff_flat_2pct": flat["point_diff"], "ci_90_lower_flat_2pct": flat["lower"],
        "ci_90_upper_flat_2pct": flat["upper"], "significant_flat_2pct": flat["significant"],
    }


def strategy_summary(strategy: str, size: str, series: pd.DataFrame, benchmark: pd.DataFrame, benchmark_name: str,
                     rf_monthly: pd.Series, periods: dict, n_sims: int = 5000, seed: int = 42) -> pd.DataFrame:
    """One row per period and basis for one portfolio, with its test against its own benchmark."""
    rows = []
    for period, dates in periods.items():
        s, b = series.loc[dates], benchmark.loc[dates]
        for basis, (column, benchmark_column) in BASES.items():
            rows.append({
                "period": period, "strategy": strategy, "size": size, "basis": basis,
                "headline_test": basis == HEADLINE_BASIS,
                **period_metrics(s[column], rf_monthly),
                "avg_turnover_existing": s["turnover_existing"].mean(),
                "avg_turnover_drift": s["turnover_drift"].mean(),
                "names_held_min": int(s["names_held"].min()), "names_held_max": int(s["names_held"].max()),
                "benchmark": benchmark_name, "benchmark_basis": benchmark_column,
                "benchmark_sharpe_tbill": sharpe_ratio_tbill(b[benchmark_column], rf_monthly),
                "benchmark_sharpe_flat_2pct": sharpe_ratio(b[benchmark_column], FLAT_RF),
                **sharpe_difference(s[column], b[benchmark_column], rf_monthly, n_sims, seed),
            })
    return pd.DataFrame(rows)


def reference_summary(name: str, series: pd.DataFrame, bases: list[str], rf_monthly: pd.Series,
                      periods: dict) -> pd.DataFrame:
    """Rows for a benchmark or SPY: metrics only, no test. Turnover is filled where the series has it."""
    rows = []
    for period, dates in periods.items():
        s = series.loc[dates]
        for basis in bases:
            row = {"period": period, "strategy": name, "basis": basis, "headline_test": False,
                   **period_metrics(s[basis], rf_monthly)}
            for column in ("turnover_existing", "turnover_drift"):
                if column in s:
                    row[f"avg_{column}"] = s[column].mean()
            if "names_held" in s:
                row["names_held_min"], row["names_held_max"] = int(s["names_held"].min()), int(s["names_held"].max())
            rows.append(row)
    return pd.DataFrame(rows)


def returns_frame(strategy: str, size: str | None, series: pd.DataFrame, rf_monthly: pd.Series) -> pd.DataFrame:
    """The monthly series of one portfolio, benchmark or SPY, with its period and the month's T-bill rate."""
    frame = monthly_frame(series.index)
    frame["strategy"], frame["size"] = strategy, size
    for column in series.columns:
        frame[column] = series[column].values
    frame["rf_monthly"] = rf_monthly.reindex(series.index).values
    return frame


# ---------------------------------------------------------------------------
# Survivorship diagnostic (descriptive, Amendment 13, decision 8)
# ---------------------------------------------------------------------------

def survivorship_monthly(mask: pd.DataFrame, returns: pd.DataFrame, groups: pd.Series) -> pd.DataFrame:
    """
    Each month, the number of usable names with a return and their equal-weight
    mean return, for removed and stayed names. The grouping uses each name's
    full membership history, so it is descriptive and never selects names.
    """
    r = returns.reindex(index=mask.index, columns=mask.columns).where(mask)
    columns = {}
    for group in (REMOVED, STAYED):
        names = [t for t in mask.columns if groups.get(t) == group]
        columns[f"{group}_names"] = r[names].notna().sum(axis=1)
        columns[f"{group}_mean"] = r[names].mean(axis=1)
    return pd.DataFrame(columns, index=mask.index)


def survivorship_summary(monthly: pd.DataFrame, periods: dict, universe_set: str) -> pd.DataFrame:
    """
    By period: months, months with no name in the group, average names, mean
    monthly return over the months the group has names, and that mean x 12.
    The difference row is the removed mean minus the stayed mean.
    """
    rows = []
    for period, dates in periods.items():
        sub = monthly.loc[dates]
        means = {}
        for group in (REMOVED, STAYED):
            names, mean = sub[f"{group}_names"], sub[f"{group}_mean"].mean()
            means[group] = mean
            rows.append({"period": period, "universe_set": universe_set, "group": group, "months": len(sub),
                         "months_empty": int((names == 0).sum()), "names_per_month_avg": names.mean(),
                         "mean_monthly_return": mean, "annualised_mean": mean * MONTHS_PER_YEAR})
        difference = means[REMOVED] - means[STAYED]
        rows.append({"period": period, "universe_set": universe_set, "group": "removed_minus_stayed",
                     "months": len(sub), "mean_monthly_return": difference,
                     "annualised_mean": difference * MONTHS_PER_YEAR})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# SPY reference (Amendment 13, decision 7)
# ---------------------------------------------------------------------------

def spy_cache_path() -> Path:
    return cache_dir() / "reference" / "SPY.csv.gz"


def spy_month_end_returns(daily: pd.DataFrame, calendar: pd.Series) -> pd.Series:
    """
    Adjusted close on the study's last trading day of each month, and its
    change from one month end to the next, dated at the calendar month end.
    """
    prices = daily["Adj Close"].reindex(pd.DatetimeIndex(calendar.values))
    returns = prices.pct_change(fill_method=None)
    returns.index = returns.index.to_period("M").to_timestamp(how="end").normalize()
    return returns.rename("SPY")


def spy_overlap_failures(new: pd.Series, saved: pd.Series, tolerance: float = SPY_TOLERANCE) -> list[str]:
    """Every month of the saved series must have a new return within the tolerance."""
    if saved.empty:
        return ["the saved SPY series is empty"]
    failures = []
    for date, expected in saved.items():
        found = new.get(date)
        if found is None or pd.isna(found) or not abs(found - expected) <= tolerance:
            failures.append(f"{date:%Y-%m}: new {found!r}, saved {expected!r}")
    return failures


# ---------------------------------------------------------------------------
# Checks and outputs
# ---------------------------------------------------------------------------

def stage3_count_failures(found: pd.Series, stage3: pd.DataFrame, column: str, label: str) -> list[str]:
    """Usable names per month against a committed Stage 3 monthly_counts file, which must match exactly."""
    expected = stage3.set_index(pd.to_datetime(stage3["date"]))[column]
    aligned = pd.DataFrame({"found": found, "expected": expected})
    differs = aligned[~(aligned["found"] == aligned["expected"])]
    return [f"{label} {d:%Y-%m}: found {r.found}, Stage 3 {r.expected}" for d, r in differs.iterrows()]


def portfolio_outputs(folder: Path = RESULTS_DIR) -> dict:
    """
    {(set, part): path}. The registered names hold the headline only; the
    exclusion sets get the suffixes _excl_24 and _excl_37 (Amendment 13, decision 4).
    """
    paths = {(HEADLINE, part): folder / f"universe_study_{part}.csv" for part in HEADLINE_PARTS}
    for name in (EXCLUDING_24, EXCLUDING_37):
        paths.update({(name, part): folder / f"universe_study_{part}_{name}.csv" for part in SENSITIVITY_PARTS})
    return paths
