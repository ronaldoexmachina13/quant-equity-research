"""
Unit tests for src/book_value_rule.py (Amendments 9 and 10).

All inputs are small invented examples whose answers were worked out by
hand. No network, no real data.
"""
import pandas as pd
import pytest

from src.book_value_rule import (
    fixed_equity, fixed_shares, fixed_book_value_records, suspected_units_errors,
)

STANDARD = "StockholdersEquity"
INCLUDING_NCI = "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
BALANCE_SHEET = "CommonStockSharesOutstanding"
COVER_PAGE = "EntityCommonStockSharesOutstanding"


def entry(end, filed, value):
    return {"end": end, "filed": filed, "val": value}


def make_facts(standard=(), including_nci=(), balance_sheet=(), cover_page=()):
    """Company facts in the SEC layout, with only the tags that were given."""
    gaap, dei = {}, {}
    if standard:
        gaap[STANDARD] = {"units": {"USD": list(standard)}}
    if including_nci:
        gaap[INCLUDING_NCI] = {"units": {"USD": list(including_nci)}}
    if balance_sheet:
        gaap[BALANCE_SHEET] = {"units": {"shares": list(balance_sheet)}}
    if cover_page:
        dei[COVER_PAGE] = {"units": {"shares": list(cover_page)}}
    return {"facts": {"us-gaap": gaap, "dei": dei}}


def test_equity_prefers_standard_on_the_same_period_and_filing():
    # The tie from the finding: same period, same filing date, different values.
    facts = make_facts(standard=[entry("2020-03-31", "2020-04-24", 18)],
                       including_nci=[entry("2020-03-31", "2020-04-24", 20)])
    assert fixed_equity(facts)["value"].tolist() == [18]


def test_equity_prefers_standard_whichever_order_the_tags_arrive():
    # Standard filed earlier than the other tag: the old code kept the later one.
    facts = make_facts(standard=[entry("2020-03-31", "2020-04-24", 18)],
                       including_nci=[entry("2020-03-31", "2020-07-24", 20)])
    result = fixed_equity(facts)
    assert result["value"].tolist() == [18]
    assert result["filed_date"].tolist() == [pd.Timestamp("2020-04-24")]


def test_equity_uses_noncontrolling_figure_only_where_standard_is_absent():
    facts = make_facts(standard=[entry("2020-03-31", "2020-04-24", 18)],
                       including_nci=[entry("2020-03-31", "2020-04-24", 20), entry("2020-06-30", "2020-07-24", 21)])
    assert fixed_equity(facts)["value"].tolist() == [18, 21]


def test_equity_with_only_the_noncontrolling_figure():
    facts = make_facts(including_nci=[entry("2020-03-31", "2020-04-24", 20)])
    assert fixed_equity(facts)["value"].tolist() == [20]


def test_negative_standard_equity_is_kept_and_not_replaced():
    # The standard figure exists, so it is used; the positive mixed figure is not.
    facts = make_facts(standard=[entry("2020-03-31", "2020-04-24", -5)],
                       including_nci=[entry("2020-03-31", "2020-04-24", 3)])
    assert fixed_equity(facts)["value"].tolist() == [-5]


def test_equity_with_no_tags_is_empty():
    assert fixed_equity(make_facts()).empty


def test_shares_prefer_the_balance_sheet_figure_on_the_same_date():
    facts = make_facts(balance_sheet=[entry("2020-03-31", "2020-04-24", 100)],
                       cover_page=[entry("2020-03-31", "2020-04-24", 90)])
    assert fixed_shares(facts)["value"].tolist() == [100]


def test_shares_use_the_cover_page_where_the_balance_sheet_is_absent():
    facts = make_facts(balance_sheet=[entry("2020-03-31", "2020-04-24", 100)],
                       cover_page=[entry("2020-04-20", "2020-04-24", 90), entry("2020-07-20", "2020-07-24", 95)])
    assert fixed_shares(facts)["value"].tolist() == [100, 90, 95]


def test_shares_drop_non_positive_values_before_choosing():
    # A zero on the balance sheet is an invalid record, so that figure counts as absent.
    facts = make_facts(balance_sheet=[entry("2020-03-31", "2020-04-24", 0)],
                       cover_page=[entry("2020-03-31", "2020-04-24", 90)])
    assert fixed_shares(facts)["value"].tolist() == [90]


def test_record_divides_standard_equity_by_balance_sheet_shares():
    facts = make_facts(standard=[entry("2020-03-31", "2020-04-24", 1000)],
                       including_nci=[entry("2020-03-31", "2020-04-24", 2000)],
                       balance_sheet=[entry("2020-03-31", "2020-04-24", 100)],
                       cover_page=[entry("2020-03-31", "2020-04-24", 50)])
    assert fixed_book_value_records(facts)["book_value_per_share"].tolist() == [10.0]


def test_record_prefers_the_balance_sheet_date_over_a_later_cover_date():
    # Exact-date balance sheet figure of 100 beats the cover figure 20 days later.
    facts = make_facts(standard=[entry("2020-03-31", "2020-04-24", 1000)],
                       balance_sheet=[entry("2020-03-31", "2020-04-24", 100)],
                       cover_page=[entry("2020-04-20", "2020-04-24", 50)])
    assert fixed_book_value_records(facts)["book_value_per_share"].tolist() == [10.0]


def test_record_uses_the_cover_page_when_it_is_the_only_figure_within_45_days():
    facts = make_facts(standard=[entry("2020-03-31", "2020-04-24", 1000)],
                       cover_page=[entry("2020-04-20", "2020-04-24", 50)])
    assert fixed_book_value_records(facts)["book_value_per_share"].tolist() == [20.0]


def test_record_has_no_share_count_beyond_45_days():
    # 2020-03-31 to 2020-05-16 is 46 days.
    facts = make_facts(standard=[entry("2020-03-31", "2020-04-24", 1000)],
                       cover_page=[entry("2020-05-16", "2020-05-20", 50)])
    assert fixed_book_value_records(facts).empty


def test_record_filing_date_is_the_later_of_equity_and_shares():
    facts = make_facts(standard=[entry("2020-03-31", "2020-04-24", 1000)],
                       cover_page=[entry("2020-04-20", "2020-05-01", 50)])
    assert fixed_book_value_records(facts)["filed_date"].tolist() == [pd.Timestamp("2020-05-01")]


def test_record_drops_non_positive_book_value():
    facts = make_facts(standard=[entry("2020-03-31", "2020-04-24", -5), entry("2020-06-30", "2020-07-24", 800)],
                       balance_sheet=[entry("2020-03-31", "2020-04-24", 100), entry("2020-06-30", "2020-07-24", 100)])
    assert fixed_book_value_records(facts)["book_value_per_share"].tolist() == [8.0]


def test_two_records_on_one_filing_date_keep_the_newest_period():
    # The JNJ case: an old period and the current one share a filing date.
    facts = make_facts(standard=[entry("2023-01-01", "2023-07-31", 2900), entry("2023-07-02", "2023-07-31", 2800)],
                       balance_sheet=[entry("2023-01-01", "2023-07-31", 100), entry("2023-07-02", "2023-07-31", 100)])
    records = fixed_book_value_records(facts)
    assert records["book_value_per_share"].tolist() == [28.0]
    assert records["end_date"].tolist() == [pd.Timestamp("2023-07-02")]


def test_no_equity_or_no_shares_gives_empty_records_with_the_right_columns():
    for facts in (make_facts(), make_facts(standard=[entry("2020-03-31", "2020-04-24", 1)]), {}):
        records = fixed_book_value_records(facts)
        assert records.empty
        assert list(records.columns) == ["end_date", "filed_date", "book_value_per_share"]


def test_units_error_is_listed_above_a_factor_of_100():
    # 5,000,000 against 40,000 in one filing is a factor of 125.
    facts = make_facts(balance_sheet=[entry("2020-03-31", "2020-04-24", 5_000_000)],
                       cover_page=[entry("2020-04-20", "2020-04-24", 40_000)])
    errors = suspected_units_errors(facts)
    assert errors["factor"].tolist() == pytest.approx([125.0])
    assert errors["filed_date"].tolist() == [pd.Timestamp("2020-04-24")]


def test_units_error_works_in_either_direction():
    facts = make_facts(balance_sheet=[entry("2020-03-31", "2020-04-24", 40_000)],
                       cover_page=[entry("2020-04-20", "2020-04-24", 5_000_000)])
    assert suspected_units_errors(facts)["factor"].tolist() == pytest.approx([125.0])


def test_exactly_a_factor_of_100_is_not_listed():
    facts = make_facts(balance_sheet=[entry("2020-03-31", "2020-04-24", 100_000)],
                       cover_page=[entry("2020-04-20", "2020-04-24", 1_000)])
    assert suspected_units_errors(facts).empty


def test_tags_in_different_filings_are_not_compared():
    facts = make_facts(balance_sheet=[entry("2020-03-31", "2020-04-24", 5_000_000)],
                       cover_page=[entry("2020-07-20", "2020-07-24", 40_000)])
    assert suspected_units_errors(facts).empty


def test_units_check_with_one_tag_only_is_empty():
    assert suspected_units_errors(make_facts(balance_sheet=[entry("2020-03-31", "2020-04-24", 100)])).empty
