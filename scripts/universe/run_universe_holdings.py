"""
Holdings and per-stock summary of the large-universe study, for the dashboard.

This adds no new test and changes no result. It rebuilds the top-decile
portfolios of run_universe_portfolios.py with the same functions and the same
inputs, and writes down which names each portfolio held each month. Before
anything is written it checks that the rebuilt gross returns and number of
names held equal the committed results/universe_study_portfolio_returns.csv
in every month, so the holdings are the ones behind the reported results.

Outputs are new files, never overwritten (mode "x"):
  results/universe_study_holdings.csv        one row per month, strategy and held name
  results/universe_study_stock_summary.csv   one row per ticker ever in the index

Run after run_universe_portfolios.py:
  python run_universe_holdings.py
"""
import sqlite3

import pandas as pd

from scripts.universe.run_universe_gates import run_gate2, run_gate1a_momentum, run_count_check, run_value_path, stop_on_failures
from scripts.universe.run_universe_signals import load_inputs, stop_if_outputs_exist
from src.backtest import calculate_monthly_returns
from src.universe import FEASIBILITY_DB_PATH, survivor_group
from src.universe_study import read_month_end_prices
from src.universe_value import signal_sets, HEADLINE
from src.universe_portfolio import top_group_weights, held_returns

STRATEGIES = ["Momentum", "Value", "Combined"]
DECILE = 10
RETURNS_PATH = "results/universe_study_portfolio_returns.csv"
MEMBERSHIP_PATH = "results/universe_membership.csv"
OUTPUTS = {
    "holdings": "results/universe_study_holdings.csv",
    "stock_summary": "results/universe_study_stock_summary.csv",
}
TOLERANCE = 1e-9


def check_against_committed(weights: dict, returns: pd.DataFrame) -> list[str]:
    """Rebuilt gross return and names held equal the committed portfolio_returns file, every month."""
    committed = pd.read_csv(RETURNS_PATH, parse_dates=["date"])
    failures = []
    for strategy in STRATEGIES:
        saved = committed[(committed["strategy"] == strategy) & (committed["size"] == "top_decile")].set_index("date")
        rebuilt = held_returns(weights[strategy], returns).reindex(saved.index)
        held = (weights[strategy] > 0).sum(axis=1).reindex(saved.index)
        gap = (rebuilt - saved["gross"]).abs().max()
        if not gap < TOLERANCE:
            failures.append(f"{strategy}: gross return differs from the committed file by up to {gap}")
        if not (held == saved["names_held"]).all():
            failures.append(f"{strategy}: names held differ from the committed file")
        print(f"  {strategy}: {len(saved)} months, largest gross difference {gap:.2e}")
    return failures


def holdings_frame(weights: dict, signals: dict, returns: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    parts = []
    for strategy in STRATEGIES:
        w = weights[strategy].loc[dates]
        held = w.where(w > 0).stack().dropna()  # pandas 3 keeps empty cells in stack()
        frame = held.rename("weight").reset_index()
        frame.columns = ["date", "ticker", "weight"]
        frame["score"] = [signals[strategy].at[d, t] for d, t in zip(frame["date"], frame["ticker"])]
        frame["return"] = [returns.at[d, t] for d, t in zip(frame["date"], frame["ticker"])]
        frame["contribution"] = frame["weight"] * frame["return"]
        frame.insert(1, "strategy", strategy)
        parts.append(frame)
    out = pd.concat(parts, ignore_index=True)
    counts = out.groupby(["date", "strategy"]).size()
    committed = pd.read_csv(RETURNS_PATH, parse_dates=["date"])
    committed = committed[committed["size"] == "top_decile"].set_index(["date", "strategy"])["names_held"]
    bad = (counts.reindex(committed.index).fillna(0) != committed).sum()
    if bad or len(out) != int(committed.sum()):
        raise SystemExit(f"Holdings rows do not match the committed names held ({bad} months differ). Stopping.")
    out["date"] = out["date"].dt.strftime("%Y-%m")
    return out


def stock_summary(holdings: pd.DataFrame, signals: dict, returns: pd.DataFrame, dates: pd.DatetimeIndex,
                  price_tickers: list[str]) -> pd.DataFrame:
    members = pd.read_csv(MEMBERSHIP_PATH)
    conn = sqlite3.connect(f"file:{FEASIBILITY_DB_PATH}?mode=ro", uri=True)
    intervals = pd.read_sql_query("SELECT * FROM index_membership", conn)
    conn.close()
    out = members[["ticker", "company", "gics_sector", "start_date", "end_date"]].drop_duplicates("ticker").copy()
    out["group"] = [survivor_group(intervals, t) for t in out["ticker"]]
    out["has_price_history"] = out["ticker"].isin(price_tickers)
    usable_m = signals["Momentum"].loc[dates].notna().sum()
    usable_v = signals["Value"].loc[dates].notna().sum()
    out["months_usable_momentum"] = out["ticker"].map(usable_m).fillna(0).astype(int)
    out["months_usable_value"] = out["ticker"].map(usable_v).fillna(0).astype(int)
    avg_ret = returns.loc[dates].where(signals["Momentum"].loc[dates].notna()).mean()
    out["avg_monthly_return"] = out["ticker"].map(avg_ret)
    for strategy in STRATEGIES:
        h = holdings[holdings["strategy"] == strategy]
        key = strategy.lower()
        out[f"months_held_{key}"] = out["ticker"].map(h.groupby("ticker").size()).fillna(0).astype(int)
        out[f"contribution_{key}"] = out["ticker"].map(h.groupby("ticker")["contribution"].sum())
    return out.sort_values("ticker")


def main():
    stop_if_outputs_exist(OUTPUTS.values())
    calendar, usability = load_inputs()
    run_gate2(calendar)
    prices = read_month_end_prices(calendar)
    run_gate1a_momentum(prices, usability)
    run_count_check(prices, usability)
    path = run_value_path(calendar, prices, usability)

    returns = calculate_monthly_returns(prices)
    signals = signal_sets(path["momentum"], path["value"])[HEADLINE]
    weights = {s: top_group_weights(signals[s], DECILE) for s in STRATEGIES}

    print("\nCheck against the committed portfolio returns:")
    stop_on_failures("Holdings check", check_against_committed(weights, returns))

    dates = pd.read_csv(RETURNS_PATH, parse_dates=["date"])["date"].drop_duplicates().sort_values()
    dates = pd.DatetimeIndex(dates)
    holdings = holdings_frame(weights, signals, returns, dates)
    stocks = stock_summary(holdings, signals, returns, dates, list(prices.columns))

    stop_if_outputs_exist(OUTPUTS.values())
    for name, frame in {"holdings": holdings, "stock_summary": stocks}.items():
        frame.to_csv(OUTPUTS[name], index=False, mode="x")
        print(f"Wrote {OUTPUTS[name]} ({len(frame)} rows)")


if __name__ == "__main__":
    main()
