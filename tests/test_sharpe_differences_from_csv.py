"""
Check the 18 headline Sharpe differences against the saved monthly returns.

The pre-registered test compares, for each of Momentum, Value and Combined
(top decile and top quintile, three periods), the Sharpe ratio of the
portfolio with the Sharpe ratio of its equal-weight benchmark. The result
files hold both the monthly returns and the finished summary. This test
recomputes the summary from the returns, using only numpy and pandas, so a
reader can confirm the saved numbers without downloading any data. It does
not touch the network and it does not rerun the bootstrap.

Financial logic: Sharpe = (annualised return minus annualised risk-free
return) / annualised volatility. Returns are compounded, not averaged, and
the risk-free rate is the compounded Treasury bill rate over the same months.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RESULTS = Path(__file__).resolve().parent.parent / "results"
TOLERANCE = 1e-9  # the saved files agree to about 1e-15; this leaves room for platform rounding


def sharpe(monthly_returns, monthly_risk_free):
    months = len(monthly_returns)
    annual_return = np.prod(1 + monthly_returns) ** (12 / months) - 1
    annual_risk_free = np.prod(1 + monthly_risk_free) ** (12 / months) - 1
    annual_volatility = monthly_returns.std(ddof=1) * np.sqrt(12)
    return (annual_return - annual_risk_free) / annual_volatility


def months_in_period(table, period):
    """The full period is every month; the other two are named in the 'period' column."""
    if period.startswith("Full period"):
        return table
    return table[table["period"] == period]


@pytest.fixture(scope="module")
def returns():
    return pd.read_csv(RESULTS / "universe_study_portfolio_returns.csv", parse_dates=["date"])


@pytest.fixture(scope="module")
def headline_rows():
    summary = pd.read_csv(RESULTS / "universe_study_portfolio_summary.csv")
    return summary[summary["headline_test"]]


def test_there_are_18_headline_comparisons(headline_rows):
    assert len(headline_rows) == 18


def test_sharpe_differences_match_saved_summary(headline_rows, returns):
    for _, row in headline_rows.iterrows():
        portfolio = returns[(returns["strategy"] == row["strategy"]) & (returns["size"] == row["size"])]
        portfolio = months_in_period(portfolio, row["period"]).set_index("date")
        benchmark = returns[returns["strategy"] == row["benchmark"]]
        benchmark = months_in_period(benchmark, row["period"]).set_index("date")
        benchmark = benchmark.loc[portfolio.index]  # same months for both, in the same order

        label = f"{row['strategy']} {row['size']} {row['period']}"
        assert len(portfolio) == row["months"], label

        # The headline test is gross of costs, against the Treasury bill rate.
        risk_free = portfolio["rf_monthly"].to_numpy()
        portfolio_sharpe = sharpe(portfolio["gross"].to_numpy(), risk_free)
        benchmark_sharpe = sharpe(benchmark["gross"].to_numpy(), risk_free)

        assert portfolio_sharpe == pytest.approx(row["sharpe_tbill"], abs=TOLERANCE), label
        assert benchmark_sharpe == pytest.approx(row["benchmark_sharpe_tbill"], abs=TOLERANCE), label
        assert portfolio_sharpe - benchmark_sharpe == pytest.approx(row["sharpe_diff_tbill"], abs=TOLERANCE), label
