"""
Tests for three small fixes, all built by hand.

C2  annualized_return drops missing months before it compounds and counts months.
C4  run_backtest refuses a held name with no return instead of counting it as 0%.
C12 get_price_history_multi raises when the vendor returns nothing for a ticker.
"""
import importlib
import sys
import types

import numpy as np
import pandas as pd
import pytest

from src.backtest import run_backtest
from src.risk import annualized_return, sharpe_ratio


def test_annualized_return_ignores_a_missing_month_in_both_product_and_count():
    with_gap = pd.Series([0.10, np.nan, 0.10, 0.10, 0.10, 0.10])
    without_gap = with_gap.dropna()
    assert annualized_return(with_gap) == pytest.approx(annualized_return(without_gap))


def test_annualized_return_hand_value():
    # Five months of +10%: 1.1^5 compounded over 5/12 of a year -> 1.1^12 - 1.
    assert annualized_return(pd.Series([0.10] * 5)) == pytest.approx(1.1 ** 12 - 1)
    assert annualized_return(pd.Series([0.10, np.nan, 0.10, 0.10, 0.10, 0.10])) == pytest.approx(1.1 ** 12 - 1)


def test_sharpe_is_unchanged_by_a_missing_month():
    clean = pd.Series([0.02, -0.01, 0.03, 0.01])
    gap = pd.Series([0.02, np.nan, -0.01, 0.03, 0.01])
    assert sharpe_ratio(gap) == pytest.approx(sharpe_ratio(clean))


def _weights_and_returns():
    dates = pd.date_range("2021-01-31", periods=3, freq="ME")
    weights = pd.DataFrame({"AAA": [0.5, 0.5, 0.0], "BBB": [0.5, 0.5, 0.0]}, index=dates)
    returns = pd.DataFrame({"AAA": [0.10, 0.10, 0.10], "BBB": [0.00, 0.00, np.nan]}, index=dates)
    return weights, returns


def test_run_backtest_still_works_and_ignores_missing_return_on_unheld_name():
    weights, returns = _weights_and_returns()
    result = run_backtest(weights, returns)
    assert result.tolist() == pytest.approx([0.05, 0.05, 0.0])


def test_run_backtest_refuses_a_held_name_with_no_return():
    weights, returns = _weights_and_returns()
    returns.loc[returns.index[1], "BBB"] = np.nan
    with pytest.raises(ValueError, match=r"BBB on 2021-02-28"):
        run_backtest(weights, returns)


def _load_data_loader(monkeypatch, columns):
    """Import src.data_loader against a stand-in yfinance, so the test needs no network and no yfinance install."""
    def download(tickers, start, end, auto_adjust):
        index = pd.date_range("2021-01-01", periods=3, freq="D")
        frame = pd.DataFrame(columns, index=index)
        frame.columns = pd.MultiIndex.from_product([["Adj Close"], frame.columns])
        return frame
    stub = types.ModuleType("yfinance")
    stub.download = download
    monkeypatch.setitem(sys.modules, "yfinance", stub)
    monkeypatch.delitem(sys.modules, "src.data_loader", raising=False)
    return importlib.import_module("src.data_loader")


def test_price_history_multi_returns_prices_when_every_ticker_has_data(monkeypatch):
    loader = _load_data_loader(monkeypatch, {"AAA": [1.0, 2.0, 3.0], "BBB": [4.0, 5.0, 6.0]})
    prices = loader.get_price_history_multi(["AAA", "BBB"], "2021-01-01", "2021-01-04")
    assert list(prices.columns) == ["AAA", "BBB"]


def test_price_history_multi_raises_when_one_ticker_is_all_missing(monkeypatch):
    loader = _load_data_loader(monkeypatch, {"AAA": [1.0, 2.0, 3.0], "BBB": [np.nan] * 3})
    with pytest.raises(ValueError, match=r"\['BBB'\]"):
        loader.get_price_history_multi(["AAA", "BBB"], "2021-01-01", "2021-01-04")


def test_price_history_multi_raises_when_a_ticker_column_is_absent(monkeypatch):
    loader = _load_data_loader(monkeypatch, {"AAA": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError, match=r"\['BBB'\]"):
        loader.get_price_history_multi(["AAA", "BBB"], "2021-01-01", "2021-01-04")
