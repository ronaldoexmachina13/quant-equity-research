"""
Tests for the analytical queries in sql/ that are not part of the 500-stock
pipeline: factor_construction_in_sql.sql and portfolio_and_regime_queries.sql.

The README presents these queries as an independent check on the Python code,
so each is run here on a small hand-made database and compared with a
hand-worked answer or with the pandas function it is meant to reproduce. The
database is built with the project's own save functions in a temporary file.
"""
import re
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import src.database as database
from src.factors import calculate_momentum

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"


def statements(filename: str) -> list[str]:
    """The statements of a .sql file: comments removed, split at the semicolons, empty parts dropped."""
    text = (SQL_DIR / filename).read_text(encoding="utf-8")
    text = re.sub(r"--[^\n]*", "", text)
    return [part.strip() for part in text.split(";") if part.strip()]


@pytest.fixture
def price_database(tmp_path, monkeypatch):
    """Two tickers with daily prices on business days of 2023, and book value at each calendar month end."""
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))
    database.create_tables()
    days = pd.bdate_range("2022-01-03", "2023-12-29")
    prices = pd.DataFrame({"AAA": 100 + np.arange(len(days)) * 0.5, "BBB": 50 + np.arange(len(days)) * 0.25},
                          index=days)
    prices.index.name = "Date"
    database.save_prices(prices)
    month_ends = prices.resample("ME").last().index
    book = pd.DataFrame({"AAA": 20.0, "BBB": 10.0}, index=month_ends)
    book.index.name = "date"
    database.save_book_value(book)
    connection = sqlite3.connect(database.DB_PATH)
    yield connection, prices, book
    connection.close()


def test_sql_momentum_matches_the_pandas_signal(price_database):
    """
    Momentum is the price at the end of the previous month over the price 11
    months before that, minus 1: the same signal as calculate_momentum().
    The SQL rounds to 4 decimals, so the two agree to within 1e-4.
    """
    connection, prices, _ = price_database
    sql = pd.read_sql_query(statements("factor_construction_in_sql.sql")[0], connection)
    sql["month"] = pd.to_datetime(sql["date"]).dt.to_period("M")
    expected = calculate_momentum(prices).stack().rename("pandas").reset_index()
    expected.columns = ["month_end", "ticker", "pandas"]
    expected["month"] = expected["month_end"].dt.to_period("M")
    merged = sql.merge(expected, on=["ticker", "month"])
    assert len(merged) == 2 * 12          # 24 months of prices, signal exists from month 13 to month 24 for 2 tickers
    assert (merged["momentum_12m_to_prev_month"] - merged["pandas"]).abs().max() < 1e-4


def test_sql_price_to_book_has_a_row_for_every_month_not_only_weekday_month_ends(price_database):
    """
    Prices are dated on the last trading day and book value on the calendar
    month end. Several 2022 and 2023 month ends fall on a weekend (for example
    30 April 2023 is a Sunday), so a join on the exact date silently drops those
    months. Every month with a price must come back, with P/B = price / 20 for AAA.
    """
    connection, prices, _ = price_database
    result = pd.read_sql_query(statements("factor_construction_in_sql.sql")[1], connection)
    months_with_price = len(prices.resample("ME").last())
    assert result.groupby("ticker").size().to_dict() == {"AAA": months_with_price, "BBB": months_with_price}
    aaa = result[result["ticker"] == "AAA"]
    assert aaa["price_to_book"].tolist() == pytest.approx((aaa["adj_close"] / 20.0).round(4).tolist())


def test_sql_coverage_diagnostic_agrees_with_the_price_to_book_query(price_database):
    """Both queries must report the same months: no month is missing book value in this database."""
    connection, _, _ = price_database
    coverage = pd.read_sql_query(statements("factor_construction_in_sql.sql")[2], connection)
    assert coverage["months_missing_book_value"].tolist() == [0, 0]


def test_sql_turnover_counts_a_name_that_leaves_and_comes_back(tmp_path, monkeypatch):
    """
    Two holdings, equal weight. January A and B; February B and C (A sold, C
    bought); March A and B (A bought back, C sold). In the project's rule,
    half the sum of absolute weight changes, turnover is 1.0 in January (bought
    from cash), 0.5 in February and 0.5 in March. A query that looks only at
    the ticker's previous row would see A as held in January and in March and
    report 0 for March.
    """
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))
    database.create_tables()
    rows = [(d, t, "momentum", 0.5)
            for d, held in [("2021-01-31", "AB"), ("2021-02-28", "BC"), ("2021-03-31", "AB")] for t in held]
    database.save_portfolio_weights(pd.DataFrame(rows, columns=["date", "ticker", "strategy", "weight"]))
    connection = sqlite3.connect(database.DB_PATH)
    try:
        result = pd.read_sql_query(statements("portfolio_and_regime_queries.sql")[0], connection)
    finally:
        connection.close()
    assert result["date"].tolist() == ["2021-01-31", "2021-02-28", "2021-03-31"]
    assert result["turnover_fraction"].tolist() == pytest.approx([1.0, 0.5, 0.5])
