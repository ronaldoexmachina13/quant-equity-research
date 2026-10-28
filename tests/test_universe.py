"""
Unit tests for src/universe.py (Phase 3 data feasibility check).

All inputs are small invented examples whose answers were worked out by
hand. No network, no real data. The usability tests run the real SQL files
against an in-memory SQLite database.
"""
import sqlite3

import pandas as pd
import pytest

from src.fundamentals import forward_fill_book_value
from src.universe import (
    month_range, shift_month, calendar_month_end, evaluation_months_frame,
    clean_cell, normalize_ticker, parse_constituents, parse_changes,
    rebuild_membership, is_member, member_months, tickers_in_window, format_intervals,
    trading_calendar, months_with_price, price_window_flags, book_value_months,
    make_cached_company_facts, download_with_retries, RateLimiter,
    write_gzip_json, load_named_queries, members_query,
    create_feasibility_tables, build_member_month_flags, mark_reliable_months, coverage_query,
    gate1_failures, availability_mismatches, exclusion_reasons, SQL_DIR,
    COUNT_COLUMNS, summarize_by_year, survivor_group,
)


# ---------------------------------------------------------------------------
# Months
# ---------------------------------------------------------------------------

def test_month_helpers():
    assert month_range("2020-11", "2021-02") == ["2020-11", "2020-12", "2021-01", "2021-02"]
    assert shift_month("2012-01", -12) == "2011-01"
    assert shift_month("2012-01", -1) == "2011-12"
    assert calendar_month_end("2024-02") == pd.Timestamp("2024-02-29")


def test_evaluation_months_frame_matches_registered_window():
    """2012-01 to 2026-08 is 176 months; month t uses t-1, t-12 and the calendar end of t-1."""
    frame = evaluation_months_frame()
    assert len(frame) == 176
    first = frame.iloc[0]
    assert (first["month"], first["month_t1"], first["month_t12"], first["universe_date"]) == \
        ("2012-01", "2011-12", "2011-01", "2011-12-31")
    assert frame.iloc[-1]["month"] == "2026-08"


# ---------------------------------------------------------------------------
# Parsing (hand-made HTML with the same structure as the Wikipedia tables)
# ---------------------------------------------------------------------------

CONSTITUENTS_HTML = """
<table id="constituents"><tbody>
<tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>GICS Sub-Industry</th></tr>
<tr><td>AAA</td><td>Alpha Corp</td><td>Industrials</td><td>x</td></tr>
<tr><td>BRK.B</td><td>Berkshire Hathaway[1]</td><td>Financials</td><td>x</td></tr>
</tbody></table>
"""

CHANGES_HTML = """
<table id="changes"><tbody>
<tr><th rowspan="2">Effective Date</th><th colspan="2">Added</th><th colspan="2">Removed</th><th rowspan="2">Reason</th></tr>
<tr><th>Ticker</th><th>Security</th><th>Ticker</th><th>Security</th></tr>
<tr><td>June 15, 2020</td><td>DDD</td><td>Delta Inc</td><td>XXX</td><td>Xray Co</td><td>r</td></tr>
<tr><td>March 1, 2018[4]</td><td></td><td></td><td>YYY</td><td>Yankee Co</td><td>r</td></tr>
<tr><td>sometime in 2015</td><td>QQQ</td><td>Q Co</td><td></td><td></td><td>r</td></tr>
</tbody></table>
"""


def test_clean_cell_and_normalize_ticker():
    assert clean_cell(" Alpha [12] ") == "Alpha"
    assert clean_cell(float("nan")) is None
    assert normalize_ticker("brk.b") == "BRK-B"
    assert normalize_ticker("") is None
    assert normalize_ticker("ALLE |") == "ALLE"
    assert normalize_ticker(" | ") is None


def test_parse_constituents():
    current = parse_constituents(CONSTITUENTS_HTML)
    assert list(current["ticker"]) == ["AAA", "BRK-B"]
    assert list(current["company"]) == ["Alpha Corp", "Berkshire Hathaway"]
    assert list(current["gics_sector"]) == ["Industrials", "Financials"]


def test_parse_changes_keeps_unparseable_dates_and_blank_sides():
    changes = parse_changes(CHANGES_HTML)
    assert list(changes["source_row"]) == [1, 2, 3]
    assert changes.loc[0, "date"] == pd.Timestamp("2020-06-15")
    assert changes.loc[1, "date"] == pd.Timestamp("2018-03-01")  # footnote stripped
    assert pd.isna(changes.loc[2, "date"])                       # kept, not dropped
    assert changes.loc[0, "added_ticker"] == "DDD" and changes.loc[0, "removed_ticker"] == "XXX"
    assert pd.isna(changes.loc[1, "added_ticker"]) and changes.loc[1, "removed_ticker"] == "YYY"


# ---------------------------------------------------------------------------
# Membership reconstruction (test a)
# ---------------------------------------------------------------------------

def _invented_membership():
    """
    Current list: A, B, C, D. Changes, newest first:
      r1 2020-06-15  added D,  removed X
      r2 2018-03-01  added B,  removed Y   (B comes back)
      r3 2016-09-30  added X,  removed B
      r4 2014-01-02  added Y,  removed Z
      r5 2013-05-01  added Q,  removed A   (both inconsistent: Q is never a member
                                           afterwards, A is still a member afterwards)
    Worked out by hand:
      A: before history to current        B: before history to 2016-09-29, 2018-03-01 to current
      C: before history to current        D: 2020-06-15 to current
      X: 2016-09-30 to 2020-06-14         Y: 2014-01-02 to 2018-02-28
      Z: before history to 2014-01-01
    """
    current = pd.DataFrame({"ticker": ["A", "B", "C", "D"],
                            "company": ["Alpha", "Bravo", "Charlie", "Delta"],
                            "gics_sector": ["Energy", "Utilities", "Energy", "Financials"]})
    changes = pd.DataFrame({
        "date": pd.to_datetime(["2020-06-15", "2018-03-01", "2016-09-30", "2014-01-02", "2013-05-01"]),
        "raw_date": ["", "", "", "", ""],
        "added_ticker": ["D", "B", "X", "Y", "Q"],
        "added_name": ["Delta", "Bravo", "Xray", "Yankee", "Quebec"],
        "removed_ticker": ["X", "Y", "B", "Z", "A"],
        "removed_name": ["Xray", "Yankee", "Bravo", "Zulu", "Alpha"],
        "source_row": [1, 2, 3, 4, 5],
    })
    return rebuild_membership(current, changes)


def test_rebuild_membership_intervals_match_hand_result():
    intervals, _ = _invented_membership()
    none_if_missing = lambda v: None if pd.isna(v) else v
    got = [(r.ticker, none_if_missing(r.start_date), none_if_missing(r.end_date)) for r in intervals.itertuples()]
    expected = sorted([
        ("A", None, None),
        ("B", None, "2016-09-29"),
        ("B", "2018-03-01", None),
        ("C", None, None),
        ("D", "2020-06-15", None),
        ("X", "2016-09-30", "2020-06-14"),
        ("Y", "2014-01-02", "2018-02-28"),
        ("Z", None, "2014-01-01"),
    ], key=lambda t: (t[0], t[1] or "", t[2] or ""))
    got = sorted(got, key=lambda t: (t[0], t[1] or "", t[2] or ""))
    assert got == expected


def test_rebuild_membership_counts_inconsistencies_without_repairing():
    intervals, problems = _invented_membership()
    assert sorted(problems["ticker"]) == ["A", "Q"]
    assert "Q" not in set(intervals["ticker"])
    assert (intervals["ticker"] == "A").sum() == 1  # A not split by the bad removal


def test_rebuild_from_parsed_tables_treats_blank_cells_as_no_change():
    """
    Parsed tables store blank cells as NaN. Row 2 (only a removal of YYY)
    must not count as an addition, and row 3 (unparseable date) must be
    reported as a problem. Current list: DDD only.
      DDD: 2020-06-15 to current; XXX: before history to 2020-06-14;
      YYY: before history to 2018-02-28.
    """
    current = pd.DataFrame({"ticker": ["DDD"], "company": ["Delta Inc"], "gics_sector": ["Energy"]})
    intervals, problems = rebuild_membership(current, parse_changes(CHANGES_HTML))
    assert format_intervals(intervals, "DDD") == "2020-06-15 to current"
    assert format_intervals(intervals, "XXX") == "before history to 2020-06-14"
    assert format_intervals(intervals, "YYY") == "before history to 2018-02-28"
    assert list(problems["problem"]) == ["unparseable date"]
    assert list(problems["ticker"]) == ["QQQ"]


def test_rebuild_membership_sector_only_for_current_names():
    intervals, _ = _invented_membership()
    sectors = dict(zip(intervals["ticker"], intervals["gics_sector"]))
    assert sectors["D"] == "Financials"
    assert pd.isna(sectors["X"])


def test_members_at_dates_by_hand():
    intervals, _ = _invented_membership()
    def members(date):
        return {t for t in intervals["ticker"].unique() if is_member(intervals, t, date)}
    assert members("2013-12-31") == {"A", "B", "C", "Z"}
    assert members("2015-01-31") == {"A", "B", "C", "Y"}
    assert members("2017-01-31") == {"A", "C", "X", "Y"}
    assert members("2020-06-14") == {"A", "B", "C", "X"}   # last day for X
    assert members("2020-06-15") == {"A", "B", "C", "D"}   # effective date for D


def test_member_months_and_tickers_in_window():
    intervals, _ = _invented_membership()
    months = month_range("2016-08", "2016-10")
    assert member_months(intervals, "X", months) == ["2016-09", "2016-10"]
    assert member_months(intervals, "B", months) == ["2016-08"]
    assert tickers_in_window(intervals, month_range("2019-01", "2019-02")) == ["A", "B", "C", "X"]
    assert format_intervals(intervals, "B") == "before history to 2016-09-29; 2018-03-01 to current"


def test_sql_members_query_matches_python_rule():
    intervals, _ = _invented_membership()
    conn = sqlite3.connect(":memory:")
    create_feasibility_tables(conn)
    intervals.to_sql("index_membership", conn, if_exists="append", index=False)
    for date in ["2013-12-31", "2016-09-29", "2016-09-30", "2020-06-14", "2020-06-15"]:
        sql_members = {r[0] for r in conn.execute(members_query(), {"as_of_date": date})}
        py_members = {t for t in intervals["ticker"].unique() if is_member(intervals, t, date)}
        assert sql_members == py_members, date


# ---------------------------------------------------------------------------
# Month-end prices and price flags
# ---------------------------------------------------------------------------

def test_trading_calendar_uses_half_of_downloaded_tickers():
    """
    Four tickers. January: 3 trade on the 28th, only 1 on the 29th, so the
    last trading day is the 28th. February: exactly 2 of 4 on the 26th, which
    meets "at least half".
    """
    d = pd.Timestamp
    price_dates = {
        "A": [d("2021-01-28"), d("2021-01-29"), d("2021-02-26")],
        "B": [d("2021-01-28"), d("2021-02-25"), d("2021-02-26")],
        "C": [d("2021-01-28"), d("2021-02-25")],
        "D": [d("2021-01-27"), d("2021-02-25")],
    }
    calendar = trading_calendar(price_dates, ["2021-01", "2021-02", "2021-03"])
    assert calendar["2021-01"] == d("2021-01-28")
    assert calendar["2021-02"] == d("2021-02-26")
    assert pd.isna(calendar["2021-03"])


def test_months_with_price_requires_the_last_trading_day():
    """A stock delisted mid-month has prices in the month but no month-end price."""
    calendar = pd.Series({"2021-01": pd.Timestamp("2021-01-29"), "2021-02": pd.Timestamp("2021-02-26")})
    dates = pd.to_datetime(["2021-01-28", "2021-01-29", "2021-02-10"])
    assert months_with_price(dates, calendar) == ["2021-01"]


def test_price_window_flags():
    months = ["m1", "m2", "m3", "m4", "m5"]
    late_and_gap = price_window_flags({"m2", "m4", "m5"}, months)
    assert late_and_gap == {"member_months": 5, "months_with_price": 3,
                            "starts_late": True, "ends_early": False, "gap_inside": True}
    early = price_window_flags({"m1", "m2"}, months)
    assert (early["starts_late"], early["ends_early"], early["gap_inside"]) == (False, True, False)
    none = price_window_flags(set(), months)
    assert none["months_with_price"] == 0 and not none["starts_late"]


# ---------------------------------------------------------------------------
# Book value: the existing 6-month (180-day) rule, reused (test b)
# ---------------------------------------------------------------------------

def test_book_value_months_applies_existing_180_day_cap():
    """
    Filed 2020-08-03: usable from the end of August. 2020-12-31 is 150 days
    later (usable); 2021-01-31 is 181 days later (stale). Filed 2020-08-04:
    2021-01-31 is exactly 180 days later, which the existing rule keeps.
    July is before the filing date, so never usable.
    """
    months = month_range("2020-07", "2021-01")
    bv = pd.DataFrame({"end_date": [pd.Timestamp("2020-06-30")],
                       "filed_date": [pd.Timestamp("2020-08-03")],
                       "book_value_per_share": [10.0]})
    assert book_value_months(bv, months, forward_fill_book_value) == \
        ["2020-08", "2020-09", "2020-10", "2020-11", "2020-12"]
    bv.loc[0, "filed_date"] = pd.Timestamp("2020-08-04")
    assert book_value_months(bv, months, forward_fill_book_value)[-1] == "2021-01"


def test_book_value_months_empty_input():
    empty = pd.DataFrame(columns=["end_date", "filed_date", "book_value_per_share"])
    assert book_value_months(empty, ["2020-01"], forward_fill_book_value) == []


def test_cached_company_facts(tmp_path):
    write_gzip_json(tmp_path / "CIK0000000001.json.gz", {"facts": {"x": 1}})
    (tmp_path / "CIK0000000002.empty.json").write_text("{}")
    ciks = {"AAA": "0000000001", "BBB": "0000000002", "CCC": "0000000003"}
    get_company_facts = make_cached_company_facts(ciks.__getitem__, tmp_path)
    assert get_company_facts("AAA") == {"facts": {"x": 1}}
    assert get_company_facts("BBB") == {}
    with pytest.raises(FileNotFoundError):
        get_company_facts("CCC")


# ---------------------------------------------------------------------------
# Downloads: confirmed-empty rule, retries, throttle
# ---------------------------------------------------------------------------

class Missing(Exception):
    pass


def _fetch_sequence(outcomes):
    """fetch() that raises or returns the next item of `outcomes` on each call."""
    outcomes = list(outcomes)
    def fetch():
        item = outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    return fetch


def _run(outcomes, confirmations=2):
    sleeps = []
    result = download_with_retries(_fetch_sequence(outcomes), lambda e: isinstance(e, Missing),
                                   missing_confirmations=confirmations, sleep=sleeps.append)
    return result, sleeps


def test_missing_twice_is_confirmed_empty():
    (status, _, attempts, _), _ = _run([Missing(), Missing()])
    assert (status, attempts) == ("empty", 2)


def test_missing_once_then_data_is_ok():
    (status, result, attempts, _), _ = _run([Missing(), "data"])
    assert (status, result, attempts) == ("ok", "data", 2)


def test_missing_on_two_separate_attempts_with_error_between_is_empty():
    (status, _, attempts, _), _ = _run([Missing(), ConnectionError(), Missing()])
    assert (status, attempts) == ("empty", 3)


def test_persistent_error_is_error_not_missing():
    (status, result, attempts, message), sleeps = _run([ConnectionError("down")] * 4)
    assert (status, result, attempts) == ("error", None, 4)
    assert "ConnectionError" in message
    assert sleeps == [2, 8, 30]


def test_single_missing_then_errors_is_error():
    (status, _, _, _), _ = _run([Missing(), ConnectionError(), ConnectionError(), ConnectionError()])
    assert status == "error"


def test_sec_404_needs_one_confirmation():
    (status, _, attempts, _), _ = _run([Missing()], confirmations=1)
    assert (status, attempts) == ("empty", 1)


def test_rate_limiter_spaces_requests():
    now = [0.0]
    sleeps = []
    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds
    limiter = RateLimiter(8, clock=lambda: now[0], sleep=sleep)
    limiter.wait()             # first request: no wait
    now[0] += 0.05
    limiter.wait()             # 0.05 s later: waits the remaining 0.075 s
    now[0] += 0.5
    limiter.wait()             # long after: no wait
    assert sleeps == [pytest.approx(0.075)]


# ---------------------------------------------------------------------------
# Usability rules in SQL (test b)
# ---------------------------------------------------------------------------

def _coverage_db():
    """
    One evaluation month, t = 2021-02 (universe date 2021-01-31, t-1 = 2021-01,
    t-12 = 2020-02). Invented names:
      AAA  member; prices t-12, t-1, t; CIK; book value     -> usable both, observable
      BBB  added 2021-02-10, during month t                 -> not in t's universe
      CCC  member; price t-1 only                           -> no signal inputs
      DDD  member; prices t-12, t-1, none at t; book value  -> usable both, in both gaps
      EEE  last day 2021-01-30                              -> not a member at 2021-01-31
      FFF  member; prices; CIK; no book value               -> usable for Momentum only
      GGG  member; prices; no CIK                           -> usable for Momentum only
      HHH  last day 2021-01-31 (removed effective 2021-02-01) -> member; Momentum only
    CCC also has a book value row, so it counts as "with book value" (book value
    plus a t-1 price) but is still not usable, because it has no t-12 price.
    Hand counts: members 6 (AAA CCC DDD FFF GGG HHH), price t-1 6, signal inputs 5,
    CIK 5, book value 3 (AAA CCC DDD), usable Momentum 5, usable Value/Combined 2
    (AAA DDD), delisting gap Momentum 2 (DDD HHH), Value/Combined 1 (DDD).
    """
    conn = sqlite3.connect(":memory:")
    create_feasibility_tables(conn)
    membership = [("AAA", None, None), ("BBB", "2021-02-10", None), ("CCC", None, None),
                  ("DDD", None, None), ("EEE", None, "2021-01-30"), ("FFF", None, None),
                  ("GGG", None, None), ("HHH", None, "2021-01-31")]
    conn.executemany("INSERT INTO index_membership (ticker, start_date, end_date) VALUES (?, ?, ?)", membership)
    prices = {"AAA": ["2020-02", "2021-01", "2021-02"], "BBB": ["2020-02", "2021-01", "2021-02"],
              "CCC": ["2021-01"], "DDD": ["2020-02", "2021-01"], "EEE": ["2020-02", "2021-01"],
              "FFF": ["2020-02", "2021-01", "2021-02"], "GGG": ["2020-02", "2021-01", "2021-02"],
              "HHH": ["2020-02", "2021-01"]}
    conn.executemany("INSERT INTO price_month_end VALUES (?, ?)",
                     [(t, m) for t, ms in prices.items() for m in ms])
    conn.executemany("INSERT INTO book_value_month_end VALUES (?, ?)",
                     [("AAA", "2021-01"), ("DDD", "2021-01"), ("BBB", "2021-01"), ("CCC", "2021-01")])
    conn.executemany("INSERT INTO ticker_cik VALUES (?, ?)",
                     [("AAA", "1"), ("BBB", "2"), ("CCC", "3"), ("DDD", "4"), ("FFF", "6"),
                      ("GGG", None), ("HHH", "8")])
    evaluation_months_frame("2021-02", "2021-02").to_sql("evaluation_months", conn, if_exists="append", index=False)
    conn.executemany("INSERT INTO ticker_group VALUES (?, ?, ?)",
                     [("AAA", "stayed", "Energy"), ("CCC", "stayed", "Energy"), ("DDD", "removed", "unknown"),
                      ("FFF", "stayed", "Utilities"), ("GGG", "stayed", "Utilities"),
                      ("HHH", "removed", "unknown")])
    build_member_month_flags(conn)
    return conn


def test_monthly_usability_counts_by_hand():
    conn = _coverage_db()
    mark_reliable_months(conn, members_min=1, members_max=10)
    row = coverage_query(conn, "monthly_counts").iloc[0]
    assert row["month"] == "2021-02" and row["universe_date"] == "2021-01-31"
    expected = {"members": 6, "reliable": 1, "with_price_t1": 6, "with_signal_inputs": 5, "with_cik": 5,
                "with_book_value": 3, "usable_momentum": 5, "usable_value_combined": 2,
                "delisting_gap_momentum": 2, "delisting_gap_value_combined": 1,
                "members_no_price_t1": 0, "members_no_signal_inputs": 1}
    assert {k: int(row[k]) for k in expected} == expected


def test_member_flags_per_ticker():
    conn = _coverage_db()
    flags = pd.read_sql_query("SELECT * FROM member_month_usability ORDER BY ticker", conn).set_index("ticker")
    assert list(flags.index) == ["AAA", "CCC", "DDD", "FFF", "GGG", "HHH"]
    assert flags.loc["CCC", "has_book_value"] == 1           # book value and t-1 price ...
    assert flags.loc["CCC", "usable_value_combined"] == 0    # ... but no t-12 price
    assert flags.loc["DDD", "delisting_gap_value_combined"] == 1
    assert flags.loc["HHH", "delisting_gap_momentum"] == 1   # removed after t-1, no price at t


def test_reliable_flag_uses_registered_range():
    conn = _coverage_db()
    mark_reliable_months(conn)  # 480 to 520; 6 members is outside
    assert coverage_query(conn, "monthly_counts").iloc[0]["reliable"] == 0
    assert coverage_query(conn, "counts_by_sector").empty  # unreliable months excluded


def test_counts_by_group_and_sector():
    conn = _coverage_db()
    mark_reliable_months(conn, members_min=1, members_max=10)
    groups = coverage_query(conn, "monthly_counts_by_group").set_index("survivor_group")
    assert int(groups.loc["removed", "members"]) == 2
    assert int(groups.loc["removed", "delisting_gap_momentum"]) == 2
    assert int(groups.loc["stayed", "usable_value_combined"]) == 1
    sectors = coverage_query(conn, "counts_by_sector").set_index("sector")
    assert int(sectors.loc["Utilities", "usable_momentum"]) == 2
    assert int(sectors.loc["Utilities", "with_cik"]) == 1


def test_named_queries_present():
    queries = load_named_queries(SQL_DIR / "universe_coverage.sql")
    assert set(queries) == {"insert_member_month_flags", "create_usability_view", "mark_reliable_months",
                            "monthly_counts", "monthly_counts_by_group", "counts_by_sector"}


def test_summarize_by_year_uses_reliable_months_only():
    """
    Year 2021, three months; 2021-03 is unreliable and must be ignored.
    Group "removed" has no row in 2021-02, which counts as zero members.
      stayed:  members 10 + 20 = 30 over 2 reliable months -> avg 15;
               usable momentum 8 + 12 = 20 -> share 20/30; gap 1 of 20 usable -> 0.05
      removed: members 4 (one month) -> avg 2 over 2 reliable months;
               usable value/combined 0 -> delisting-gap share undefined (NaN)
    """
    def row(month, group, members, usable_m, gap_m):
        base = {c: 0 for c in COUNT_COLUMNS}
        base.update({"month": month, "group": group, "members": members,
                     "usable_momentum": usable_m, "delisting_gap_momentum": gap_m,
                     "members_no_price_t1": members - usable_m})
        return base
    counts = pd.DataFrame([row("2021-01", "stayed", 10, 8, 1), row("2021-02", "stayed", 20, 12, 0),
                           row("2021-03", "stayed", 999, 999, 999), row("2021-01", "removed", 4, 2, 0)])
    reliability = pd.Series({"2021-01": 1, "2021-02": 1, "2021-03": 0})
    result = summarize_by_year(counts, reliability).set_index("group")

    stayed = result.loc["stayed"]
    assert (stayed["months_reliable"], stayed["months_unreliable"], stayed["member_months"]) == (2, 1, 30)
    assert stayed["avg_members"] == pytest.approx(15.0)
    assert stayed["share_usable_momentum"] == pytest.approx(20 / 30)
    assert stayed["share_no_price_t1"] == pytest.approx(10 / 30)
    assert stayed["delisting_gap_share_momentum"] == pytest.approx(0.05)

    removed = result.loc["removed"]
    assert removed["avg_members"] == pytest.approx(2.0)
    assert pd.isna(removed["delisting_gap_share_value_combined"])


def test_survivor_group():
    intervals, _ = _invented_membership()
    assert survivor_group(intervals, "A") == "stayed"
    assert survivor_group(intervals, "B") == "removed"   # removed 2016, added again 2018
    assert survivor_group(intervals, "X") == "removed"
    late = pd.DataFrame({"ticker": ["L"], "start_date": [None], "end_date": ["2026-09-14"]})
    assert survivor_group(late, "L") == "stayed"          # removed after the window


# ---------------------------------------------------------------------------
# Gates and audit reasons
# ---------------------------------------------------------------------------

def test_gate1_failures():
    intervals, _ = _invented_membership()
    months = month_range("2016-09", "2016-11")  # universes on 2016-08-31, 09-30, 10-31
    assert gate1_failures(intervals, ["A", "X"], months) == {"X": ["2016-09"]}
    assert gate1_failures(intervals, ["B"], months) == {"B": ["2016-10", "2016-11"]}


def test_availability_mismatches():
    new = {("AAA", "2021-01"), ("AAA", "2021-02")}
    existing = {("AAA", "2021-01"), ("BBB", "2021-01")}
    rows = availability_mismatches(new, existing, ["AAA", "BBB"], ["2021-01", "2021-02"])
    assert rows == [{"ticker": "AAA", "month": "2021-02", "new": True, "existing": False},
                    {"ticker": "BBB", "month": "2021-01", "new": False, "existing": True}]


def test_exclusion_reasons():
    full = {"member_months": 10, "months_with_price": 10,
            "starts_late": False, "ends_early": False, "gap_inside": False}
    assert exclusion_reasons(10, "1", "ok", full, "ok", 10) == []

    partial = dict(full, months_with_price=7, starts_late=True)
    assert exclusion_reasons(10, "1", "ok", partial, "ok", 4) == [
        ("partial prices", "starts after membership start; 7 of 10 member months with a month-end price"),
        ("partial book value", "4 of 10 member months with book value"),
    ]

    none = dict(full, months_with_price=0)
    assert exclusion_reasons(10, None, "empty", none, None, 0) == [
        ("no prices", "0 of 10 member months with a month-end price"),
        ("no CIK", "ticker not in the SEC ticker file"),
    ]

    assert exclusion_reasons(10, "1", "error", none, "error", 0) == [
        ("persistent download error", "yfinance"),
        ("persistent download error", "SEC company facts"),
    ]
    assert exclusion_reasons(10, "1", "ok", full, "empty", 0) == [
        ("no book value", "0 of 10 member months with book value"),
    ]
