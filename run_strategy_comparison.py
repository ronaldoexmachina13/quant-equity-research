import json

import pandas as pd

from config import UNIVERSE
from src.factors import (
    load_prices,
    calculate_momentum,
    calculate_value_score,
    calculate_combined_score,
)
from src.database import load_book_value, save_portfolio_weights, save_performance
from src.portfolio import build_portfolio
from src.backtest import calculate_monthly_returns, run_backtest, calculate_benchmark_returns
from src.risk import summarize_risk


def compute_all_scores(prices: pd.DataFrame, book_value: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Build Momentum, Value, and Combined factor scores from the same
    underlying prices and book value data used elsewhere in the project.

    Returns
    -------
    dict[str, pd.DataFrame]
        {"Momentum": ..., "Value": ..., "Combined": ...}, each in the
        same wide-format shape as calculate_momentum()'s output.
    """
    momentum = calculate_momentum(prices)
    value = calculate_value_score(prices, book_value)
    combined = calculate_combined_score(momentum, value)
    return {"Momentum": momentum, "Value": value, "Combined": combined}


def backtest_strategy(score_df: pd.DataFrame, monthly_returns: pd.DataFrame, top_n: int = 5) -> pd.Series:
    """
    Build a top-N portfolio from a factor score and simulate its returns.

    Only returns dates where the portfolio actually held positions
    (weights.sum(axis=1) > 0) -- same rule backtest.py already used for
    the momentum-only case, applied consistently here to every strategy.
    """
    weights = build_portfolio(score_df, top_n=top_n)
    valid_dates = weights[weights.sum(axis=1) > 0].index
    return run_backtest(weights, monthly_returns).loc[valid_dates]


def backtest_strategy_with_weights(score_df: pd.DataFrame, monthly_returns: pd.DataFrame, top_n: int = 5):
    """
    Same as backtest_strategy(), but also returns the weights DataFrame
    restricted to the same valid_dates. Needed so the actual month-by-month
    holdings can be persisted to the database (see save_portfolio_weights()
    in __main__), not just the resulting return series -- backtest_strategy()
    itself is left unchanged since it's also used for the top-8 concentration
    check below, which is a separate what-if scenario and isn't persisted.

    Returns
    -------
    (pd.Series, pd.DataFrame)
        Strategy returns, and the weights DataFrame over the same valid dates.
    """
    weights = build_portfolio(score_df, top_n=top_n)
    valid_dates = weights[weights.sum(axis=1) > 0].index
    returns = run_backtest(weights, monthly_returns).loc[valid_dates]
    return returns, weights.loc[valid_dates]


def compare_within_period(strategy_returns: dict, benchmark_returns: pd.Series, start: str, end: str) -> pd.DataFrame:
    """
    Re-run the risk summary for every strategy and the benchmark, but
    restricted to a specific sub-period (e.g. "2021-01-01" to "2022-12-31").

    This answers a different question than the full-period table above:
    not "which strategy wins on average," but "does the full-period
    winner still win if I only look at this slice of time." Re-slicing
    existing return series (rather than rebuilding portfolios from
    scratch for the sub-period) is deliberate: it keeps this a true
    subset of the exact same full-period backtest, not a separate signal
    computed with different history.
    """
    results = []
    for name, r in strategy_returns.items():
        sliced = r.loc[start:end]
        results.append(summarize_risk(sliced, name))

    sliced_benchmark = benchmark_returns.loc[start:end]
    results.append(summarize_risk(sliced_benchmark, "Benchmark"))

    df = pd.DataFrame(results).set_index("label")
    return df[["total_return", "annualized_return", "annualized_volatility", "sharpe_ratio", "max_drawdown"]]


def backtest_all_strategies(scores: dict, monthly_returns: pd.DataFrame, top_n: int) -> tuple[dict, pd.DatetimeIndex]:
    """
    Run backtest_strategy() for every factor score in `scores` at a given
    concentration (top_n), and find the dates common to all of them --
    same fairness rule as the top-5 comparison above, generalized to any
    top_n so it can be reused for the concentration check below.
    """
    returns = {name: backtest_strategy(score_df, monthly_returns, top_n=top_n)
               for name, score_df in scores.items()}
    common = None
    for r in returns.values():
        common = r.index if common is None else common.intersection(r.index)
    return returns, common


def build_weights_long_df(strategy_weights: dict, common_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Reshape {strategy_name: wide-format weights DataFrame} into a single
    long-format DataFrame (date, ticker, strategy, weight), restricted to
    common_dates and to actual holdings only (weight > 0), ready for
    save_portfolio_weights(). Zero-weight rows are dropped deliberately --
    storing "0% weight" for every non-held ticker every month would make
    the table roughly 17x larger than the strategies.html Portfolio Timeline
    actually needs, for no analytical benefit.
    """
    frames = []
    for name, weights_df in strategy_weights.items():
        w = weights_df.loc[common_dates].reset_index()
        w.columns = ["date"] + list(w.columns[1:])
        w = w.melt(id_vars="date", var_name="ticker", value_name="weight")
        w = w[w["weight"] > 0]
        w["strategy"] = name.lower()
        frames.append(w[["date", "ticker", "strategy", "weight"]])
    return pd.concat(frames, ignore_index=True)


def build_performance_long_df(strategy_returns: dict, benchmark_returns: pd.Series,
                               common_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Reshape {strategy_name: return series} plus the benchmark return series
    into a single long-format DataFrame (date, strategy, portfolio_value,
    daily_return), ready for save_performance(). portfolio_value is
    reconstructed from the return series as a cumulative-growth-of-$1 index
    (1 + r).cumprod() -- there's no separately tracked dollar value anywhere
    upstream, and this is the standard way to turn a return series back into
    a value series for charting/drawdown purposes.
    """
    frames = []
    for name, r in strategy_returns.items():
        r_common = r.loc[common_dates]
        frames.append(pd.DataFrame({
            "date": r_common.index,
            "strategy": name.lower(),
            "portfolio_value": (1 + r_common).cumprod().values,
            "daily_return": r_common.values,
        }))

    frames.append(pd.DataFrame({
        "date": benchmark_returns.index,
        "strategy": "benchmark",
        "portfolio_value": (1 + benchmark_returns).cumprod().values,
        "daily_return": benchmark_returns.values,
    }))

    df = pd.concat(frames, ignore_index=True)
    df["date"] = df["date"].astype(str)
    return df


if __name__ == "__main__":
    prices = load_prices()
    book_value = load_book_value()
    monthly_returns = calculate_monthly_returns(prices)

    scores = compute_all_scores(prices, book_value)

    strategy_returns = {}
    strategy_weights = {}
    for name, score_df in scores.items():
        returns, weights = backtest_strategy_with_weights(score_df, monthly_returns, top_n=5)
        strategy_returns[name] = returns
        strategy_weights[name] = weights

    # Restrict every strategy AND the benchmark to the dates where ALL
    # THREE strategies have a valid portfolio -- otherwise Value (which
    # has less usable history than Momentum, since book value coverage
    # starts later/thinner than price history) would be compared over a
    # different, longer window than Momentum and Combined, making the
    # "which strategy wins" comparison unfair.
    common_dates = strategy_returns["Momentum"].index
    for r in strategy_returns.values():
        common_dates = common_dates.intersection(r.index)

    benchmark_returns = calculate_benchmark_returns(monthly_returns).loc[common_dates]

    print(f"Comparison period: {common_dates.min().date()} to {common_dates.max().date()} "
          f"({len(common_dates)} months, common to all strategies)\n")

    # Facts about the backtest itself (universe size, date range, month
    # count) that index.html's summary stats need but that don't live in
    # any of the per-strategy CSVs -- saved here, once, at the source,
    # rather than left for a human to count and type in by hand.
    metadata = {
        "n_stocks": len(UNIVERSE),
        "n_months": len(common_dates),
        "start_date": str(common_dates.min().date()),
        "end_date": str(common_dates.max().date()),
    }
    with open("results/backtest_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    results = []
    for name, r in strategy_returns.items():
        results.append(summarize_risk(r.loc[common_dates], name))
    results.append(summarize_risk(benchmark_returns, "Benchmark"))

    summary_df = pd.DataFrame(results).set_index("label")
    summary_df = summary_df[["total_return", "annualized_return", "annualized_volatility", "sharpe_ratio", "max_drawdown"]]

    print(summary_df.round(3))

    summary_df.to_csv("results/strategy_comparison_full_period.csv")
    print("\nSaved to results/strategy_comparison_full_period.csv")

    strategy_returns_common = {name: r.loc[common_dates] for name, r in strategy_returns.items()}

    print("\n\n--- 2021-2022 ---")
    period_1 = compare_within_period(strategy_returns_common, benchmark_returns, "2021-01-01", "2022-12-31")
    print(period_1.round(3))
    period_1.to_csv("results/strategy_comparison_2021_2022.csv")

    print("\n--- 2023-2024 ---")
    period_2 = compare_within_period(strategy_returns_common, benchmark_returns, "2023-01-01", "2024-12-31")
    print(period_2.round(3))
    period_2.to_csv("results/strategy_comparison_2023_2024.csv")

    # --- Persist portfolio weights and performance to the database (Tier B) ---
    # Only the headline top-5 run is persisted here. The top-8 concentration
    # check further below is a separate what-if scenario -- not what the rest
    # of the dashboard (or the SQL turnover/regime queries) report on -- so
    # its weights and returns aren't written back to the database.
    # Note: benchmark weights aren't persisted, only benchmark performance.
    # calculate_benchmark_returns() doesn't expose a per-ticker weights
    # DataFrame the way build_portfolio() does for the active strategies,
    # and the turnover/overlap SQL queries only need momentum/value/combined
    # holdings anyway (the benchmark isn't a "pick," it's just holding
    # everything, so there's no turnover or overlap question to ask of it).
    all_weights_df = build_weights_long_df(strategy_weights, common_dates)
    save_portfolio_weights(all_weights_df)

    performance_df = build_performance_long_df(strategy_returns, benchmark_returns, common_dates)
    save_performance(performance_df)

    print("\n\n=== Concentration check: top-5 vs top-8 ===")

    returns_top8, common_dates_8 = backtest_all_strategies(scores, monthly_returns, top_n=8)
    benchmark_top8 = calculate_benchmark_returns(monthly_returns).loc[common_dates_8]

    concentration_rows = []
    for name in ["Momentum", "Value", "Combined"]:
        concentration_rows.append(summarize_risk(strategy_returns[name].loc[common_dates], f"{name} (top-5)"))
        concentration_rows.append(summarize_risk(returns_top8[name].loc[common_dates_8], f"{name} (top-8)"))
    concentration_rows.append(summarize_risk(benchmark_returns, "Benchmark (top-5 dates)"))
    concentration_rows.append(summarize_risk(benchmark_top8, "Benchmark (top-8 dates)"))

    concentration_df = pd.DataFrame(concentration_rows).set_index("label")
    concentration_df = concentration_df[["annualized_return", "annualized_volatility", "sharpe_ratio", "max_drawdown"]]
    print(concentration_df.round(3))

    concentration_df.to_csv("results/strategy_comparison_concentration.csv")
    print("\nSaved to results/strategy_comparison_concentration.csv")
