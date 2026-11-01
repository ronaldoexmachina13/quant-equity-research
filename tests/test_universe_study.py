"""
Unit tests for src/universe_study.py (Phase 4, Stage 2, Momentum path).

All inputs are small invented examples whose answers were worked out by
hand. No network, no real data. Cache files are written to a temporary folder.
"""
import gzip
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from src.backtest import calculate_monthly_returns
from src.universe_study import (
    evaluation_dates, read_month_end_prices, cached_tickers, usable_mask, momentum_signal,
    count_mismatches, price_ratio_report, price_ratio_failures, top_n_returns, sharpe_failures,
    holdings_differences, study_periods, period_labels, NEW_TEST, RE_TEST, FULL_PERIOD, UNIVERSE_NOTE,
    counts_frame, series_frame,
)
from src.signal_eval import monthly_counts


def write_prices(folder, ticker, rows, field="Adj Close"):
    (folder / "prices").mkdir(exist_ok=True)
    text = pd.DataFrame(rows, columns=["Date", field, "Close"]).to_csv(index=False)
    (folder / "prices" / f"{ticker}.csv.gz").write_bytes(gzip.compress(text.encode("utf-8")))


def test_momentum_path_imports_no_book_value_or_split_code():
    code = ("import sys; import src.universe_study; "
            "print([m for m in sys.modules if m in ('src.fundamentals', 'src.split_adjust', 'yfinance')])")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "[]"


def test_evaluation_dates_cover_the_registered_176_months():
    dates = evaluation_dates()
    assert len(dates) == 176
    assert dates[0] == pd.Timestamp("2012-01-31")
    assert dates[-1] == pd.Timestamp("2026-08-31")


def test_read_month_end_prices_takes_only_the_last_trading_day(tmp_path, monkeypatch):
    # AAA trades to the end of both months. BBB stops on 2020-02-10, before
    # February's last trading day, so it has a January price and no February one.
    monkeypatch.setenv("UNIVERSE_CACHE_DIR", str(tmp_path))
    write_prices(tmp_path, "AAA", [("2020-01-30", 9, 90), ("2020-01-31", 10, 100), ("2020-02-28", 11, 110)])
    write_prices(tmp_path, "BBB", [("2020-01-31", 20, 200), ("2020-02-10", 21, 210)])
    calendar = pd.Series(pd.to_datetime(["2020-01-31", "2020-02-28"]), index=["2020-01", "2020-02"])
    prices = read_month_end_prices(calendar)
    assert cached_tickers() == ["AAA", "BBB"]
    assert prices["AAA"].tolist() == [10, 11]
    assert prices["BBB"].iloc[0] == 20 and np.isnan(prices["BBB"].iloc[1])


def test_read_month_end_prices_can_read_the_close(tmp_path, monkeypatch):
    monkeypatch.setenv("UNIVERSE_CACHE_DIR", str(tmp_path))
    write_prices(tmp_path, "AAA", [("2020-01-31", 10, 100)])
    calendar = pd.Series(pd.to_datetime(["2020-01-31"]), index=["2020-01"])
    assert read_month_end_prices(calendar, field="Close")["AAA"].tolist() == [100]


def test_usable_mask_dates_rows_at_the_calendar_end_and_ignores_unusable_rows():
    usability = pd.DataFrame({"month": ["2020-01", "2020-01", "2020-02"], "ticker": ["AAA", "BBB", "AAA"],
                              "usable_momentum": [1, 0, 1]})
    dates = pd.to_datetime(["2020-01-31", "2020-02-29"])
    mask = usable_mask(usability, "usable_momentum", dates, ["AAA", "BBB", "CCC"])
    assert mask["AAA"].tolist() == [True, True]
    assert mask["BBB"].tolist() == [False, False]
    assert mask["CCC"].tolist() == [False, False]


def momentum_inputs():
    """Fourteen month-end prices. AAA doubles from 2019-01 to 2019-12; BBB is flat until it stops after 2020-01."""
    dates = pd.date_range("2019-01-31", periods=14, freq="ME")
    aaa = [100.0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 200, 999, 999]
    bbb = [50.0] * 13 + [np.nan]
    return pd.DataFrame({"AAA": aaa, "BBB": bbb}, index=dates)


def test_momentum_signal_row_t_uses_prices_to_t_minus_one():
    # Row dated 2020-01: price at 2019-12 over price at 2019-01, minus 1 = 1.0.
    # The 2020-01 price of 999 must not enter it.
    prices = momentum_inputs()
    dates = pd.to_datetime(["2020-01-31"])
    usability = pd.DataFrame({"month": ["2020-01"], "ticker": ["AAA"], "usable_momentum": [1]})
    signal = momentum_signal(prices, usability, dates)
    assert signal.loc[dates[0], "AAA"] == pytest.approx(1.0)


def test_momentum_signal_blanks_names_that_are_not_usable():
    # BBB has a momentum value in 2020-01 but is not in the universe that month.
    prices = momentum_inputs()
    dates = pd.to_datetime(["2020-01-31"])
    usability = pd.DataFrame({"month": ["2020-01"], "ticker": ["AAA"], "usable_momentum": [1]})
    assert np.isnan(momentum_signal(prices, usability, dates).loc[dates[0], "BBB"])


def test_a_name_with_no_price_at_t_has_no_return_and_stays_usable():
    # BBB has no 2020-02 price: usable at the end of 2020-01, no return in 2020-02.
    # calculate_monthly_returns() must leave NaN and not fill a 0% return.
    prices = momentum_inputs()
    returns = calculate_monthly_returns(prices)
    dates = pd.to_datetime(["2020-02-29"])
    usability = pd.DataFrame({"month": ["2020-02", "2020-02"], "ticker": ["AAA", "BBB"], "usable_momentum": [1, 1]})
    signal = momentum_signal(prices, usability, dates)
    assert np.isnan(returns.loc[dates[0], "BBB"])
    counts = monthly_counts(signal, returns)
    assert counts["usable"].tolist() == [2]
    assert counts["no_return"].tolist() == [1]


def test_count_mismatches():
    found = pd.Series([10, 11], index=pd.to_datetime(["2020-01-31", "2020-02-29"]))
    good = pd.DataFrame({"month": ["2020-01", "2020-02"], "n": [10, 11]})
    bad = pd.DataFrame({"month": ["2020-01", "2020-02"], "n": [10, 12]})
    assert count_mismatches(found, good, "n").empty
    assert count_mismatches(found, bad, "n").to_dict("records") == [{"month": "2020-02", "found": 11.0, "expected": 12.0}]


def test_count_mismatches_flags_a_month_on_one_side_only():
    found = pd.Series([10], index=pd.to_datetime(["2020-01-31"]))
    coverage = pd.DataFrame({"month": ["2020-01", "2020-02"], "n": [10, 11]})
    assert count_mismatches(found, coverage, "n")["month"].tolist() == ["2020-02"]


def price_frames():
    dates = pd.to_datetime(["2020-01-31", "2020-02-28"])
    stored = pd.DataFrame({"AAA": [100.0, 110.0]}, index=dates)
    return dates, stored


def test_price_ratio_constant_level_difference_passes_and_is_reported():
    # Cached prices are a constant 0.5% lower: ratio 0.995 in both months.
    dates, stored = price_frames()
    report = price_ratio_report(stored * 0.995, stored)
    assert report["level_difference"].iloc[0] == pytest.approx(-0.005)
    assert report["spread"].iloc[0] == pytest.approx(0, abs=1e-12)
    assert price_ratio_failures(report) == []


def test_price_ratio_spread_above_tolerance_fails():
    # Ratios 1.0 and 1.00002: spread 2e-5, above 1e-5.
    dates, stored = price_frames()
    cached = pd.DataFrame({"AAA": [100.0, 110.0 * 1.00002]}, index=dates)
    assert len(price_ratio_failures(price_ratio_report(cached, stored))) == 1


def test_price_ratio_spread_just_inside_tolerance_passes():
    # Ratios 1.0 and 1.000005: spread 5e-6.
    dates, stored = price_frames()
    cached = pd.DataFrame({"AAA": [100.0, 110.0 * 1.000005]}, index=dates)
    assert price_ratio_failures(price_ratio_report(cached, stored)) == []


def test_price_ratio_missing_month_fails():
    dates, stored = price_frames()
    cached = pd.DataFrame({"AAA": [100.0, np.nan]}, index=dates)
    assert len(price_ratio_failures(price_ratio_report(cached, stored))) == 1


def test_top_n_returns_applies_the_row_dated_t_to_the_return_dated_t():
    # Top 1 by signal is AAA in January and BBB in February: returns 1% then 4%.
    dates = pd.to_datetime(["2020-01-31", "2020-02-29"])
    signal = pd.DataFrame({"AAA": [2.0, 1.0], "BBB": [1.0, 2.0]}, index=dates)
    returns = pd.DataFrame({"AAA": [.01, .03], "BBB": [.02, .04]}, index=dates)
    gross, weights = top_n_returns(signal, returns, dates, top_n=1)
    assert gross.tolist() == pytest.approx([.01, .04])
    assert weights["AAA"].tolist() == [1.0, 0.0]


def test_sharpe_failures_uses_the_tolerance():
    # Constant-mean series: Sharpe is computed, then compared with itself.
    series = pd.Series([.01, .03, -.01, .02] * 6)
    from src.risk import sharpe_ratio
    published = pd.DataFrame({"sharpe_ratio": [sharpe_ratio(series)]}, index=["Momentum"])
    assert sharpe_failures({"Momentum": series}, published) == []
    published.loc["Momentum", "sharpe_ratio"] += 0.00011
    assert len(sharpe_failures({"Momentum": series}, published)) == 1


def test_sharpe_failures_treats_nan_as_a_failure():
    published = pd.DataFrame({"sharpe_ratio": [np.nan]}, index=["Momentum"])
    assert len(sharpe_failures({"Momentum": pd.Series([.01, .02, .03])}, published)) == 1


def test_holdings_differences_lists_months_that_differ():
    dates = pd.to_datetime(["2020-01-31", "2020-02-29"])
    weights = pd.DataFrame({"AAA": [1.0, 0.0], "BBB": [0.0, 1.0]}, index=dates)
    published = pd.DataFrame({"date": ["2020-01-31", "2020-02-29"], "ticker": ["AAA", "AAA"]})
    assert holdings_differences(weights, published) == ["2020-02"]


def test_study_periods_are_the_registered_windows():
    periods = study_periods()
    assert list(periods) == [NEW_TEST, RE_TEST, FULL_PERIOD]
    assert [len(d) for d in periods.values()] == [108, 68, 176]
    assert periods[NEW_TEST][-1] == pd.Timestamp("2020-12-31")
    assert periods[RE_TEST][0] == pd.Timestamp("2021-01-31")


def test_period_labels_put_each_month_in_new_test_or_re_test():
    labels = period_labels(pd.to_datetime(["2020-12-31", "2021-01-31"]))
    assert labels.tolist() == [NEW_TEST, RE_TEST]


def test_universe_note_states_the_required_points():
    for phrase in ("available data", "survivorship", "zero in every month",
                   "delisted names have no price history", "no delistings occurred"):
        assert phrase in UNIVERSE_NOTE
    assert "—" not in UNIVERSE_NOTE


def test_counts_frame_keeps_the_momentum_layout():
    dates = pd.to_datetime(["2020-12-31", "2021-01-31"])
    counts = pd.DataFrame({"usable": [300, 301], "no_return": [0, 1]}, index=dates)
    frame = counts_frame(counts, pd.DataFrame({"members": [500, 501]}), "momentum")
    assert list(frame.columns) == ["date", "period", "universe_size", "usable_momentum", "no_return_momentum"]
    assert frame["period"].tolist() == [NEW_TEST, RE_TEST]
    assert frame["universe_size"].tolist() == [500, 501]


def test_counts_frame_names_its_columns_after_the_label():
    counts = pd.DataFrame({"usable": [300], "no_return": [0]}, index=pd.to_datetime(["2020-12-31"]))
    frame = counts_frame(counts, pd.DataFrame({"members": [500]}), "value_combined")
    assert frame["usable_value_combined"].tolist() == [300]
    assert frame["no_return_value_combined"].tolist() == [0]


def test_series_frame_keeps_the_momentum_layout():
    series = pd.Series([0.1, 0.2], index=pd.to_datetime(["2020-12-31", "2021-01-31"]))
    frame = series_frame(series, "Momentum", "rank_ic")
    assert list(frame.columns) == ["date", "period", "signal", "rank_ic"]
    assert frame["signal"].tolist() == ["Momentum", "Momentum"]
    assert frame["rank_ic"].tolist() == [0.1, 0.2]
