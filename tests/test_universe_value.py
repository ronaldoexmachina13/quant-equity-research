"""
Unit tests for src/universe_value.py (Phase 4, Stage 2, Value path).

All inputs are small invented examples whose answers were worked out by
hand. No network, no real data. Cache files are written to a temporary folder.
"""
import numpy as np
import pandas as pd
import pytest

from src.universe_value import (
    SPLIT_CUTOFF, split_path, write_split_file, load_split_history, apply_split_cutoff, build_records,
    value_usable_mask, value_signal, combined_signal, reconcile_usable, reconciliation_failures,
    book_value_jumps, split_event_check, is_ordinary_ratio, extreme_move_names, winsorise_pb, excluding_names,
    sensitivity_signals, pb_range, pb_cases,
)

MONTHS = pd.to_datetime(["2020-01-31", "2020-02-29", "2020-03-31"])


def splits(*events):
    return pd.Series([r for _, r in events], index=pd.to_datetime([d for d, _ in events]), dtype=float)


def records(*rows):
    frame = pd.DataFrame(rows, columns=["end_date", "filed_date", "book_value_per_share"])
    frame["end_date"] = pd.to_datetime(frame["end_date"])
    frame["filed_date"] = pd.to_datetime(frame["filed_date"])
    return frame


def test_cut_off_is_the_registered_date():
    assert SPLIT_CUTOFF == "2026-10-28"


def test_split_file_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("UNIVERSE_CACHE_DIR", str(tmp_path))
    write_split_file("AAA", splits(("2020-08-31", 4.0)))
    loaded, missing = load_split_history(["AAA"])
    assert missing == []
    assert loaded["AAA"].to_dict() == {pd.Timestamp("2020-08-31"): 4.0}


def test_a_confirmed_no_split_file_loads_as_empty_and_is_not_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("UNIVERSE_CACHE_DIR", str(tmp_path))
    write_split_file("AAA", splits())
    assert split_path("AAA").exists()
    loaded, missing = load_split_history(["AAA"])
    assert missing == []
    assert loaded["AAA"].empty
    assert isinstance(loaded["AAA"].index, pd.DatetimeIndex)


def test_a_ticker_with_no_file_is_missing_and_never_read_as_no_splits(tmp_path, monkeypatch):
    monkeypatch.setenv("UNIVERSE_CACHE_DIR", str(tmp_path))
    write_split_file("AAA", splits())
    loaded, missing = load_split_history(["AAA", "BBB"])
    assert missing == ["BBB"]
    assert "BBB" not in loaded


def test_cut_off_keeps_the_day_itself_and_lists_later_splits():
    history = {"AAA": splits(("2026-10-28", 2.0), ("2026-10-29", 3.0)), "BBB": splits()}
    kept, ignored = apply_split_cutoff(history)
    assert kept["AAA"].index.tolist() == [pd.Timestamp("2026-10-28")]
    assert kept["BBB"].empty
    assert ignored.to_dict("records") == [{"ticker": "AAA", "date": pd.Timestamp("2026-10-29"), "ratio": 3.0}]


def test_build_records_applies_the_validity_rule_and_keeps_tickers_with_empty_facts():
    # Share tags of 101 and 1 in one filing are a factor of 101: that filing has no book value.
    facts = {"AAA": {"facts": {
        "us-gaap": {"StockholdersEquity": {"units": {"USD": [{"end": "2020-03-31", "filed": "2020-04-24", "val": 1010}]}},
                    "CommonStockSharesOutstanding": {"units": {"shares": [
                        {"end": "2020-03-31", "filed": "2020-04-24", "val": 101}]}}},
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
            {"end": "2020-04-20", "filed": "2020-04-24", "val": 1}]}}}}},
             "BBB": {}}
    result, units = build_records(["AAA", "BBB"], facts.get)
    assert result["AAA"]["filed_date"].tolist() == [pd.Timestamp("2020-04-24")]
    assert result["AAA"]["book_value_per_share"].isna().all()
    assert result["BBB"].empty
    assert units["ticker"].tolist() == ["AAA"]
    assert units["factor"].tolist() == [101.0]


def test_value_usable_mask_needs_a_momentum_name_and_book_value_at_t_minus_one():
    # Row 2020-02 uses book value at 2020-01. AAA has it, BBB does not, and CCC
    # has it but is not usable for Momentum. DDD has no book value column.
    months = MONTHS[:2]
    book = pd.DataFrame({"AAA": [5.0, np.nan], "BBB": [np.nan, 5.0], "CCC": [5.0, 5.0]}, index=months)
    momentum = pd.DataFrame({"AAA": [False, True], "BBB": [False, True], "CCC": [False, False], "DDD": [False, True]},
                            index=months)
    mask = value_usable_mask(momentum, book)
    assert mask.loc[months[1]].to_dict() == {"AAA": True, "BBB": False, "CCC": False, "DDD": False}


def test_value_signal_uses_close_and_book_at_t_minus_one():
    # Row 2020-02: price 20 at 2020-01 over book 4 is P/B 5, score -5. The
    # 2020-02 price of 999 and book of 1 must not enter it.
    close = pd.DataFrame({"AAA": [20.0, 999.0]}, index=pd.to_datetime(["2020-01-31", "2020-02-28"]))
    book = pd.DataFrame({"AAA": [4.0, 1.0]}, index=MONTHS[:2])
    mask = pd.DataFrame({"AAA": [True]}, index=MONTHS[1:2])
    assert value_signal(close, book, mask)["AAA"].tolist() == [-5.0]


def test_value_signal_blanks_names_that_are_not_usable():
    close = pd.DataFrame({"AAA": [20.0, 21.0], "BBB": [20.0, 21.0]}, index=pd.to_datetime(["2020-01-31", "2020-02-28"]))
    book = pd.DataFrame({"AAA": [4.0, 4.0], "BBB": [4.0, 4.0]}, index=MONTHS[:2])
    mask = pd.DataFrame({"AAA": [True], "BBB": [False]}, index=MONTHS[1:2])
    result = value_signal(close, book, mask)
    assert result["AAA"].iloc[0] == -5.0 and np.isnan(result["BBB"].iloc[0])


def test_combined_signal_z_scores_each_leg_on_its_own_usable_names():
    # Momentum has three names, so its z-scores use all three: mean 2, sd 1.
    # Value has A and B only: scores -2 and -4, mean -3, sd sqrt 2.
    # A: (-1 + 1/sqrt2) / 2. C has no Value, so no Combined score.
    dates = MONTHS[:1]
    momentum = pd.DataFrame({"A": [1.0], "B": [2.0], "C": [3.0]}, index=dates)
    value = pd.DataFrame({"A": [-2.0], "B": [-4.0], "C": [np.nan]}, index=dates)
    result = combined_signal(momentum, value)
    assert result["A"].iloc[0] == pytest.approx((-1 + 1 / np.sqrt(2)) / 2)
    assert np.isnan(result["C"].iloc[0])


def masks():
    """January: Phase 3 has A, B; the rule has B, C. February: both have A."""
    phase3 = pd.DataFrame({"A": [True, True], "B": [True, False], "C": [False, False]}, index=MONTHS[:2])
    used = pd.DataFrame({"A": [False, True], "B": [True, False], "C": [True, False]}, index=MONTHS[:2])
    return phase3, used


def test_reconcile_counts_and_names():
    table = reconcile_usable(*masks())
    january = table.iloc[0]
    assert january["month"] == "2020-01"
    assert (january["phase3"], january["lost"], january["gained"], january["used"]) == (2, 1, 1, 2)
    assert january["lost_names"] == "A" and january["gained_names"] == "C"
    assert table.iloc[1]["lost_names"] == "" and table.iloc[1]["used"] == 1


def good_inputs():
    table = reconcile_usable(*masks())
    coverage = pd.DataFrame({"month": ["2020-01", "2020-02"], "usable_value_combined": [2, 1]})
    signal_counts = pd.Series([2, 1], index=MONTHS[:2])
    return table, coverage, signal_counts


def test_reconciliation_closes():
    assert reconciliation_failures(*good_inputs()) == []


def test_reconciliation_fails_if_phase3_differs_from_the_coverage_file():
    table, coverage, signal_counts = good_inputs()
    coverage.loc[0, "usable_value_combined"] = 3
    assert len(reconciliation_failures(table, coverage, signal_counts)) == 1


def test_reconciliation_fails_if_the_signal_count_differs_from_the_count_used():
    table, coverage, signal_counts = good_inputs()
    signal_counts.iloc[1] = 0
    assert len(reconciliation_failures(table, coverage, signal_counts)) == 1


def test_reconciliation_fails_if_the_arithmetic_does_not_close():
    table, coverage, signal_counts = good_inputs()
    table.loc[0, "gained"] = 5
    assert len(reconciliation_failures(table, coverage, signal_counts)) == 1


def test_jump_above_a_factor_of_two_is_listed_in_either_direction():
    # 10 to 21 is a factor of 2.1 up; 21 to 7 is a factor of 3 down.
    book = pd.DataFrame({"A": [10.0, 21.0, 7.0]}, index=MONTHS)
    jumps = book_value_jumps(book)
    assert jumps["factor"].tolist() == pytest.approx([2.1, 3.0])
    assert jumps["month"].tolist() == ["2020-02", "2020-03"]
    assert jumps["ticker"].tolist() == ["A", "A"]


def test_exactly_a_factor_of_two_is_not_a_jump():
    book = pd.DataFrame({"A": [10.0, 20.0, 10.0]}, index=MONTHS)
    assert book_value_jumps(book).empty


def test_a_jump_across_a_gap_is_still_listed_with_its_length():
    book = pd.DataFrame({"A": [10.0, np.nan, 30.0]}, index=MONTHS)
    jumps = book_value_jumps(book)
    assert jumps["factor"].tolist() == pytest.approx([3.0])
    assert jumps["months_since_previous"].tolist() == [2]


def test_jumps_on_an_empty_frame_have_the_right_columns():
    jumps = book_value_jumps(pd.DataFrame({"A": [np.nan] * 3}, index=MONTHS))
    assert jumps.empty
    assert "factor" in jumps.columns


def test_is_ordinary_ratio():
    assert is_ordinary_ratio(4.0) and is_ordinary_ratio(1.5) and is_ordinary_ratio(0.1) and is_ordinary_ratio(0.125)
    assert not is_ordinary_ratio(1.589)


def test_split_event_check_shows_a_clean_restatement():
    # 3:1 on 2024-02-26. As filed 30 then 10.5; restated 10 then 10.5, a step of 1.05.
    filed = records(("2023-10-31", "2023-11-30", 30.0), ("2024-04-30", "2024-06-07", 10.5))
    rows = split_event_check({"AAA": filed}, {"AAA": splits(("2024-02-26", 3.0))})
    row = rows.iloc[0]
    assert row["as_filed_before"] == 30.0 and row["as_filed_after"] == 10.5
    assert row["restated_before"] == pytest.approx(10.0)
    assert row["restated_step"] == pytest.approx(1.05)
    assert not row["large_step"]
    assert row["ordinary_ratio"]


def test_split_event_check_flags_a_filing_after_the_split_on_old_shares():
    # The filing after the split still carries the old share count, so it is
    # not divided: restated 10 then 31, a step of 3.1. This is what the check is for.
    filed = records(("2023-10-31", "2023-11-30", 30.0), ("2024-01-31", "2024-03-15", 31.0))
    assert split_event_check({"AAA": filed}, {"AAA": splits(("2024-02-26", 3.0))}).iloc[0]["large_step"]


def test_split_event_check_handles_a_split_with_no_filing_on_one_side():
    filed = records(("2023-10-31", "2023-11-30", 30.0))
    row = split_event_check({"AAA": filed}, {"AAA": splits(("2024-02-26", 3.0))}).iloc[0]
    assert np.isnan(row["restated_step"])
    assert not row["large_step"]


def test_split_event_check_skips_tickers_with_no_records():
    empty = pd.DataFrame(columns=["end_date", "filed_date", "book_value_per_share"])
    assert split_event_check({"AAA": empty}, {"AAA": splits(("2024-02-26", 3.0))}).empty


def test_split_check_passes_over_a_blank_from_the_validity_rule():
    # The filing before the split is a blank, so the step is measured from the last filing with a value.
    bv = pd.concat([records(("2019-12-31", "2020-02-01", 100.0), ("2020-03-31", "2020-05-01", 50.0)),
                    records((None, "2020-03-01", float("nan")))], ignore_index=True)
    row = split_event_check({"AAA": bv}, {"AAA": splits(("2020-04-01", 2.0))}).iloc[0]
    assert row["as_filed_before"] == 100.0
    assert row["restated_step"] == 1.0


def test_extreme_move_names_are_strictly_above_the_factor():
    jumps = pd.DataFrame({"ticker": ["BBB", "AAA", "AAA", "CCC"], "factor": [150.0, 101.0, 300.0, 100.0]})
    assert extreme_move_names(jumps) == ["AAA", "BBB"]


def test_extreme_move_names_on_an_empty_report():
    assert extreme_move_names(pd.DataFrame(columns=["ticker", "factor"])) == []


def wide_scores(pb_values):
    """One month of Value scores from a list of P/B values."""
    names = [f"N{i:03d}" for i in range(len(pb_values))]
    return pd.DataFrame([[-p for p in pb_values]], index=MONTHS[:1], columns=names, dtype=float)


def test_winsorise_caps_both_tails_at_the_percentiles():
    # P/B 1 to 101: position 0.01 * 100 = 1 is 2, and position 0.99 * 100 = 99 is 100.
    result = -winsorise_pb(wide_scores(list(range(1, 102)))).iloc[0]
    assert result.iloc[0] == 2.0
    assert result.iloc[-1] == 100.0
    assert result.iloc[1:-1].tolist() == list(range(2, 101))


def test_winsorise_uses_each_month_on_its_own_and_skips_blanks():
    frame = pd.DataFrame({"A": [-1.0, -100.0], "B": [-2.0, np.nan], "C": [-3.0, -300.0]}, index=MONTHS[:2])
    result = winsorise_pb(frame, lower=0.5, upper=0.5)
    # Month 1 has median 2. Month 2 has only A and C, median 200, and B stays blank.
    assert result.iloc[0].tolist() == [-2.0, -2.0, -2.0]
    assert result.loc[MONTHS[1], ["A", "C"]].tolist() == [-200.0, -200.0]
    assert np.isnan(result.loc[MONTHS[1], "B"])


def test_winsorise_stops_one_extreme_value_flattening_the_others():
    # The reason for decision 3: with raw P/B the z-score gap between ordinary names nearly vanishes.
    raw = wide_scores(list(range(1, 101)) + [1_000_000])
    capped = winsorise_pb(raw)
    # P/B 3 and 4 are one apart. The standard deviation is about 99,500 raw and about 29 capped.
    gap = lambda frame: abs((frame.iloc[0, 2] - frame.iloc[0, 3]) / frame.iloc[0].std())
    assert gap(raw) < 0.0001
    assert gap(capped) > 0.03


def test_excluding_names_blanks_every_month_and_keeps_the_shape():
    frame = pd.DataFrame({"A": [1.0, 2.0], "B": [3.0, 4.0]}, index=MONTHS[:2])
    result = excluding_names(frame, ["B", "NOT_THERE"])
    assert list(result.columns) == ["A", "B"]
    assert result["A"].tolist() == [1.0, 2.0]
    assert result["B"].isna().all()


def test_sensitivity_signals_leave_the_inputs_unchanged():
    momentum = pd.DataFrame([[0.1, 0.2, 0.3, 0.4]], index=MONTHS[:1], columns=list("ABCD"))
    value = pd.DataFrame([[-1.0, -2.0, -3.0, -4.0]], index=MONTHS[:1], columns=list("ABCD"))
    before = value.copy()
    sensitivity_signals(momentum, value, ["D"])
    pd.testing.assert_frame_equal(value, before)


def test_excluded_names_leave_combined_before_it_is_standardised():
    # Without D, momentum 0.1, 0.2, 0.3 and P/B 3, 2, 1 have z-scores -1, 0, 1 in both legs.
    momentum = pd.DataFrame([[0.1, 0.2, 0.3, 9.0]], index=MONTHS[:1], columns=list("ABCD"))
    value = pd.DataFrame([[-3.0, -2.0, -1.0, -1000.0]], index=MONTHS[:1], columns=list("ABCD"))
    combined = sensitivity_signals(momentum, value, ["D"])["excluding_extreme_moves"]["Combined"].iloc[0]
    assert combined[list("ABC")].tolist() == pytest.approx([-1.0, 0.0, 1.0])
    assert np.isnan(combined["D"])


def test_winsorised_combined_uses_the_capped_value_leg():
    names = [f"N{i:03d}" for i in range(101)]
    momentum = pd.DataFrame([[float(i) for i in range(101)]], index=MONTHS[:1], columns=names)
    value = wide_scores(list(range(1, 102)))
    result = sensitivity_signals(momentum, value, [])["winsorised_pb"]
    pd.testing.assert_frame_equal(result["Value"], winsorise_pb(value))
    pd.testing.assert_frame_equal(result["Combined"], combined_signal(momentum, winsorise_pb(value)))


def test_pb_range_counts_and_period_filter():
    value = pd.DataFrame({"A": [-0.05, -2.0], "B": [-3.0, -0.01], "C": [-5.0, np.nan]}, index=MONTHS[:2])
    report = pb_range(value)
    assert report["name_months"] == 5
    assert report["min"] == 0.01
    assert report["max"] == 5.0
    assert report["median"] == 2.0
    assert report["below_low"] == 2
    assert report["months_below_low"] == 2
    assert pb_range(value, MONTHS[:1])["below_low"] == 1


def test_pb_cases_lists_low_and_high_name_months():
    value = pd.DataFrame({"A": [-0.05, -2.0], "B": [-3.0, -0.01]}, index=MONTHS[:2])
    low, high = pb_cases(value, top=1)
    assert low.to_dict("records") == [{"month": "2020-02", "ticker": "B", "pb": 0.01},
                                      {"month": "2020-01", "ticker": "A", "pb": 0.05}]
    assert high.to_dict("records") == [{"month": "2020-01", "ticker": "B", "pb": 3.0}]
