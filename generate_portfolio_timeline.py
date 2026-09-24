import json

import pandas as pd

from config import IN_SAMPLE_END, OUT_OF_SAMPLE_START, OUT_OF_SAMPLE_END

from src.database import load_book_value
from src.factors import load_prices, calculate_momentum, calculate_value_score, calculate_combined_score
from src.portfolio import build_portfolio
from src.backtest import calculate_monthly_returns, run_backtest
from src.risk import rolling_sharpe, rolling_volatility

STRATEGY_KEYS = {"Momentum": "momentum", "Value": "value", "Combined": "combined"}


def export_timeline(weights: pd.DataFrame, monthly_returns: pd.DataFrame, window: int = 12,
                    cumulative_from: str = None):
    """
    Compute holdings, per-stock contributions, and rolling metrics for
    one strategy, over the exact dates already present in `weights`.

    `weights` is expected to already be restricted to the dates common
    to every strategy (see __main__) -- this function doesn't decide
    which dates to include, it just computes over whatever it's given.

    Returns three dicts, each keyed by "YYYY-MM":
      - holdings: which tickers were held each month
      - contributions: each held stock's own return and its contribution
        to the portfolio's return that month, ranked highest to lowest
      - metrics: monthly return, cumulative return, and trailing
        `window`-month rolling Sharpe/volatility, using true geometric
        compounding (None for the first `window - 1` months, which
        don't have enough history yet)

    If `cumulative_from` is given, cumulative return is measured from that
    date onward (used to restart it at the start of the out-of-sample
    period); rolling metrics still use the full trailing window.
    """
    portfolio_returns = run_backtest(weights, monthly_returns).loc[weights.index]

    cum_returns = portfolio_returns if cumulative_from is None else portfolio_returns[portfolio_returns.index >= cumulative_from]
    cumulative = (1 + cum_returns).cumprod() - 1
    sharpe = rolling_sharpe(portfolio_returns, window=window)
    vol = rolling_volatility(portfolio_returns, window=window)

    holdings, contributions, metrics = {}, {}, {}

    for date in weights.index:
        date_str = date.strftime("%Y-%m")
        w = weights.loc[date]
        held_tickers = w[w > 0].index.tolist()
        holdings[date_str] = held_tickers

        rows = []
        for t in held_tickers:
            stock_ret = float(monthly_returns.loc[date, t]) * 100
            contrib = float(w[t]) * float(monthly_returns.loc[date, t]) * 100
            rows.append({"ticker": t, "return": round(stock_ret, 2), "contribution": round(contrib, 2)})
        rows.sort(key=lambda r: r["contribution"], reverse=True)
        contributions[date_str] = rows

        s = sharpe.loc[date]
        v = vol.loc[date]
        metrics[date_str] = {
            "return": round(float(portfolio_returns.loc[date]) * 100, 2),
            "cumulative": round(float(cumulative.loc[date]) * 100, 2) if date in cumulative.index else None,
            "sharpe": None if pd.isna(s) else round(float(s), 2),
            "volatility": None if pd.isna(v) else round(float(v) * 100, 2),
        }

    return holdings, contributions, metrics


if __name__ == "__main__":
    prices = load_prices()
    book_value = load_book_value()
    monthly_returns = calculate_monthly_returns(prices)

    momentum = calculate_momentum(prices)
    value = calculate_value_score(prices, book_value)
    combined = calculate_combined_score(momentum, value)
    scores = {"Momentum": momentum, "Value": value, "Combined": combined}

    # Same fairness rule as run_strategy_comparison.py: restrict every
    # strategy to the dates where ALL THREE have a valid portfolio.
    # Without this, Value (which only needs one month of book value data,
    # not 12 months like Momentum's lookback) ends up with a much longer,
    # mismatched date range than Momentum and Combined.
    raw_weights = {name: build_portfolio(s, top_n=5) for name, s in scores.items()}
    valid_by_strategy = {name: w[w.sum(axis=1) > 0].index for name, w in raw_weights.items()}
    common_dates = None
    for dates in valid_by_strategy.values():
        common_dates = dates if common_dates is None else common_dates.intersection(dates)

    # Keep only in-sample months, so newer data added for the
    # out-of-sample test cannot change these results.
    common_dates = common_dates[common_dates <= IN_SAMPLE_END]

    print(f"Common dates across all 3 strategies: {len(common_dates)} months "
          f"({common_dates.min().date()} to {common_dates.max().date()})\n")

    all_holdings, all_contributions, all_metrics = {}, {}, {}
    for name, score_df in scores.items():
        key = STRATEGY_KEYS[name]
        weights = raw_weights[name].loc[common_dates]
        h, c, m = export_timeline(weights, monthly_returns, window=12)
        all_holdings[key] = h
        all_contributions[key] = c
        all_metrics[key] = m
        print(f"{name}: {len(h)} months exported")

    with open("results/portfolio_timeline.json", "w") as f:
        json.dump({
            "holdings": all_holdings,
            "contributions": all_contributions,
            "metrics": all_metrics,
        }, f, indent=2)

    print("\nSaved to results/portfolio_timeline.json")

    # ---- Out-of-sample months (Jan 2025 - Aug 2026), saved separately ----
    # Built over the full history so that January 2025's portfolio and the
    # trailing 12-month rolling metrics use the real prior months; only the
    # out-of-sample months are then kept, with cumulative return restarted
    # at the start of the out-of-sample period.
    all_dates = None
    for dates in valid_by_strategy.values():
        all_dates = dates if all_dates is None else all_dates.intersection(dates)
    all_dates = all_dates[all_dates <= OUT_OF_SAMPLE_END]
    oos_keys = [d.strftime("%Y-%m") for d in all_dates if d >= pd.Timestamp(OUT_OF_SAMPLE_START)]

    oos = {"holdings": {}, "contributions": {}, "metrics": {}}
    for name in scores:
        key = STRATEGY_KEYS[name]
        h, c, m = export_timeline(raw_weights[name].loc[all_dates], monthly_returns, window=12,
                                  cumulative_from=OUT_OF_SAMPLE_START)
        oos["holdings"][key] = {k: h[k] for k in oos_keys}
        oos["contributions"][key] = {k: c[k] for k in oos_keys}
        oos["metrics"][key] = {k: m[k] for k in oos_keys}
    print(f"Out of sample: {len(oos_keys)} months exported ({oos_keys[0]} to {oos_keys[-1]})")

    with open("results/portfolio_timeline_oos.json", "w") as f:
        json.dump(oos, f, indent=2)
    print("Saved to results/portfolio_timeline_oos.json")