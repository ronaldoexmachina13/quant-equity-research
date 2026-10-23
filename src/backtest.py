import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import brentq

from src.factors import load_prices, calculate_momentum
from src.portfolio import build_portfolio
from src.risk import summarize_risk, sharpe_ratio


def calculate_monthly_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Month-end simple returns for each ticker."""
    monthly_prices = prices.resample("ME").last()
    return monthly_prices.pct_change()


def run_backtest(weights: pd.DataFrame, returns: pd.DataFrame) -> pd.Series:
    """
    Simulate strategy returns: weight[t] applied to return[t] (same index),
    valid because momentum's skip-month already lags the signal appropriately.
    """
    common_dates = weights.index.intersection(returns.index)
    w = weights.loc[common_dates]
    r = returns.loc[common_dates]
    return (w * r).sum(axis=1)


def calculate_benchmark_returns(returns: pd.DataFrame) -> pd.Series:
    """Equal-weight return across all tickers — our passive comparison."""
    return returns.mean(axis=1)


def calculate_cumulative(returns: pd.Series) -> pd.Series:
    return (1 + returns).cumprod() - 1

def calculate_turnover(weights: pd.DataFrame) -> pd.Series:
    """
    Fraction of the portfolio actually traded each month.

    For every month except the first, this is half the sum of absolute
    weight changes from the prior month -- using half, not the full sum,
    avoids double-counting, since selling 20% of the book and buying a
    different 20% is one 20% re-positioning, not 40% of trading.

    The very first month is a special case: there's no prior portfolio
    to compare against, since the strategy is starting from cash, not
    rebalancing an existing position. That means the ENTIRE portfolio
    is pure buying with no offsetting sells, so its turnover is the
    full invested weight, not half of it.
    """
    prior = weights.shift(1)
    diff = (weights - prior.fillna(0)).abs().sum(axis=1)
    turnover = 0.5 * diff
    first_valid = weights.index[0]
    turnover.loc[first_valid] = weights.loc[first_valid].sum()
    return turnover


def apply_transaction_costs(returns: pd.Series, turnover: pd.Series, cost_bps: float = 10) -> pd.Series:
    """
    Deduct a flat transaction cost from each month's return, proportional
    to how much of the portfolio was actually traded that month.

    cost_bps is a ONE-WAY cost in basis points (default 10 = 0.10%) --
    a standard, slightly conservative assumption for large, liquid US
    equities like this project's universe: mostly bid-ask spread, with
    negligible commission at today's near-zero equity brokerage rates.
    Turnover already represents a symmetric buy+sell re-positioning
    (except the special first-month case), so the cost is applied
    twice per unit of turnover -- once for the selling leg, once for
    the buying leg.
    """
    cost_rate = cost_bps / 10000
    cost_drag = turnover * cost_rate * 2
    return returns - cost_drag


# ---------------------------------------------------------------------------
# Cost sensitivity (LIMITATIONS_PLAN.md, Phase 1B and Amendment 2).
# ---------------------------------------------------------------------------

def equal_weight_targets(asset_returns: pd.DataFrame) -> pd.DataFrame:
    """
    The weights the equal-weight benchmark holds each month: 1/N across
    the tickers with a return that month, 0 for the rest. This is the
    portfolio calculate_benchmark_returns() implicitly holds, since
    returns.mean(axis=1) skips missing values.
    """
    available = asset_returns.notna().astype(float)
    return available.div(available.sum(axis=1), axis=0)


def calculate_turnover_with_drift(target_weights: pd.DataFrame, asset_returns: pd.DataFrame) -> pd.Series:
    """
    Turnover that also counts the trades needed to bring held names back
    to their target weights after prices move (Amendment 2, item 2).

    run_backtest() applies weights dated t to the return dated t, the
    return earned during month t. So the portfolio entering month t is the
    month t-1 target, grown by the month t-1 returns and renormalised. That
    pre-trade portfolio is compared with the month t target; only returns
    up to t-1 are used, so there is no look-ahead.

    Missing returns are treated as 0. The first month is a purchase from
    cash, as in calculate_turnover(), so its turnover is the full weight.
    calculate_turnover() is the special case where prices do not move.
    """
    weights = target_weights.fillna(0)
    returns = asset_returns.reindex(index=weights.index, columns=weights.columns).fillna(0)
    grown = weights.shift(1) * (1 + returns.shift(1))
    pre_trade = grown.div(grown.sum(axis=1), axis=0)
    turnover = 0.5 * (weights - pre_trade).abs().sum(axis=1)
    first_valid = weights.index[0]
    turnover.loc[first_valid] = weights.loc[first_valid].sum()
    return turnover


def find_break_even_cost(strat_gross: pd.Series, strat_turnover: pd.Series,
                         bench_gross: pd.Series, bench_turnover: pd.Series,
                         max_bps: float = 50, step_bps: float = 0.01) -> dict:
    """
    One-way cost (bps) at which the strategy's Sharpe equals the
    benchmark's, both net of the same cost, on the flat 2% basis
    (Amendment 2, item 3).

    Scans 0 to max_bps in steps of step_bps for a change of sign in
    Sharpe(strategy) - Sharpe(benchmark), then pins each crossing down
    with Brent's method. Returns {"crossings_bps": [...], "note": str}.
    With no crossing the note is "below benchmark at 0 bps" or "above
    benchmark at 50 bps", as registered.
    """
    def gap(cost_bps: float) -> float:
        strat = sharpe_ratio(apply_transaction_costs(strat_gross, strat_turnover, cost_bps))
        bench = sharpe_ratio(apply_transaction_costs(bench_gross, bench_turnover, cost_bps))
        return strat - bench

    grid = np.linspace(0, max_bps, int(round(max_bps / step_bps)) + 1)
    gaps = np.array([gap(c) for c in grid])

    crossings = []
    for i in range(len(grid) - 1):
        if gaps[i] == 0:
            crossings.append(float(grid[i]))
        elif gaps[i] * gaps[i + 1] < 0:
            crossings.append(float(brentq(gap, grid[i], grid[i + 1], xtol=1e-10)))
    if gaps[-1] == 0:
        crossings.append(float(grid[-1]))

    if crossings:
        direction = "falls to" if gaps[0] > 0 else "rises to"
        note = f"strategy Sharpe {direction} the benchmark's within 0 to {max_bps:g} bps"
    elif gaps[0] < 0:
        note = "below benchmark at 0 bps"
    else:
        note = f"above benchmark at {max_bps:g} bps"
    return {"crossings_bps": crossings, "note": note}


# ---------------------------------------------------------------------------
# Quarterly rebalancing (LIMITATIONS_PLAN.md, Phase 2 detailed design).
# ---------------------------------------------------------------------------

def hold_between_refreshes(target_weights: pd.DataFrame, asset_returns: pd.DataFrame,
                           refresh_months: tuple = (1, 4, 7, 10)) -> pd.DataFrame:
    """
    The weights actually held at the start of each month when the selection
    is only refreshed in refresh_months (January, April, July and October by
    default) and positions are carried, drifting with prices, in between.

    - Refresh month t: held weights are that month's target (whose signal,
      as in the monthly path, uses information up to t-1).
    - Other months: the previous month's held weights, grown by the previous
      month's returns and renormalised, w_t = w_{t-1}(1 + r_{t-1}) / sum.
      This is buy-and-hold over the quarter. Missing returns count as 0, as
      in calculate_turnover_with_drift() and run_backtest().

    Feeding the result to run_backtest() gives the returns, and to
    calculate_turnover_with_drift() gives turnover that is exactly zero in
    non-refresh months. Refreshing in every month returns the targets.
    """
    targets = target_weights.fillna(0)
    returns = asset_returns.reindex(index=targets.index, columns=targets.columns).fillna(0)
    if targets.index[0].month not in refresh_months:
        raise ValueError(f"The first month ({targets.index[0].date()}) must be a refresh month.")

    held = pd.DataFrame(0.0, index=targets.index, columns=targets.columns)
    previous_date = None
    for date in targets.index:
        if date.month in refresh_months:
            row = targets.loc[date]
            if row.sum() <= 0:
                raise ValueError(f"No valid target portfolio in refresh month {date.date()}.")
        else:
            grown = held.loc[previous_date] * (1 + returns.loc[previous_date])
            row = grown / grown.sum()
        held.loc[date] = row
        previous_date = date
    return held


if __name__ == "__main__":
    prices = load_prices()
    momentum = calculate_momentum(prices)
    weights = build_portfolio(momentum, top_n=5)
    monthly_returns = calculate_monthly_returns(prices)

    # Only evaluate dates where the portfolio is actually populated
    valid_dates = weights[weights.sum(axis=1) > 0].index

    strategy_returns = run_backtest(weights, monthly_returns).loc[valid_dates]
    benchmark_returns = calculate_benchmark_returns(monthly_returns).loc[valid_dates]

    strategy_cum = calculate_cumulative(strategy_returns)
    benchmark_cum = calculate_cumulative(benchmark_returns)

    print(f"Backtest period: {valid_dates.min().date()} to {valid_dates.max().date()}")
    print(f"Strategy total return:  {strategy_cum.iloc[-1]:.1%}")
    print(f"Benchmark total return: {benchmark_cum.iloc[-1]:.1%}")

    plt.figure(figsize=(10, 5))
    strategy_stats = summarize_risk(strategy_returns, "Momentum Strategy")
    benchmark_stats = summarize_risk(benchmark_returns, "Equal-Weight Benchmark")

    print("\n--- Risk-Adjusted Comparison ---")
    for stats in [strategy_stats, benchmark_stats]:
        print(f"\n{stats['label']}:")
        print(f"  Annualized Return:     {stats['annualized_return']:.1%}")
        print(f"  Annualized Volatility: {stats['annualized_volatility']:.1%}")
        print(f"  Sharpe Ratio:          {stats['sharpe_ratio']:.2f}")
        print(f"  Max Drawdown:          {stats['max_drawdown']:.1%}")
    