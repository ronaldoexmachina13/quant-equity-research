"""
Rebuild of the database part of Phase 3, step 4, after database/universe_feasibility.db was lost.

database/universe_feasibility.db is gitignored and cannot be restored from Git. The three earlier Phase 3
steps (run_universe_membership.py, run_universe_prices.py, run_universe_fundamentals.py) rebuild its
tables from the cache without new downloads. This script does the remaining database work of
run_universe_coverage.py (the month, group and member-month tables, the usability view and the
reliable flag) and does NOT write anything to results/, because those files are committed and are
never overwritten.

Proof of an exact rebuild: gates 1 and 2 are rerun, and the rebuilt membership and monthly coverage
tables must equal the committed results/universe_membership.csv and results/universe_coverage_monthly.csv
text for text. Any difference stops the script with a non-zero exit code.

Run after the three Phase 3 steps, with the cache folder set:
  $env:UNIVERSE_CACHE_DIR='C:\\Dev\\quant-cache\\universe'; python rebuild_feasibility_db.py
"""
import sqlite3

import pandas as pd

from run_universe_coverage import check_inputs, fill_month_and_group_tables, run_gate1, run_gate2
from src.universe import (
    FEASIBILITY_DB_PATH, create_feasibility_tables, build_member_month_flags, mark_reliable_months, coverage_query,
)

MEMBERSHIP_COLUMNS = ["ticker", "company", "gics_sector", "start_date", "end_date", "source_row"]
COMMITTED = {"membership": "results/universe_membership.csv", "monthly": "results/universe_coverage_monthly.csv"}


def same_text(frame: pd.DataFrame, path: str) -> bool:
    """The frame written as CSV must equal the committed file, ignoring line endings."""
    rebuilt = frame.to_csv(index=False).replace("\r\n", "\n")
    with open(path, encoding="utf-8", newline="") as f:
        committed = f.read().replace("\r\n", "\n")
    return rebuilt == committed


def main():
    conn = sqlite3.connect(FEASIBILITY_DB_PATH)
    create_feasibility_tables(conn)
    check_inputs(conn)
    intervals = pd.read_sql_query("SELECT * FROM index_membership", conn)
    calendar = pd.read_sql_query("SELECT month, last_trading_day FROM trading_calendar", conn)
    calendar = pd.to_datetime(calendar.set_index("month")["last_trading_day"])

    fill_month_and_group_tables(conn, intervals)
    build_member_month_flags(conn)
    mark_reliable_months(conn)

    failures = []
    if not run_gate1(intervals):
        failures.append("gate 1 failed")
    if not run_gate2(conn, calendar):
        failures.append("gate 2 failed")

    monthly = coverage_query(conn, "monthly_counts")
    conn.close()
    for label, frame in (("membership", intervals[MEMBERSHIP_COLUMNS]), ("monthly", monthly)):
        ok = same_text(frame, COMMITTED[label])
        print(f"\nRebuilt {label} equals {COMMITTED[label]}: {'yes' if ok else 'NO'} ({len(frame)} rows)")
        if not ok:
            failures.append(f"{label} differs from the committed file")

    if failures:
        raise SystemExit("\nREBUILD NOT ACCEPTED: " + "; ".join(failures) + ". Do not use this database.")
    print("\nRebuild accepted: the database reproduces the committed Phase 3 results exactly. Nothing was written to results/.")


if __name__ == "__main__":
    main()
