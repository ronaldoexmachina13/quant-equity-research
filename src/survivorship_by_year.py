"""
Survivorship by calendar year (LIMITATIONS_PLAN.md, Amendment 15, decision 7).

A descriptive table, built from existing result files only, for the
registered Momentum, Value and Combined signals (not the 12-1 sensitivity).
For each year it puts side by side:
- the share of index members usable for the signal, for all names and for
  names later removed from the index and names that stayed (Phase 3
  coverage), and the share in the tested set (Stage 3 counts, all names);
- the mean monthly rank IC;
- the gross top-decile and benchmark levels (annualised return, Sharpe with
  the Treasury bill rate) and their Sharpe difference with a paired 90%
  bootstrap interval.

The missing names are mostly acquired or bankrupt companies and are absent
from the strategy and its benchmark alike, so survivorship affects both the
levels and the differences. Neither is presented as unbiased. The table adds
no test, and its yearly intervals, on 8 to 12 months, are not part of any
test family.
"""
import pandas as pd

from src.risk import annualized_return, sharpe_ratio_tbill, bootstrap_sharpe_diff_tbill
from src.universe_portfolio import MOMENTUM_BENCHMARK, VALUE_BENCHMARK, GROSS

SIGNALS = ("Momentum", "Value", "Combined")
UNIVERSE_SET = {"Momentum": "Momentum usable", "Value": "Value and Combined usable",
                "Combined": "Value and Combined usable"}
SHARE_COLUMN = {"Momentum": "share_usable_momentum", "Value": "share_usable_value_combined",
                "Combined": "share_usable_value_combined"}
COUNT_COLUMN = {"Momentum": "usable_momentum", "Value": "usable_value_combined", "Combined": "usable_value_combined"}
BENCHMARK = {"Momentum": MOMENTUM_BENCHMARK, "Value": VALUE_BENCHMARK, "Combined": VALUE_BENCHMARK}
GROUPS = ("all", "removed", "stayed")
TOP_DECILE = "top_decile"
FULL_YEAR = 12

BY_YEAR_NOTE = (
    "Descriptive table, no test. It uses the registered Momentum, Value and Combined signals and portfolios, not "
    "the 12-1 sensitivity. Universe: names with available data only, affected by survivorship. The missing names "
    "are mostly acquired or bankrupt companies and are absent from the strategy and its benchmark alike, so "
    "survivorship affects both the levels and the differences; neither is an unbiased estimate. Yearly intervals "
    "on 8 to 12 months are wide and are not part of any test family."
)

TABLE_COLUMNS = [
    "year", "signal", "universe_set", "months", "partial_year",
    "share_usable_all", "share_usable_removed", "share_usable_stayed", "share_usable_tested",
    "ic_months", "mean_rank_ic",
    "top_decile_months", "top_decile_annualized_return", "benchmark_annualized_return",
    "top_decile_sharpe_tbill", "benchmark_sharpe_tbill",
    "sharpe_diff_tbill", "ci_90_lower_tbill", "ci_90_upper_tbill", "interval_excludes_zero",
    "benchmark", "basis", "universe_note",
]


def _differs(found: float, expected: float, tolerance: float) -> bool:
    if pd.isna(found) and pd.isna(expected):
        return False
    return not abs(float(found) - float(expected)) <= tolerance


# ---------------------------------------------------------------------------
# Shares of the index
# ---------------------------------------------------------------------------

def yearly_shares(by_year: pd.DataFrame, column: str) -> pd.DataFrame:
    """One row per year with the share in `column` for all names, removed names and stayed names."""
    wide = by_year.pivot(index="year", columns="group", values=column)
    return wide[list(GROUPS)].rename(columns={g: f"share_usable_{g}" for g in GROUPS})


def share_tested_by_year(counts: pd.DataFrame, column: str) -> pd.Series:
    """Usable names in the tested set over index members, summed over the months of each year (all names only)."""
    years = pd.to_datetime(counts["date"]).dt.year.astype(int)
    totals = counts.groupby(years)[[column, "universe_size"]].sum()
    return (totals[column] / totals["universe_size"]).rename("share_usable_tested").rename_axis("year")


def share_failures(coverage_monthly: pd.DataFrame, by_year: pd.DataFrame, tolerance: float = 1e-9) -> list[str]:
    """
    The 'all' shares of the yearly file against the monthly coverage file,
    over reliable months, and removed plus stayed member-months against all.
    """
    reliable = coverage_monthly[coverage_monthly["reliable"] == 1]
    totals = reliable.groupby(reliable["month"].str[:4].astype(int)).sum(numeric_only=True)
    rows = by_year.set_index(["year", "group"])
    failures = []
    for year in totals.index:
        for column, count in (("share_usable_momentum", "usable_momentum"),
                              ("share_usable_value_combined", "usable_value_combined")):
            found = totals.loc[year, count] / totals.loc[year, "members"]
            expected = rows.loc[(year, "all"), column]
            if _differs(found, expected, tolerance):
                failures.append(f"{year} {column}: monthly file gives {found!r}, yearly file {expected!r}")
        parts = rows.loc[(year, "removed"), "member_months"] + rows.loc[(year, "stayed"), "member_months"]
        if parts != rows.loc[(year, "all"), "member_months"]:
            failures.append(f"{year}: removed plus stayed member-months {parts}, all {rows.loc[(year, 'all'), 'member_months']}")
    return failures


# ---------------------------------------------------------------------------
# Rank IC
# ---------------------------------------------------------------------------

def yearly_mean_ic(ic_monthly: pd.DataFrame, signal: str) -> pd.DataFrame:
    """Calendar months, months with an IC and the mean IC, by year, for one signal of a monthly IC file."""
    rows = ic_monthly[ic_monthly["signal"] == signal]
    values = pd.Series(rows["rank_ic"].values, index=pd.to_datetime(rows["date"]))
    grouped = values.groupby(values.index.year.astype(int))
    return pd.DataFrame({"months": grouped.size(), "ic_months": grouped.count(),
                         "mean_rank_ic": grouped.mean()}).rename_axis("year")


def period_ic_failures(ic_monthly: pd.DataFrame, saved_summary: pd.DataFrame, signal: str, periods: dict,
                       tolerance: float = 1e-9) -> list[str]:
    """Mean and months of the monthly IC file in each period against the saved rank_ic summary row."""
    rows = ic_monthly[ic_monthly["signal"] == signal]
    values = pd.Series(rows["rank_ic"].values, index=pd.to_datetime(rows["date"]))
    saved = saved_summary[(saved_summary["test"] == "rank_ic") & (saved_summary["signal"] == signal)].set_index("period")
    failures = []
    for period, dates in periods.items():
        used = values.reindex(dates).dropna()
        if period not in saved.index:
            failures.append(f"{signal} {period}: no saved rank_ic row")
            continue
        if len(used) != saved.loc[period, "months"] or _differs(used.mean(), saved.loc[period, "mean"], tolerance):
            failures.append(f"{signal} {period}: {len(used)} months, mean {used.mean()!r}; saved "
                            f"{saved.loc[period, 'months']} months, mean {saved.loc[period, 'mean']!r}")
    return failures


# ---------------------------------------------------------------------------
# Top-decile Sharpe, gross, Treasury bill rate
# ---------------------------------------------------------------------------

def strategy_and_benchmark(returns_long: pd.DataFrame, signal: str) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Gross top-decile returns, gross benchmark returns and the T-bill rate, by date, from the saved returns file."""
    dated = returns_long.assign(date=pd.to_datetime(returns_long["date"]))
    strategy = dated[(dated["strategy"] == signal) & (dated["size"] == TOP_DECILE)].set_index("date").sort_index()
    benchmark = dated[dated["strategy"] == BENCHMARK[signal]].set_index("date").sort_index()
    return strategy[GROSS], benchmark[GROSS].reindex(strategy.index), strategy["rf_monthly"]


def yearly_sharpe(strategy: pd.Series, benchmark: pd.Series, rf_monthly: pd.Series,
                  n_sims: int = 5000, seed: int = 42, ci: float = 0.90) -> pd.DataFrame:
    """Levels and the paired Sharpe difference with its bootstrap interval, one row per calendar year."""
    rows = {}
    for year in sorted(set(strategy.index.year)):
        s, b = strategy[strategy.index.year == year], benchmark[benchmark.index.year == year]
        rf = rf_monthly[rf_monthly.index.year == year]
        test = bootstrap_sharpe_diff_tbill(s, b, rf, n_sims=n_sims, ci=ci, seed=seed)
        rows[year] = {
            "top_decile_months": len(s),
            "top_decile_annualized_return": annualized_return(s),
            "benchmark_annualized_return": annualized_return(b),
            "top_decile_sharpe_tbill": sharpe_ratio_tbill(s, rf),
            "benchmark_sharpe_tbill": sharpe_ratio_tbill(b, rf),
            "sharpe_diff_tbill": test["point_diff"],
            "ci_90_lower_tbill": test["lower"],
            "ci_90_upper_tbill": test["upper"],
            "interval_excludes_zero": test["significant"],
        }
    return pd.DataFrame.from_dict(rows, orient="index").rename_axis("year")


def period_sharpe_failures(returns_long: pd.DataFrame, saved_summary: pd.DataFrame, signal: str, periods: dict,
                           tolerance: float = 1e-9) -> list[str]:
    """Point estimates from the saved returns against the saved gross top-decile rows. No bootstrap."""
    strategy, benchmark, rf = strategy_and_benchmark(returns_long, signal)
    saved = saved_summary[(saved_summary["strategy"] == signal) & (saved_summary["size"] == TOP_DECILE)
                          & (saved_summary["basis"] == GROSS)].set_index("period")
    failures = []
    for period, dates in periods.items():
        if period not in saved.index:
            failures.append(f"{signal} {period}: no saved gross top-decile row")
            continue
        s, b, r = strategy.loc[dates], benchmark.loc[dates], rf.loc[dates]
        found = {"months": len(s), "sharpe_tbill": sharpe_ratio_tbill(s, r),
                 "benchmark_sharpe_tbill": sharpe_ratio_tbill(b, r)}
        found["sharpe_diff_tbill"] = found["sharpe_tbill"] - found["benchmark_sharpe_tbill"]
        for column, value in found.items():
            if _differs(value, saved.loc[period, column], tolerance):
                failures.append(f"{signal} {period}: {column} {value!r}, saved {saved.loc[period, column]!r}")
    return failures


# ---------------------------------------------------------------------------
# Registered survivorship diagnostic (Amendment 13, decision 8), reproduced as context
# ---------------------------------------------------------------------------

DIAGNOSTIC_KEYS = ["period", "universe_set", "group"]
DIAGNOSTIC_VALUES = ["months", "months_empty", "names_per_month_avg", "mean_monthly_return", "annualised_mean"]


def diagnostic_failures(found: pd.DataFrame, saved: pd.DataFrame, tolerance: float = 1e-9) -> list[str]:
    """A recomputed survivorship diagnostic against the saved file, row by row. NaN matches NaN."""
    found, saved = found.set_index(DIAGNOSTIC_KEYS), saved.set_index(DIAGNOSTIC_KEYS)
    failures = [f"{key}: in only one of the recomputed and the saved diagnostic"
                for key in found.index.symmetric_difference(saved.index)]
    for key in found.index.intersection(saved.index):
        for column in DIAGNOSTIC_VALUES:
            if _differs(found.loc[key, column], saved.loc[key, column], tolerance):
                failures.append(f"{key}: {column} {found.loc[key, column]!r}, saved {saved.loc[key, column]!r}")
    return failures


# ---------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------

def survivorship_by_year_table(by_year: pd.DataFrame, tested: dict, ic_monthly: dict, returns_long: pd.DataFrame,
                               n_sims: int = 5000, seed: int = 42) -> pd.DataFrame:
    """
    One row per year and registered signal. tested maps each signal to its
    yearly tested share (share_tested_by_year()), and ic_monthly each signal to the
    monthly IC file that holds it.
    """
    parts = []
    for signal in SIGNALS:
        strategy, benchmark, rf = strategy_and_benchmark(returns_long, signal)
        frame = (yearly_shares(by_year, SHARE_COLUMN[signal])
                 .join(tested[signal])
                 .join(yearly_mean_ic(ic_monthly[signal], signal))
                 .join(yearly_sharpe(strategy, benchmark, rf, n_sims=n_sims, seed=seed)))
        frame = frame.reset_index().assign(signal=signal, universe_set=UNIVERSE_SET[signal],
                                           benchmark=BENCHMARK[signal], basis=GROSS, universe_note=BY_YEAR_NOTE)
        frame["partial_year"] = frame["months"] < FULL_YEAR
        parts.append(frame[TABLE_COLUMNS])
    return pd.concat(parts, ignore_index=True)


def yearly_total_failures(table: pd.DataFrame, saved_signal_summary: pd.DataFrame,
                          saved_portfolio_summary: pd.DataFrame, full_period: str) -> list[str]:
    """For each signal, yearly IC months and top-decile months add up to the saved full-period months."""
    failures = []
    for signal, rows in table.groupby("signal"):
        ic = saved_signal_summary[(saved_signal_summary["test"] == "rank_ic") & (saved_signal_summary["signal"] == signal)
                                  & (saved_signal_summary["period"] == full_period)]["months"]
        port = saved_portfolio_summary[(saved_portfolio_summary["strategy"] == signal)
                                       & (saved_portfolio_summary["size"] == TOP_DECILE)
                                       & (saved_portfolio_summary["basis"] == GROSS)
                                       & (saved_portfolio_summary["period"] == full_period)]["months"]
        for label, total, saved in (("IC", rows["ic_months"].sum(), ic), ("top-decile", rows["top_decile_months"].sum(), port)):
            if len(saved) != 1 or int(total) != int(saved.iloc[0]):
                failures.append(f"{signal}: yearly {label} months add up to {total}, saved full period {list(saved)}")
    return failures
