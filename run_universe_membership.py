"""
Phase 3, step 1 of 4: rebuild point-in-time S&P 500 membership.

Source: the Wikipedia page "List of S&P 500 companies" (current constituents
and the table of changes), fetched once and cached. The current list is
walked backwards through the changes (LIMITATIONS_PLAN.md, Phase 3 and
Amendment 6). Writes table index_membership in
database/universe_feasibility.db. Writes nothing to results/; the
membership CSV is written by run_universe_coverage.py after the gates pass.

Rerun safe: the cached HTML is reused, and the table is rebuilt from it.
"""
import sqlite3
from datetime import datetime, timezone

import requests

from config import UNIVERSE
from src.fundamentals import HEADERS
from src.universe import (
    FEASIBILITY_DB_PATH, WIKIPEDIA_URL, FIRST_PRICE_MONTH, EVALUATION_START, EVALUATION_END,
    GATE1_START, MEMBERS_MIN, MEMBERS_MAX,
    cache_dir, month_range, evaluation_months_frame, parse_constituents, parse_changes,
    rebuild_membership, tickers_in_window, format_intervals, gate1_failures,
    download_with_retries, write_bytes_atomic, write_json, create_feasibility_tables, members_query,
)


def fetch_wikipedia_html() -> str:
    """Return the cached page, downloading it once if it is not cached yet."""
    path = cache_dir() / "wikipedia" / "list_of_sp500_companies.html"
    if path.exists():
        print(f"Using cached Wikipedia page: {path}")
        return path.read_text(encoding="utf-8")

    def fetch():
        response = requests.get(WIKIPEDIA_URL, headers=HEADERS, timeout=60)
        response.raise_for_status()
        return response.text

    status, html, attempts, message = download_with_retries(fetch, is_missing=lambda exc: False,
                                                            missing_confirmations=1)
    if status != "ok":
        raise SystemExit(f"Wikipedia download failed after {attempts} attempts: {message}")
    write_bytes_atomic(path, html.encode("utf-8"))
    write_json(path.with_suffix(".meta.json"),
               {"url": WIKIPEDIA_URL, "retrieved_utc": datetime.now(timezone.utc).isoformat()})
    print(f"Downloaded and cached Wikipedia page: {path}")
    return html


def save_membership(intervals):
    conn = sqlite3.connect(FEASIBILITY_DB_PATH)
    create_feasibility_tables(conn)
    conn.execute("DELETE FROM index_membership")
    intervals.to_sql("index_membership", conn, if_exists="append", index=False)
    conn.commit()
    conn.close()


def print_report(current, changes, intervals, problems):
    print(f"\nCurrent constituents: {len(current)}")
    print(f"Change rows: {len(changes)} ({changes['date'].isna().sum()} with an unparseable date)")
    print(f"Membership intervals: {len(intervals)} for {intervals['ticker'].nunique()} tickers")

    print(f"\nInconsistent change rows (counted, not repaired): {len(problems)}")
    if not problems.empty:
        print(problems.to_string(index=False))

    download_list = tickers_in_window(intervals, month_range(FIRST_PRICE_MONTH, EVALUATION_END))
    print(f"\nTickers with a member month-end in {FIRST_PRICE_MONTH} to {EVALUATION_END} "
          f"(download list for prices and SEC): {len(download_list)}")

    months = evaluation_months_frame()
    conn = sqlite3.connect(FEASIBILITY_DB_PATH)
    counts = [len(conn.execute(members_query(), {"as_of_date": d}).fetchall()) for d in months["universe_date"]]
    conn.close()
    outside = [(m, c) for m, c in zip(months["month"], counts) if not MEMBERS_MIN <= c <= MEMBERS_MAX]
    print(f"\nGate 3 preview: members per month range {min(counts)} to {max(counts)}; "
          f"{len(outside)} of {len(months)} months outside {MEMBERS_MIN} to {MEMBERS_MAX}")
    for month, count in outside:
        print(f"  {month}: {count}")

    print(f"\nGate 1 preview: membership intervals of the {len(UNIVERSE)} study stocks")
    for ticker in UNIVERSE:
        print(f"  {ticker:5s} {format_intervals(intervals, ticker) or 'NOT FOUND'}")
    failures = gate1_failures(intervals, UNIVERSE, month_range(GATE1_START, EVALUATION_END))
    if failures:
        print(f"  Not a member in every month {GATE1_START} to {EVALUATION_END}:")
        for ticker, missing in failures.items():
            print(f"    {ticker}: {len(missing)} months, first {missing[0]}, last {missing[-1]}")
    else:
        print(f"  All {len(UNIVERSE)} are members in every month {GATE1_START} to {EVALUATION_END}.")


if __name__ == "__main__":
    html = fetch_wikipedia_html()
    current = parse_constituents(html)
    changes = parse_changes(html)
    if current["ticker"].isna().any() or current["ticker"].duplicated().any():
        raise SystemExit("Current constituents table has blank or duplicated tickers; stopping.")

    intervals, problems = rebuild_membership(current, changes)
    save_membership(intervals)
    print_report(current, changes, intervals, problems)
    print(f"\nindex_membership written to {FEASIBILITY_DB_PATH}. Membership step complete.")
