"""
Helpers for the Phase 3 data feasibility check (LIMITATIONS_PLAN.md, Phase 3
detailed design and Amendment 6).

Nothing in this module computes a return, a signal value or a performance
figure. Prices enter only as dates, to record whether a month-end price
exists, and book value enters only as "available or not" at a month end.
"""
import gzip
import json
import os
import re
import time
from io import StringIO
from pathlib import Path

import pandas as pd

FEASIBILITY_DB_PATH = "database/universe_feasibility.db"
EXISTING_DB_PATH = "database/quant_research.db"
SQL_DIR = Path(__file__).resolve().parent.parent / "sql"

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
WIKIPEDIA_CHANGES_URL = "https://en.wikipedia.org/wiki/Historical_components_of_the_S%26P_500"
PRICE_START = "2011-01-01"
PRICE_END = "2026-09-01"  # yfinance end date is exclusive, so this fetches through 31 Aug 2026
FIRST_PRICE_MONTH = "2011-01"  # t-12 for the first evaluation month
EVALUATION_START = "2012-01"
EVALUATION_END = "2026-08"
GATE1_START = "2021-01"
MEMBERS_MIN = 480
MEMBERS_MAX = 520
SEC_MAX_REQUESTS_PER_SECOND = 8
MAX_RETRIES = 3


def cache_dir() -> Path:
    """Raw-download cache folder: UNIVERSE_CACHE_DIR if set, else data_cache/ (gitignored)."""
    return Path(os.environ.get("UNIVERSE_CACHE_DIR", "data_cache"))


# ---------------------------------------------------------------------------
# Months
# ---------------------------------------------------------------------------

def month_range(start: str, end: str) -> list[str]:
    """Calendar months from start to end inclusive, as 'YYYY-MM' strings."""
    return [str(p) for p in pd.period_range(start, end, freq="M")]


def shift_month(month: str, k: int) -> str:
    """Month k months after `month` (k may be negative)."""
    return str(pd.Period(month, freq="M") + k)


def calendar_month_end(month: str) -> pd.Timestamp:
    """Calendar last day of the month at midnight, the same dates as resample('ME')."""
    return pd.Period(month, freq="M").to_timestamp(how="end").normalize()


def evaluation_months_frame(start: str = EVALUATION_START, end: str = EVALUATION_END) -> pd.DataFrame:
    """
    One row per evaluation month t, with the months whose data decide
    usability: t-1 (universe date, price and book value), t-12 (momentum
    warm-up price) and t itself (return observable).

    The universe in month t is the membership on the calendar end of t-1,
    so a stock added during month t is not in month t's universe.
    """
    rows = []
    for month in month_range(start, end):
        month_t1 = shift_month(month, -1)
        rows.append({
            "month": month,
            "month_t1": month_t1,
            "month_t12": shift_month(month, -12),
            "universe_date": calendar_month_end(month_t1).strftime("%Y-%m-%d"),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Membership (Wikipedia current list walked backwards through the changes)
# ---------------------------------------------------------------------------

def clean_cell(value) -> str | None:
    """Strip footnote markers like [3] and surrounding whitespace; empty becomes None."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    text = re.sub(r"\[[^\]]*\]", "", str(value)).strip()
    return text or None


def normalize_ticker(value) -> str | None:
    """
    Wikipedia writes share classes as BRK.B; yfinance and the SEC file use BRK-B.
    A few cells of the changes table carry a stray trailing "|" (for example
    "ALLE |"), which is dropped.
    """
    text = clean_cell(value)
    if text:
        text = text.split("|")[0].strip()
    return text.upper().replace(".", "-") if text else None


def _text(value) -> str | None:
    """The value if it is a non-empty string, else None (pandas stores a missing string as NaN, which is truthy)."""
    return value if isinstance(value, str) and value else None


def _find_column(columns, *parts: str):
    """The single column whose lower-cased name contains every part."""
    matches = [c for c in columns if all(p in str(c).lower() for p in parts)]
    if len(matches) != 1:
        raise ValueError(f"expected one column containing {parts}, found {matches} in {list(columns)}")
    return matches[0]


def parse_constituents(html: str) -> pd.DataFrame:
    """Current constituents table (id='constituents'): ticker, company, gics_sector."""
    table = pd.read_html(StringIO(html), attrs={"id": "constituents"})[0]
    return pd.DataFrame({
        "ticker": table[_find_column(table.columns, "symbol")].map(normalize_ticker),
        "company": table[_find_column(table.columns, "security")].map(clean_cell),
        "gics_sector": table[_find_column(table.columns, "gics sector")].map(clean_cell),
    })


def parse_changes(html: str) -> pd.DataFrame:
    """
    Table of changes (id='changes'): one row per listed change with the
    effective date, the added and removed ticker and name, and source_row,
    the 1-based position of the row in the Wikipedia table.

    Dates that cannot be parsed are kept as NaT, so the rebuild can count
    them instead of dropping them silently.
    """
    table = pd.read_html(StringIO(html), attrs={"id": "changes"})[0]
    if not isinstance(table.columns, pd.MultiIndex):
        raise ValueError(f"changes table has no two-row header: {list(table.columns)}")
    table.columns = [" | ".join(str(level) for level in col) for col in table.columns]
    raw_dates = table[_find_column(table.columns, "date")].map(clean_cell)
    return pd.DataFrame({
        "date": pd.to_datetime(raw_dates, format="%B %d, %Y", errors="coerce"),
        "raw_date": raw_dates,
        "added_ticker": table[_find_column(table.columns, "added", "ticker")].map(normalize_ticker),
        "added_name": table[_find_column(table.columns, "added", "security")].map(clean_cell),
        "removed_ticker": table[_find_column(table.columns, "removed", "ticker")].map(normalize_ticker),
        "removed_name": table[_find_column(table.columns, "removed", "security")].map(clean_cell),
        "source_row": range(1, len(table) + 1),
    })


def rebuild_membership(current: pd.DataFrame, changes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Rebuild membership intervals by walking the current list backwards
    through the changes (Amendment 6, item 3).

    Going back in time, an addition dated d closes an open interval with
    start_date = d, and a removal dated d opens an interval with
    end_date = d minus one day (the last day as a member). Names still open
    at the end get start_date None (member before the recorded history).
    Inconsistent rows are counted and returned, never repaired.

    Returns
    -------
    (intervals, problems)
        intervals: ticker, company, gics_sector, start_date, end_date
        (ISO strings or None), source_row.
        problems: source_row, date, ticker, problem.
    """
    open_members = {
        row.ticker: {"end_date": None, "end_source": "current list", "company": row.company}
        for row in current.itertuples()
    }
    intervals, problems = [], []

    ordered = changes.sort_values(["date", "source_row"], ascending=[False, True], na_position="first")
    for row in ordered.itertuples():
        added, removed = _text(row.added_ticker), _text(row.removed_ticker)
        if pd.isna(row.date):
            if added or removed:
                problems.append({"source_row": row.source_row, "date": row.raw_date,
                                 "ticker": added or removed, "problem": "unparseable date"})
            continue
        date = row.date.strftime("%Y-%m-%d")

        if added:
            member = open_members.pop(added, None)
            if member is None:
                problems.append({"source_row": row.source_row, "date": date, "ticker": added,
                                 "problem": "added ticker is not a member after this date"})
            else:
                intervals.append({
                    "ticker": added,
                    "company": _text(member["company"]) or _text(row.added_name),
                    "start_date": date,
                    "end_date": member["end_date"],
                    "source_row": f"start: changes row {row.source_row}; end: {member['end_source']}",
                })

        if removed:
            if removed in open_members:
                problems.append({"source_row": row.source_row, "date": date, "ticker": removed,
                                 "problem": "removed ticker is still a member after this date"})
            else:
                open_members[removed] = {
                    "end_date": (row.date - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                    "end_source": f"changes row {row.source_row}",
                    "company": _text(row.removed_name),
                }

    for ticker, member in open_members.items():
        intervals.append({
            "ticker": ticker,
            "company": member["company"],
            "start_date": None,
            "end_date": member["end_date"],
            "source_row": f"start: before recorded history; end: {member['end_source']}",
        })

    sectors = dict(zip(current["ticker"], current["gics_sector"]))
    result = pd.DataFrame(intervals, columns=["ticker", "company", "start_date", "end_date", "source_row"])
    result.insert(2, "gics_sector", result["ticker"].map(sectors))
    result = result.sort_values(["ticker", "start_date"], na_position="first").reset_index(drop=True)
    problem_frame = pd.DataFrame(problems, columns=["source_row", "date", "ticker", "problem"])
    return result, problem_frame


def is_member(intervals: pd.DataFrame, ticker: str, date: str) -> bool:
    """True if ticker is a member at the close of `date` (ISO), the same rule as sql/universe_at_date.sql."""
    rows = intervals[intervals["ticker"] == ticker]
    starts_ok = rows["start_date"].isna() | (rows["start_date"] <= date)
    ends_ok = rows["end_date"].isna() | (rows["end_date"] >= date)
    return bool((starts_ok & ends_ok).any())


def member_months(intervals: pd.DataFrame, ticker: str, months: list[str]) -> list[str]:
    """Months whose calendar month end falls inside one of the ticker's intervals."""
    rows = intervals[intervals["ticker"] == ticker]
    windows = [(_text(r.start_date) or "0000-00-00", _text(r.end_date) or "9999-99-99") for r in rows.itertuples()]
    month_ends = [(m, calendar_month_end(m).strftime("%Y-%m-%d")) for m in months]
    return [m for m, day in month_ends if any(start <= day <= end for start, end in windows)]


def tickers_in_window(intervals: pd.DataFrame, months: list[str]) -> list[str]:
    """Tickers that are members at the end of at least one of the months (the download list)."""
    return sorted(t for t in intervals["ticker"].unique() if member_months(intervals, t, months))


def format_intervals(intervals: pd.DataFrame, ticker: str) -> str:
    """Human-readable membership dates, e.g. '2016-09-30 to 2020-06-14; before history to current'."""
    rows = intervals[intervals["ticker"] == ticker]
    return "; ".join(
        f"{_text(r.start_date) or 'before history'} to {_text(r.end_date) or 'current'}" for r in rows.itertuples()
    )


# ---------------------------------------------------------------------------
# Prices: only dates are used, to decide whether a month-end price exists
# ---------------------------------------------------------------------------

def trading_calendar(price_dates: dict, months: list[str]) -> pd.Series:
    """
    Last trading day of each month (Amendment 6, item 1): the last date in
    the month on which at least half of the downloaded tickers have a price.
    "Downloaded tickers" are those with a non-empty download.

    Returns a Series indexed by month; NaT where no date qualifies.
    """
    n_tickers = len(price_dates)
    all_dates = pd.concat([pd.Series(pd.DatetimeIndex(d).unique()) for d in price_dates.values()])
    counts = all_dates.value_counts()
    qualifying = pd.DatetimeIndex(counts[counts >= n_tickers / 2].index).sort_values()
    last_by_month = pd.Series(qualifying, index=qualifying.strftime("%Y-%m")).groupby(level=0).max()
    return last_by_month.reindex(months)


def months_with_price(dates, calendar: pd.Series) -> list[str]:
    """Months whose last trading day is among the ticker's price dates."""
    date_set = set(pd.DatetimeIndex(dates))
    return [m for m, day in calendar.dropna().items() if day in date_set]


def price_window_flags(present: set, months_member: list[str]) -> dict:
    """
    Compare month-end price availability with the months the ticker was a
    member, to catch ticker reuse and ticker changes: history that starts
    after the membership start, ends before the membership end, or has a
    gap inside.
    """
    has_price = [m in present for m in months_member]
    n_present = sum(has_price)
    flags = {"member_months": len(months_member), "months_with_price": n_present,
             "starts_late": False, "ends_early": False, "gap_inside": False}
    if n_present == 0:
        return flags
    first = has_price.index(True)
    last = len(has_price) - 1 - has_price[::-1].index(True)
    flags["starts_late"] = first > 0
    flags["ends_early"] = last < len(has_price) - 1
    flags["gap_inside"] = not all(has_price[first:last + 1])
    return flags


# ---------------------------------------------------------------------------
# Book value: the existing rule in src/fundamentals.py, read as available or not
# ---------------------------------------------------------------------------

def book_value_months(bv_df: pd.DataFrame, months: list[str], forward_fill) -> list[str]:
    """
    Months whose calendar month end has a book value under the existing
    forward_fill_book_value rule (passed in, not re-implemented): filed on or
    before the month end and at most 180 days old.
    """
    target_dates = [calendar_month_end(m) for m in months]
    filled = forward_fill(bv_df, target_dates)
    present = filled.dropna(subset=["book_value_per_share"])
    return [pd.Timestamp(d).strftime("%Y-%m") for d in present["date"]]


def make_cached_company_facts(get_cik, facts_dir: Path):
    """
    Drop-in replacement for fundamentals.get_company_facts(ticker) that reads
    only the cache. A confirmed-empty marker (SEC 404) gives {}, which the
    existing extract_concept treats as "no data". A missing cache entry
    raises, so an undownloaded company is never mistaken for one with no data.
    """
    def get_company_facts(ticker: str) -> dict:
        cik = get_cik(ticker)
        path = Path(facts_dir) / f"CIK{cik}.json.gz"
        if path.exists():
            return read_gzip_json(path)
        if (Path(facts_dir) / f"CIK{cik}.empty.json").exists():
            return {}
        raise FileNotFoundError(f"no cached company facts for {ticker} (CIK {cik})")
    return get_company_facts


# ---------------------------------------------------------------------------
# Downloads: retries, confirmed-empty rule, throttling, cache files
# ---------------------------------------------------------------------------

def download_with_retries(fetch, is_missing, missing_confirmations: int,
                          max_retries: int = MAX_RETRIES, backoff_seconds=(2, 8, 30), sleep=time.sleep):
    """
    Call fetch() up to 1 + max_retries times (Amendment 6, item 5).

    A "missing data" exception (is_missing(exc) is True) confirms an empty
    result only once it has been seen on `missing_confirmations` separate
    attempts (2 for yfinance, 1 for an SEC 404). Any other exception is an
    error and is retried with backoff. If the attempts run out, the status
    is "error", which is never counted as missing data.

    Returns
    -------
    (status, result, attempts, message) with status "ok", "empty" or "error".
    """
    missing_seen = 0
    message = ""
    for attempt in range(1, max_retries + 2):
        try:
            result = fetch()
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            if is_missing(exc):
                missing_seen += 1
                if missing_seen >= missing_confirmations:
                    return "empty", None, attempt, message
        else:
            return "ok", result, attempt, ""
        if attempt <= max_retries:
            sleep(backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)])
    return "error", None, max_retries + 1, message


class RateLimiter:
    """Spaces request starts at least 1/max_per_second seconds apart."""

    def __init__(self, max_per_second: float, clock=time.monotonic, sleep=time.sleep):
        self.min_interval = 1.0 / max_per_second
        self.clock = clock
        self.sleep = sleep
        self.last_start = None

    def wait(self):
        if self.last_start is not None:
            delay = self.last_start + self.min_interval - self.clock()
            if delay > 0:
                self.sleep(delay)
        self.last_start = self.clock()


def write_bytes_atomic(path: Path, data: bytes):
    """Write via a temporary file and rename, so an interrupted run never leaves a half-written cache file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def write_gzip_json(path: Path, obj):
    write_bytes_atomic(path, gzip.compress(json.dumps(obj).encode("utf-8")))


def read_gzip_json(path: Path):
    return json.loads(gzip.decompress(Path(path).read_bytes()).decode("utf-8"))


def write_json(path: Path, obj):
    write_bytes_atomic(path, json.dumps(obj, indent=2).encode("utf-8"))


# ---------------------------------------------------------------------------
# Feasibility database and SQL coverage
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS index_membership (
    ticker TEXT NOT NULL, company TEXT, gics_sector TEXT,
    start_date TEXT, end_date TEXT, source_row TEXT
);
CREATE TABLE IF NOT EXISTS price_month_end (
    ticker TEXT NOT NULL, month TEXT NOT NULL, PRIMARY KEY (ticker, month)
);
CREATE TABLE IF NOT EXISTS book_value_month_end (
    ticker TEXT NOT NULL, month TEXT NOT NULL, PRIMARY KEY (ticker, month)
);
CREATE TABLE IF NOT EXISTS ticker_cik (
    ticker TEXT PRIMARY KEY, cik TEXT
);
CREATE TABLE IF NOT EXISTS trading_calendar (
    month TEXT PRIMARY KEY, last_trading_day TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS download_status (
    source TEXT NOT NULL, key TEXT NOT NULL, status TEXT NOT NULL,
    attempts INTEGER, message TEXT, PRIMARY KEY (source, key)
);
CREATE TABLE IF NOT EXISTS evaluation_months (
    month TEXT PRIMARY KEY, month_t1 TEXT NOT NULL, month_t12 TEXT NOT NULL,
    universe_date TEXT NOT NULL, reliable INTEGER
);
CREATE TABLE IF NOT EXISTS ticker_group (
    ticker TEXT PRIMARY KEY, survivor_group TEXT NOT NULL, sector_group TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS member_month_flags (
    month TEXT NOT NULL, ticker TEXT NOT NULL,
    has_price_t1 INTEGER NOT NULL, has_signal_inputs INTEGER NOT NULL,
    has_cik INTEGER NOT NULL, has_book_value INTEGER NOT NULL, has_price_t INTEGER NOT NULL,
    PRIMARY KEY (month, ticker)
);
"""


def create_feasibility_tables(conn):
    conn.executescript(SCHEMA)


def load_named_queries(path: Path) -> dict:
    """Split a .sql file into queries headed by '-- name: <name>' lines."""
    queries, name, lines = {}, None, []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        match = re.match(r"--\s*name:\s*(\w+)", line)
        if match:
            if name:
                queries[name] = "\n".join(lines).strip().rstrip(";")
            name, lines = match.group(1), []
        elif name:
            lines.append(line)
    if name:
        queries[name] = "\n".join(lines).strip().rstrip(";")
    return queries


def members_query() -> str:
    """The 'members at date t' query from sql/universe_at_date.sql (parameter :as_of_date)."""
    return (SQL_DIR / "universe_at_date.sql").read_text(encoding="utf-8").strip().rstrip(";")


def build_member_month_flags(conn):
    """
    For every evaluation month, load the members at the universe date with
    sql/universe_at_date.sql and join them to the availability tables
    (sql/universe_coverage.sql), one row per member and month.
    """
    queries = load_named_queries(SQL_DIR / "universe_coverage.sql")
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS members (ticker TEXT PRIMARY KEY)")
    conn.execute("DELETE FROM member_month_flags")
    months = conn.execute(
        "SELECT month, month_t1, month_t12, universe_date FROM evaluation_months ORDER BY month"
    ).fetchall()
    for month, month_t1, month_t12, universe_date in months:
        conn.execute("DELETE FROM temp.members")
        conn.execute("INSERT INTO temp.members " + members_query(), {"as_of_date": universe_date})
        conn.execute(queries["insert_member_month_flags"],
                     {"month": month, "month_t1": month_t1, "month_t12": month_t12})
    conn.execute("DROP VIEW IF EXISTS member_month_usability")
    conn.execute(queries["create_usability_view"])
    conn.commit()


def coverage_query(conn, name: str, params: dict | None = None) -> pd.DataFrame:
    """Run one named query from sql/universe_coverage.sql."""
    queries = load_named_queries(SQL_DIR / "universe_coverage.sql")
    return pd.read_sql_query(queries[name], conn, params=params or {})


def mark_reliable_months(conn, members_min: int = MEMBERS_MIN, members_max: int = MEMBERS_MAX):
    """Gate 3: a month is reliable if its member count is within [members_min, members_max]."""
    queries = load_named_queries(SQL_DIR / "universe_coverage.sql")
    conn.execute(queries["mark_reliable_months"], {"members_min": members_min, "members_max": members_max})
    conn.commit()


COUNT_COLUMNS = [
    "members", "with_price_t1", "with_signal_inputs", "with_cik", "with_book_value",
    "usable_momentum", "usable_value_combined", "delisting_gap_momentum", "delisting_gap_value_combined",
    "members_no_price_t1", "members_no_signal_inputs",
]


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else float("nan")


def summarize_by_year(counts: pd.DataFrame, reliability: pd.Series) -> pd.DataFrame:
    """
    Yearly averages of the monthly counts per group, over reliable months
    only (Amendment 6, item 4).

    Parameters
    ----------
    counts : one row per (month, group) with COUNT_COLUMNS; a group with no
        members in a month may be absent (it counts as zero).
    reliability : Series indexed by month ('YYYY-MM'), 1 if reliable else 0.

    Each avg_ column is the yearly sum divided by the number of reliable
    months. Shares are member-month weighted: usable and missing-data shares
    over members, delisting-gap shares over the usable names of that kind.
    """
    years = sorted({m[:4] for m in reliability.index})
    rows = []
    for group in sorted(counts["group"].unique()):
        for year in years:
            in_year = reliability[[m.startswith(year) for m in reliability.index]]
            reliable_months = list(in_year[in_year == 1].index)
            subset = counts[(counts["group"] == group) & counts["month"].isin(reliable_months)]
            totals = subset[COUNT_COLUMNS].sum()
            n = len(reliable_months)
            row = {"year": int(year), "group": group, "months_reliable": n,
                   "months_unreliable": int((in_year != 1).sum()), "member_months": int(totals["members"])}
            row.update({f"avg_{c}": _ratio(totals[c], n) for c in COUNT_COLUMNS})
            row.update({
                "share_usable_momentum": _ratio(totals["usable_momentum"], totals["members"]),
                "share_usable_value_combined": _ratio(totals["usable_value_combined"], totals["members"]),
                "share_no_price_t1": _ratio(totals["members_no_price_t1"], totals["members"]),
                "share_no_signal_inputs": _ratio(totals["members_no_signal_inputs"], totals["members"]),
                "delisting_gap_share_momentum": _ratio(totals["delisting_gap_momentum"],
                                                       totals["usable_momentum"]),
                "delisting_gap_share_value_combined": _ratio(totals["delisting_gap_value_combined"],
                                                             totals["usable_value_combined"]),
            })
            rows.append(row)
    return pd.DataFrame(rows)


def survivor_group(intervals: pd.DataFrame, ticker: str, window_end: str = "2026-08-31") -> str:
    """'removed' if any interval ends before window_end (including names added again later), else 'stayed'."""
    ends = intervals.loc[intervals["ticker"] == ticker, "end_date"].dropna()
    return "removed" if (ends < window_end).any() else "stayed"


# ---------------------------------------------------------------------------
# Validation gates and audit rows
# ---------------------------------------------------------------------------

def gate1_failures(intervals: pd.DataFrame, tickers: list[str], months: list[str]) -> dict:
    """
    Gate 1 (Amendment 6, item 4): each study ticker must be a member in the
    universe of every month t in `months` (membership at the calendar end
    of t-1). Returns {ticker: [months where it is not]} for failures only.
    """
    failures = {}
    for ticker in tickers:
        missing = [m for m in months
                   if not is_member(intervals, ticker,
                                    calendar_month_end(shift_month(m, -1)).strftime("%Y-%m-%d"))]
        if missing:
            failures[ticker] = missing
    return failures


def availability_mismatches(new: set, existing: set, tickers: list[str], months: list[str]) -> list[dict]:
    """
    Gate 2: compare (ticker, month) availability from the new stage with the
    existing tables over the overlap, month by month.
    """
    rows = []
    for ticker in tickers:
        for month in months:
            in_new, in_existing = (ticker, month) in new, (ticker, month) in existing
            if in_new != in_existing:
                rows.append({"ticker": ticker, "month": month, "new": in_new, "existing": in_existing})
    return rows


def exclusion_reasons(member_month_count: int, cik, price_status: str, price_flags: dict,
                      sec_status: str | None, book_value_member_months: int) -> list[tuple[str, str]]:
    """
    Audit reasons for one ticker (registered reasons plus 'partial book
    value', Amendment 6 item 6). Returns (reason, detail) pairs; an empty
    list means the ticker is fully covered over its member months.
    """
    reasons = []
    if price_status == "error":
        reasons.append(("persistent download error", "yfinance"))
    elif price_status == "empty" or price_flags["months_with_price"] == 0:
        reasons.append(("no prices", f"0 of {member_month_count} member months with a month-end price"))
    elif price_flags["months_with_price"] < member_month_count:
        parts = [label for key, label in (("starts_late", "starts after membership start"),
                                          ("gap_inside", "gap inside membership"),
                                          ("ends_early", "ends before membership end"))
                 if price_flags[key]]
        parts.append(f"{price_flags['months_with_price']} of {member_month_count} member months with a month-end price")
        reasons.append(("partial prices", "; ".join(parts)))

    if cik is None:
        reasons.append(("no CIK", "ticker not in the SEC ticker file"))
    elif sec_status == "error":
        reasons.append(("persistent download error", "SEC company facts"))
    elif book_value_member_months == 0:
        reasons.append(("no book value", f"0 of {member_month_count} member months with book value"))
    elif book_value_member_months < member_month_count:
        reasons.append(("partial book value",
                        f"{book_value_member_months} of {member_month_count} member months with book value"))
    return reasons
