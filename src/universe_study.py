"""
Monthly universe, Momentum signal and returns for Phase 4
(LIMITATIONS_PLAN.md, Phase 4 detailed design and Amendments 8 to 10).

This module is the Momentum path: it needs the Phase 3 price cache and the
feasibility database, and no book value or split data, so Momentum can run on
its own (Amendment 10, item 7).

Month-end prices are prices on the last trading day of the month only
(Amendment 8, reading 2). The frames passed to calculate_momentum() and
calculate_monthly_returns() hold one row per month, so a stock that stopped
trading during a month has no price for it, and so no return, instead of the
partial-month price resample("ME").last() would take from daily data.
"""
import pandas as pd

from src.backtest import run_backtest
from src.factors import calculate_momentum
from src.portfolio import build_portfolio
from src.risk import sharpe_ratio
from src.universe import EVALUATION_START, EVALUATION_END, cache_dir, shift_month

GATE1A_TOLERANCE = 1e-4        # Amendment 8: gross Sharpe against the published figure
GATE2_TOLERANCE = 1e-5         # Amendment 8: spread of the cached-to-stored price ratio
PORTFOLIO_TOP_N = 5            # frozen size of the published portfolios

NEW_TEST = "New test (2012-2020)"
RE_TEST = "Re-test (2021-2026)"
FULL_PERIOD = "Full period (2012-2026)"
NEW_TEST_END = "2020-12"

UNIVERSE_NOTE = (
    "Universe: names with available data only, affected by survivorship. The no-return count is zero in "
    "every month because delisted names have no price history at all; this must not be read as no delistings occurred."
)


def evaluation_dates(start: str = EVALUATION_START, end: str = EVALUATION_END) -> pd.DatetimeIndex:
    """Calendar month ends of the evaluation months, the dates of the signal and return rows."""
    return pd.period_range(start, end, freq="M").to_timestamp(how="end").normalize()


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def load_calendar(conn) -> pd.Series:
    """Last trading day of each month, indexed by 'YYYY-MM'."""
    rows = pd.read_sql_query("SELECT month, last_trading_day FROM trading_calendar ORDER BY month", conn)
    return pd.to_datetime(rows.set_index("month")["last_trading_day"])


def load_usability(conn) -> pd.DataFrame:
    """One row per member and month from the Phase 3 view."""
    return pd.read_sql_query(
        "SELECT month, ticker, usable_momentum, usable_value_combined, has_price_t FROM member_month_usability", conn)


def cached_tickers() -> list[str]:
    """Tickers with a cached price file. Confirmed-empty downloads have no such file."""
    return sorted(p.name.removesuffix(".csv.gz") for p in (cache_dir() / "prices").glob("*.csv.gz"))


def read_month_end_prices(calendar: pd.Series, field: str = "Adj Close", tickers: list[str] | None = None) -> pd.DataFrame:
    """
    Wide month-end prices from the cache: one row per last trading day and
    one column per ticker, NaN where the ticker has no price on that day.
    """
    dates = pd.DatetimeIndex(calendar.values, name="Date")
    columns = {}
    for ticker in (cached_tickers() if tickers is None else tickers):
        path = cache_dir() / "prices" / f"{ticker}.csv.gz"
        data = pd.read_csv(path, index_col="Date", parse_dates=True, usecols=["Date", field])
        columns[ticker] = data[field].reindex(dates)
    return pd.DataFrame(columns, index=dates)


def usable_mask(usability: pd.DataFrame, column: str, dates: pd.DatetimeIndex, tickers: list) -> pd.DataFrame:
    """True where a ticker is usable in the month, with rows dated at the calendar end of month t."""
    usable = usability[usability[column] == 1]
    month_ends = pd.PeriodIndex(usable["month"], freq="M").to_timestamp(how="end").normalize()
    marks = pd.DataFrame({"date": month_ends, "ticker": usable["ticker"].values, "usable": True})
    wide = marks.pivot(index="date", columns="ticker", values="usable")
    return wide.reindex(index=dates, columns=tickers).notna()


# ---------------------------------------------------------------------------
# Signal
# ---------------------------------------------------------------------------

def momentum_signal(prices: pd.DataFrame, usability: pd.DataFrame,
                    dates: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    """
    calculate_momentum() unchanged, on the evaluation months and restricted to
    the names usable for Momentum. The row dated t uses prices up to the end
    of t-1 and pairs with the return dated t.
    """
    dates = evaluation_dates() if dates is None else dates
    signal = calculate_momentum(prices).reindex(dates)
    return signal.where(usable_mask(usability, "usable_momentum", dates, list(signal.columns)))


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def count_mismatches(found: pd.Series, coverage: pd.DataFrame, column: str) -> pd.DataFrame:
    """
    Months where a count differs from a column of the coverage file, which is
    indexed by 'YYYY-MM' in its month column. A month present on one side only
    counts as a mismatch.
    """
    months = pd.Series(found.values, index=found.index.strftime("%Y-%m")).astype(float)
    expected = coverage.set_index("month")[column].astype(float)
    aligned = pd.DataFrame({"found": months, "expected": expected})
    return aligned[aligned["found"] != aligned["expected"]].rename_axis("month").reset_index()


def price_ratio_report(cached: pd.DataFrame, stored: pd.DataFrame) -> pd.DataFrame:
    """
    Gate 2: for each ticker, the ratio of cached to stored price over the
    dates of the stored table that are in the cached frame. `spread` is
    max / min - 1 and `level_difference` the average ratio minus 1, which is
    expected to be non-zero where dividends were adjusted between downloads.
    """
    dates = cached.index.intersection(stored.index)
    rows = []
    for ticker in cached.columns:
        ratio = cached.loc[dates, ticker] / stored.loc[dates, ticker]
        rows.append({
            "ticker": ticker,
            "months": int(ratio.notna().sum()),
            "months_missing": int(ratio.isna().sum()),
            "level_difference": ratio.mean() - 1,
            "ratio_min": ratio.min(),
            "ratio_max": ratio.max(),
            "spread": ratio.max() / ratio.min() - 1,
        })
    return pd.DataFrame(rows)


def price_ratio_failures(report: pd.DataFrame, tolerance: float = GATE2_TOLERANCE) -> list[str]:
    failures = []
    for row in report.itertuples():
        if row.months == 0 or row.months_missing > 0 or row.spread > tolerance:
            failures.append(f"{row.ticker}: spread {row.spread:.3g}, {row.months_missing} months missing")
    return failures


def top_n_returns(signal: pd.DataFrame, returns: pd.DataFrame, dates: pd.DatetimeIndex,
                  top_n: int = PORTFOLIO_TOP_N) -> tuple[pd.Series, pd.DataFrame]:
    """build_portfolio() and run_backtest() unchanged. Returns gross returns and weights on `dates`."""
    weights = build_portfolio(signal.loc[dates], top_n=top_n)
    return run_backtest(weights, returns).loc[dates], weights


def sharpe_failures(returns: dict, published: pd.DataFrame, tolerance: float = GATE1A_TOLERANCE) -> list[str]:
    """Gate 1a: flat 2% gross Sharpe of each series against the sharpe_ratio column of the published table."""
    failures = []
    for name, series in returns.items():
        recomputed, expected = sharpe_ratio(series), published.loc[name, "sharpe_ratio"]
        if not abs(recomputed - expected) <= tolerance:
            failures.append(f"{name}: recomputed {recomputed!r}, published {expected!r}")
    return failures


def holdings_differences(weights: pd.DataFrame, published: pd.DataFrame) -> list[str]:
    """Months whose holdings differ from published rows with columns date and ticker. Report only."""
    months = weights.index.strftime("%Y-%m")
    held = {m: set(row.index[row > 0]) for m, (_, row) in zip(months, weights.iterrows())}
    stored = published.groupby(pd.to_datetime(published["date"]).dt.strftime("%Y-%m"))["ticker"].apply(set).to_dict()
    return [m for m in held if held[m] != stored.get(m, set())]


# ---------------------------------------------------------------------------
# Periods
# ---------------------------------------------------------------------------

def study_periods() -> dict:
    """The registered windows as {label: dates}. No window is used to choose a specification."""
    return {
        NEW_TEST: evaluation_dates(end=NEW_TEST_END),
        RE_TEST: evaluation_dates(start=shift_month(NEW_TEST_END, 1)),
        FULL_PERIOD: evaluation_dates(),
    }


def period_labels(dates: pd.DatetimeIndex) -> pd.Series:
    """New test or re-test for each date, for the monthly files."""
    new_test_end = evaluation_dates(end=NEW_TEST_END)[-1]
    return pd.Series([NEW_TEST if d <= new_test_end else RE_TEST for d in dates], index=dates)


# ---------------------------------------------------------------------------
# Monthly output frames
# ---------------------------------------------------------------------------

def monthly_frame(dates: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame({"date": dates, "period": period_labels(dates).values})


def counts_frame(counts: pd.DataFrame, coverage: pd.DataFrame, label: str) -> pd.DataFrame:
    """Output of monthly_counts() with the universe size, and columns named after the signal group."""
    frame = monthly_frame(counts.index)
    frame["universe_size"] = coverage["members"].values
    frame[f"usable_{label}"] = counts["usable"].values
    frame[f"no_return_{label}"] = counts["no_return"].values
    return frame


def series_frame(series: pd.Series, signal: str, column: str) -> pd.DataFrame:
    """A monthly series with its period and signal name."""
    frame = monthly_frame(series.index)
    frame.insert(2, "signal", signal)
    frame[column] = series.values
    return frame
