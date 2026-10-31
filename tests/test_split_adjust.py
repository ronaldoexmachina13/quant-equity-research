"""
Unit tests for src/split_adjust.py (Amendment 8).

All inputs are small invented examples whose answers were worked out by
hand. No network, no real data.
"""
import numpy as np
import pandas as pd
import pytest

from src.split_adjust import (
    splits_from_history, split_factor_after, restate_book_value, filled_book_value,
    filing_in_force, restate_stored_book_value,
)


def splits(*events):
    return pd.Series([ratio for _, ratio in events], index=pd.to_datetime([d for d, _ in events]), dtype=float)


def records(*rows):
    """(end_date, filed_date, book_value_per_share) rows, the shape of get_book_value_per_share()."""
    frame = pd.DataFrame(rows, columns=["end_date", "filed_date", "book_value_per_share"])
    frame["end_date"] = pd.to_datetime(frame["end_date"])
    frame["filed_date"] = pd.to_datetime(frame["filed_date"])
    return frame


def test_splits_from_history_keeps_only_days_with_a_split():
    dates = pd.to_datetime(["2024-02-23", "2024-02-26", "2024-02-27"])
    history = pd.DataFrame({"Close": [1.0, 2.0, 3.0], "Stock Splits": [0.0, 3.0, 0.0]}, index=dates)
    assert splits_from_history(history).to_dict() == {pd.Timestamp("2024-02-26"): 3.0}


def test_factor_is_one_with_no_later_split():
    assert split_factor_after("2024-03-15", splits(("2024-02-26", 3.0))) == 1.0
    assert split_factor_after("2024-03-15", splits()) == 1.0


def test_factor_counts_a_later_split():
    assert split_factor_after("2023-11-30", splits(("2024-02-26", 3.0))) == 3.0


def test_factor_multiplies_all_later_splits_and_skips_earlier_ones():
    # Filed after the 2:1 and before the 4:1 and the 3:1: 4 * 3 = 12.
    events = splits(("2014-01-15", 2.0), ("2020-08-31", 4.0), ("2024-02-26", 3.0))
    assert split_factor_after("2015-06-30", events) == 12.0


def test_factor_ignores_a_split_on_the_filing_date():
    assert split_factor_after("2024-02-26", splits(("2024-02-26", 3.0))) == 1.0


def test_restate_uses_the_filing_date_not_the_period_end():
    # The WMT case. The quarter to 2024-01-31 ended before the split, but was
    # filed after it, so it is already post-split and stays 10.41. The one
    # filed before the split is 29.51 / 3.
    filed = records(("2023-10-31", "2023-11-30", 29.51), ("2024-01-31", "2024-03-15", 10.41))
    restated = restate_book_value(filed, splits(("2024-02-26", 3.0)))
    assert restated["book_value_per_share"].tolist() == pytest.approx([29.51 / 3, 10.41])


def test_restate_leaves_the_input_unchanged():
    filed = records(("2023-10-31", "2023-11-30", 30.0))
    restate_book_value(filed, splits(("2024-02-26", 3.0)))
    assert filed["book_value_per_share"].tolist() == [30.0]


def test_restate_with_no_events_changes_nothing():
    filed = records(("2023-10-31", "2023-11-30", 30.0))
    pd.testing.assert_frame_equal(restate_book_value(filed, splits()), filed)


def test_restate_handles_empty_records():
    empty = pd.DataFrame(columns=["end_date", "filed_date", "book_value_per_share"])
    assert restate_book_value(empty, splits(("2024-02-26", 3.0))).empty


def test_price_over_restated_book_is_the_same_before_and_after_a_split():
    # A 3:1 split with nothing else changing: price 300 and book 30 filed
    # before it (P/B 10) become 100 and 10 after it. Yahoo shows the old price
    # as 100, so 100 / 30 is the wrong 3.33 and the restated 100 / 10 is 10.
    filed = records(("2023-10-31", "2023-11-30", 30.0), ("2024-04-30", "2024-06-07", 10.0))
    restated = restate_book_value(filed, splits(("2024-02-26", 3.0)))
    adjusted_price = 100.0
    assert (adjusted_price / restated["book_value_per_share"]).tolist() == pytest.approx([10.0, 10.0])


def test_filled_book_value_forward_fills_and_marks_gaps_as_nan():
    # Filed 2023-11-30: nothing at October's end, 30 at November's end, and
    # still 30 at 2024-05-31 (183 days is over the 180-day limit, so NaN).
    dates = pd.to_datetime(["2023-10-31", "2023-11-30", "2024-05-27", "2024-05-31"])
    frame = filled_book_value({"AAA": records(("2023-10-31", "2023-11-30", 30.0))}, dates)
    assert np.isnan(frame["AAA"].iloc[0])
    assert frame["AAA"].iloc[1:3].tolist() == [30.0, 30.0]
    assert np.isnan(frame["AAA"].iloc[3])
    assert frame["AAA"].dtype == float


def test_filled_book_value_with_no_records_is_all_nan():
    dates = pd.to_datetime(["2023-10-31"])
    empty = pd.DataFrame(columns=["end_date", "filed_date", "book_value_per_share"])
    assert filled_book_value({"V": empty}, dates)["V"].isna().all()


def test_filing_in_force_follows_the_forward_fill_rule():
    # Same dates as the forward-fill test: none before filing, in force for
    # 180 days, then none. The second filing takes over on its own date.
    filed = records(("2023-10-31", "2023-11-30", 30.0), ("2024-04-30", "2024-05-29", 10.0))
    dates = pd.to_datetime(["2023-10-31", "2023-11-30", "2024-05-28", "2024-05-29"])
    result = filing_in_force(filed, dates)
    assert pd.isna(result.iloc[0])
    assert result.iloc[1:3].tolist() == [pd.Timestamp("2023-11-30")] * 2
    assert result.iloc[3] == pd.Timestamp("2024-05-29")


def test_filing_in_force_expires_after_180_days():
    # 2023-11-30 plus 183 days is 2024-05-31, past the limit.
    result = filing_in_force(records(("2023-10-31", "2023-11-30", 30.0)), pd.to_datetime(["2024-05-31"]))
    assert pd.isna(result.iloc[0])


def test_filing_in_force_with_two_periods_on_one_filing_date():
    # The JNJ situation: whichever period wins, the filing date is the same.
    filed = records(("2023-01-01", "2023-07-31", 29.0), ("2023-07-02", "2023-07-31", 28.0))
    assert filing_in_force(filed, pd.to_datetime(["2023-08-31"])).iloc[0] == pd.Timestamp("2023-07-31")


def test_filing_in_force_with_no_records_is_all_nat():
    empty = pd.DataFrame(columns=["end_date", "filed_date", "book_value_per_share"])
    assert filing_in_force(empty, pd.to_datetime(["2023-10-31"])).isna().all()


def stored_frames():
    """Month ends around a 3:1 split on 2024-02-26; the post-split filing arrives on 2024-03-15."""
    dates = pd.to_datetime(["2024-01-31", "2024-02-29", "2024-03-31"])
    stored = pd.DataFrame({"AAA": [30.0, 30.0, 10.5], "BBB": [5.0, 5.0, 6.0]}, index=dates)
    filings = pd.DataFrame({"AAA": pd.to_datetime(["2023-11-30", "2023-11-30", "2024-03-15"]),
                            "BBB": pd.to_datetime(["2023-11-30", "2023-11-30", "2024-03-15"])}, index=dates)
    return stored, filings


def test_restate_stored_divides_months_on_a_pre_split_filing():
    # January and February use the filing before the split: 30 / 3 = 10. March
    # uses the filing after it. February is restated although the split falls
    # inside the month, because the filing in force is still the old one.
    stored, filings = stored_frames()
    restated = restate_stored_book_value(stored, filings, {"AAA": splits(("2024-02-26", 3.0)), "BBB": splits()})
    assert restated["AAA"].tolist() == pytest.approx([10.0, 10.0, 10.5])


def test_restate_stored_leaves_a_stock_with_no_event_equal():
    stored, filings = stored_frames()
    restated = restate_stored_book_value(stored, filings, {"AAA": splits(("2024-02-26", 3.0)), "BBB": splits()})
    pd.testing.assert_series_equal(restated["BBB"], stored["BBB"])


def test_restate_stored_keeps_gaps_and_leaves_the_input_unchanged():
    # A stored gap stays a gap, and a month with no filing in force is NaN.
    stored, filings = stored_frames()
    stored.loc[stored.index[0], "AAA"] = np.nan
    filings.loc[filings.index[1], "AAA"] = pd.NaT
    before = stored.copy()
    restated = restate_stored_book_value(stored, filings, {"AAA": splits(("2024-02-26", 3.0)), "BBB": splits()})
    assert restated["AAA"].isna().tolist() == [True, True, False]
    pd.testing.assert_frame_equal(stored, before)
