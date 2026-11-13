"""Tests for build_book_value_table: a network failure must never be stored as 'no data'."""
import pandas as pd
import pytest
import requests

from scripts.first_study.run_fundamentals_pipeline import build_book_value_table, sec_says_missing

DATES = pd.date_range("2020-01-31", periods=3, freq="ME")


def _http_error(code):
    response = requests.Response()
    response.status_code = code
    return requests.HTTPError(f"{code}", response=response)


def _filings():
    return pd.DataFrame({
        "end_date": [pd.Timestamp("2019-12-31")],
        "filed_date": [pd.Timestamp("2020-01-15")],
        "book_value_per_share": [10.0],
    })


def test_sec_says_missing_only_for_404_or_unlisted_ticker():
    assert sec_says_missing(_http_error(404))
    assert sec_says_missing(KeyError("V"))
    assert not sec_says_missing(_http_error(503))
    assert not sec_says_missing(requests.ConnectionError("down"))
    assert not sec_says_missing(requests.HTTPError("no response attached"))


def test_good_ticker_is_filled_forward_from_the_filing_date():
    table = build_book_value_table(["A"], DATES, fetch_book_value=lambda t: _filings(), sleep=lambda s: None)
    assert table["A"].tolist() == [10.0, 10.0, 10.0]


def test_confirmed_missing_ticker_becomes_an_all_nan_column():
    def fetch(ticker):
        raise KeyError(ticker)
    table = build_book_value_table(["V"], DATES, fetch_book_value=fetch, sleep=lambda s: None)
    assert table["V"].isna().all()


def test_transient_failure_is_retried_and_then_used():
    calls = []

    def fetch(ticker):
        calls.append(ticker)
        if len(calls) < 3:
            raise requests.ConnectionError("blip")
        return _filings()
    table = build_book_value_table(["A"], DATES, fetch_book_value=fetch, sleep=lambda s: None)
    assert len(calls) == 3
    assert table["A"].notna().all()


def test_persistent_failure_raises_instead_of_storing_nan():
    def fetch(ticker):
        raise requests.ConnectionError("down")
    with pytest.raises(RuntimeError, match="Nothing was saved"):
        build_book_value_table(["A"], DATES, fetch_book_value=fetch, sleep=lambda s: None)
