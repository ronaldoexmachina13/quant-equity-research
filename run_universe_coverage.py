"""
Phase 3, step 4 of 4: validation gates and coverage report.

Reads database/universe_feasibility.db (filled by the three earlier steps)
and opens database/quant_research.db read only for gate 2. Monthly counts
come from joining sql/universe_at_date.sql with the availability tables
(sql/universe_coverage.sql).

Gates (LIMITATIONS_PLAN.md Phase 3 and Amendment 6, item 4):
1. each of the 17 study stocks is a member in the universe of every month
   from 2021-01 to 2026-08;
2. for those 17, month-end price and book value availability match the
   existing prices and book_value tables month by month, and V has no
   book value;
3. months with fewer than 480 or more than 520 members are flagged
   unreliable (reliable = 0) and the run continues.
If gate 1 or 2 fails, the script reports and writes nothing to results/.

Outputs (never overwritten: if any exists, the script stops before doing
anything): results/universe_membership.csv, universe_coverage_monthly.csv,
universe_coverage_by_year.csv, universe_coverage_by_sector.csv,
universe_exclusions.csv. This script reports numbers only; it applies no
decision rule.
"""
import sqlite3
from pathlib import Path

import pandas as pd

from config import UNIVERSE
from src.universe import (
    FEASIBILITY_DB_PATH, EXISTING_DB_PATH, FIRST_PRICE_MONTH, EVALUATION_END, GATE1_START,
    COUNT_COLUMNS, month_range, evaluation_months_frame, tickers_in_window, member_months,
    format_intervals, price_window_flags, gate1_failures, availability_mismatches, exclusion_reasons,
    summarize_by_year, survivor_group, create_feasibility_tables, build_member_month_flags,
    mark_reliable_months, coverage_query,
)

OUTPUTS = {name: Path("results") / f"{name}.csv" for name in [
    "universe_membership", "universe_coverage_monthly", "universe_coverage_by_year",
    "universe_coverage_by_sector", "universe_exclusions",
]}


def stop_if_outputs_exist():
    existing = [str(p) for p in OUTPUTS.values() if p.exists()]
    if existing:
        raise SystemExit(f"Output files already exist and are never overwritten: {existing}. Stopping.")


def check_inputs(conn):
    for table in ["index_membership", "price_month_end", "trading_calendar", "ticker_cik"]:
        if conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0:
            raise SystemExit(f"Table {table} is empty; run the earlier Phase 3 steps first.")
    status = pd.read_sql_query(
        "SELECT source, status, COUNT(*) AS n FROM download_status GROUP BY source, status ORDER BY source, status",
        conn)
    print("Download status:\n" + status.to_string(index=False))


def fill_month_and_group_tables(conn, intervals: pd.DataFrame):
    conn.execute("DELETE FROM evaluation_months")
    evaluation_months_frame().to_sql("evaluation_months", conn, if_exists="append", index=False)
    conn.execute("DELETE FROM ticker_group")
    sectors = intervals.groupby("ticker")["gics_sector"].first()
    rows = [(t, survivor_group(intervals, t), sectors[t] if pd.notna(sectors[t]) else "unknown")
            for t in sorted(intervals["ticker"].unique())]
    conn.executemany("INSERT INTO ticker_group VALUES (?, ?, ?)", rows)
    conn.commit()


def run_gate1(intervals: pd.DataFrame) -> bool:
    print(f"\nGate 1: the {len(UNIVERSE)} study stocks, membership intervals")
    for ticker in UNIVERSE:
        print(f"  {ticker:5s} {format_intervals(intervals, ticker) or 'NOT FOUND'}")
    failures = gate1_failures(intervals, UNIVERSE, month_range(GATE1_START, EVALUATION_END))
    for ticker, missing in failures.items():
        print(f"  FAIL {ticker}: not a member in {len(missing)} months ({missing[0]} to {missing[-1]})")
    print("  Gate 1: " + ("FAILED" if failures else "passed"))
    return not failures


def existing_availability(calendar: pd.Series) -> tuple[set, set, list]:
    """(price set, book value set, overlap months) from the existing database, opened read only."""
    existing = sqlite3.connect(f"file:{EXISTING_DB_PATH}?mode=ro", uri=True)
    prices = pd.read_sql_query("SELECT date, ticker FROM prices", existing)
    book = pd.read_sql_query("SELECT date, ticker FROM book_value", existing)
    existing.close()

    prices["date"] = pd.to_datetime(prices["date"]).dt.normalize()
    overlap = [m for m in calendar.index
               if prices["date"].min().strftime("%Y-%m") <= m <= prices["date"].max().strftime("%Y-%m")]
    last_days = set(calendar[overlap])
    on_last_day = prices[prices["date"].isin(last_days)]
    price_set = {(t, d.strftime("%Y-%m")) for t, d in zip(on_last_day["ticker"], on_last_day["date"])}
    book_set = {(t, pd.Timestamp(d).strftime("%Y-%m")) for t, d in zip(book["ticker"], book["date"])}
    return price_set, book_set, overlap


def run_gate2(conn, calendar: pd.Series) -> bool:
    old_prices, old_book, overlap = existing_availability(calendar)
    new_prices = set(conn.execute("SELECT ticker, month FROM price_month_end").fetchall())
    new_book = set(conn.execute("SELECT ticker, month FROM book_value_month_end").fetchall())

    price_rows = availability_mismatches(new_prices, old_prices, UNIVERSE, overlap)
    book_rows = availability_mismatches(new_book, old_book, UNIVERSE, overlap)
    v_months = sorted(m for t, m in new_book if t == "V")

    print(f"\nGate 2: {len(UNIVERSE)} study stocks over {len(overlap)} overlap months "
          f"({overlap[0]} to {overlap[-1]})")
    print(f"  Price availability mismatches: {len(price_rows)}")
    print(f"  Book value availability mismatches: {len(book_rows)}")
    print(f"  V months with book value in the new stage: {len(v_months)}")
    for label, rows in (("price", price_rows), ("book value", book_rows)):
        if rows:
            print(f"  {label} mismatches:\n" + pd.DataFrame(rows).to_string(index=False))
    passed = not price_rows and not book_rows and not v_months
    print("  Gate 2: " + ("passed" if passed else "FAILED"))
    return passed


def build_exclusions(conn, intervals: pd.DataFrame) -> pd.DataFrame:
    months = month_range(FIRST_PRICE_MONTH, EVALUATION_END)
    price_months = pd.read_sql_query("SELECT ticker, month FROM price_month_end", conn).groupby("ticker")["month"].apply(set)
    book_months = pd.read_sql_query("SELECT ticker, month FROM book_value_month_end", conn).groupby("ticker")["month"].apply(set)
    ciks = dict(conn.execute("SELECT ticker, cik FROM ticker_cik").fetchall())
    price_status = dict(conn.execute("SELECT key, status FROM download_status WHERE source = 'yfinance'").fetchall())
    facts_status = dict(conn.execute("SELECT key, status FROM download_status WHERE source = 'sec_facts'").fetchall())
    bv_errors = {k for (k,) in conn.execute("SELECT key FROM download_status WHERE source = 'sec_book_value'")}
    company = intervals.groupby("ticker")["company"].first()

    rows = []
    for ticker in tickers_in_window(intervals, months):
        member = member_months(intervals, ticker, months)
        flags = price_window_flags(price_months.get(ticker, set()), member)
        cik = ciks.get(ticker)
        sec_status = "error" if ticker in bv_errors else facts_status.get(cik)
        bv_count = len(set(member) & book_months.get(ticker, set()))
        for reason, detail in exclusion_reasons(len(member), cik, price_status.get(ticker, "error"),
                                                flags, sec_status, bv_count):
            rows.append({"ticker": ticker, "company": company.get(ticker),
                         "membership": format_intervals(intervals, ticker), "member_months": len(member),
                         "reason": reason, "detail": detail})
    return pd.DataFrame(rows, columns=["ticker", "company", "membership", "member_months", "reason", "detail"])


def build_by_year(conn, monthly: pd.DataFrame) -> pd.DataFrame:
    by_group = coverage_query(conn, "monthly_counts_by_group").rename(columns={"survivor_group": "group"})
    all_members = monthly.assign(group="all")[["month", "group"] + COUNT_COLUMNS]
    counts = pd.concat([all_members, by_group[["month", "group"] + COUNT_COLUMNS]], ignore_index=True)
    reliability = monthly.set_index("month")["reliable"]
    return summarize_by_year(counts, reliability).sort_values(["year", "group"]).reset_index(drop=True)


def build_by_sector(conn) -> pd.DataFrame:
    sectors = coverage_query(conn, "counts_by_sector")
    for column in ["with_price_t1", "with_signal_inputs", "with_cik", "with_book_value",
                   "usable_momentum", "usable_value_combined"]:
        sectors[f"share_{column}"] = sectors[column] / sectors["member_months"]
    return sectors


if __name__ == "__main__":
    stop_if_outputs_exist()

    conn = sqlite3.connect(FEASIBILITY_DB_PATH)
    create_feasibility_tables(conn)
    check_inputs(conn)
    intervals = pd.read_sql_query("SELECT * FROM index_membership", conn)
    calendar = pd.read_sql_query("SELECT month, last_trading_day FROM trading_calendar", conn)
    calendar = pd.to_datetime(calendar.set_index("month")["last_trading_day"])

    fill_month_and_group_tables(conn, intervals)
    build_member_month_flags(conn)
    mark_reliable_months(conn)

    gate1 = run_gate1(intervals)
    gate2 = run_gate2(conn, calendar)
    if not (gate1 and gate2):
        conn.close()
        raise SystemExit("\nA validation gate failed. Nothing was written to results/. Stopping.")

    monthly = coverage_query(conn, "monthly_counts")
    unreliable = monthly[monthly["reliable"] != 1]
    print(f"\nGate 3: {len(unreliable)} of {len(monthly)} months outside the member range "
          f"(flagged reliable = 0, excluded from by-year and by-sector figures)")
    if not unreliable.empty:
        print(unreliable[["month", "members"]].to_string(index=False))

    outputs = {
        "universe_membership": intervals[["ticker", "company", "gics_sector", "start_date", "end_date", "source_row"]],
        "universe_coverage_monthly": monthly,
        "universe_coverage_by_year": build_by_year(conn, monthly),
        "universe_coverage_by_sector": build_by_sector(conn),
        "universe_exclusions": build_exclusions(conn, intervals),
    }
    conn.close()

    for name, frame in outputs.items():
        frame.to_csv(OUTPUTS[name], index=False, mode="x")
        print(f"Wrote {OUTPUTS[name]} ({len(frame)} rows)")

    reasons = outputs["universe_exclusions"]["reason"].value_counts()
    print("\nExclusion and partial-coverage reasons (rows):\n" + reasons.to_string())
    print("\nCoverage step complete. No decision rule has been applied.")
