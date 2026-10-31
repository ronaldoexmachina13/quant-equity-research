"""
Split sensitivity on the 17 study stocks, as registered in LIMITATIONS_PLAN.md
(Amendment 8, with the base book value and Gate 2 of Amendment 9).

Value and Combined are compared in three versions, with the same top 5,
monthly rebalancing, 10 bps costs and flat 2% rate as the published study:
1. published: adjusted close over book value as filed;
2. restated_adj_close: adjusted close over restated book value, which isolates
   the effect of splits;
3. restated_close: split-adjusted close (no dividend adjustment) over restated
   book value, which also removes the dividend effect.

All three are reported whatever the result. This is a labelled sensitivity:
the published figures and the pre-registered out-of-sample test stand
unchanged. Momentum, the benchmark and all holding returns are the same in
every version; only the inputs to calculate_value_score() change.

Data: returns and the base book value of all three versions come from
database/quant_research.db, opened through the existing loaders. Each stored
monthly value is divided by the product of the splits dated after the filing
in force that month, and the cached SEC records are used only to identify that
filing. The close comes from the Phase 3 price cache. Split dates are
downloaded once from yfinance and cached. Both caches are under
UNIVERSE_CACHE_DIR.

The script stops without writing if the published series rebuilt from the
database differs from the published CSVs by more than 1e-9; if, for a stock
with an event that changes the sample, the as-filed value of the filing in
force differs from the stored value by more than 1e-6 in the months restated;
or if a stock without an event changes when restated. Differences between
cached and stored book value for other stocks are printed and do not stop the
run. Output files are new and never overwritten: if any exists the script
stops before doing anything.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

import src.fundamentals as fundamentals
from config import UNIVERSE, IN_SAMPLE_END, OUT_OF_SAMPLE_START, OUT_OF_SAMPLE_END
from src.backtest import calculate_monthly_returns, calculate_benchmark_returns, calculate_turnover, apply_transaction_costs
from src.database import load_book_value
from src.factors import load_prices, calculate_momentum, calculate_value_score, calculate_combined_score
from src.risk import summarize_risk, alpha_regression, bootstrap_sharpe_diff, sharpe_ratio
from src.split_adjust import (
    splits_from_history, restate_book_value, filled_book_value, filing_in_force, restate_stored_book_value,
)
from src.universe import (
    PRICE_START, cache_dir, make_cached_company_facts, download_with_retries, write_bytes_atomic,
)
from run_strategy_comparison import backtest_strategy_with_weights

OUTPUTS = {name: Path("results") / f"value_split_{name}.csv"
           for name in ["summary", "monthly_returns", "holdings", "pb", "events"]}

TOP_N = 5                # frozen portfolio size
COST_BPS = 10            # same one-way cost as the published study
N_SIMS = 5000
SEED = 42                # same seed as the published significance tests
EVENTS_FROM = "2019-01-01"  # earliest filing that can reach the first month end (2020-01) under the 180-day limit
LAST_DATA_DATE = "2026-08-31"

STRATEGIES = ["Momentum", "Value", "Combined"]
REVISED = ["Value", "Combined"]
PUBLISHED, RESTATED_ADJ, RESTATED_CLOSE = "published", "restated_adj_close", "restated_close"
VERSIONS = [PUBLISHED, RESTATED_ADJ, RESTATED_CLOSE]
IS_LABEL = "In sample (2021-2024)"
OOS_LABEL = "Out of sample (Jan 2025-Aug 2026)"

METRICS = ["total_return", "annualized_return", "annualized_volatility", "sharpe_ratio",
           "sortino_ratio", "max_drawdown", "beta", "alpha"]
EVENT_NOTES = {"RTX": "merger and spin-off effect, not an ordinary split; applied mechanically"}


def stop_if_outputs_exist():
    existing = [str(p) for p in OUTPUTS.values() if p.exists()]
    if existing:
        raise SystemExit(f"Output files already exist and are never overwritten: {existing}. Stopping.")


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def load_cached_close(index: pd.DatetimeIndex) -> pd.DataFrame:
    """Split-adjusted close of the 17 stocks from the Phase 3 cache, on the dates of the existing prices table."""
    columns = {}
    for ticker in UNIVERSE:
        data = pd.read_csv(cache_dir() / "prices" / f"{ticker}.csv.gz", index_col="Date", parse_dates=True)
        columns[ticker] = data["Close"].reindex(index)
    close = pd.DataFrame(columns, index=index)
    if close.isna().any(axis=None):
        raise SystemExit("The cached close has no price on some dates of the prices table. Stopping.")
    return close


def fetch_splits(ticker: str) -> pd.Series:
    """Raises if yfinance returns no history, so a failed download is never read as "no splits"."""
    history = yf.Ticker(ticker).history(start=PRICE_START, auto_adjust=False, actions=True)
    if history is None or history.empty:
        raise ValueError(f"{ticker}: empty history")
    history.index = pd.DatetimeIndex(history.index).tz_localize(None).normalize()
    return splits_from_history(history)


def load_splits() -> dict:
    """{ticker: split ratios by date}. Downloaded once; the file is written only after all 17 succeed."""
    path = cache_dir() / "reference" / "splits_study_stocks.csv"
    if not path.exists():
        yf.config.debug.hide_exceptions = False
        rows = []
        for ticker in UNIVERSE:
            status, ratios, attempts, message = download_with_retries(
                lambda: fetch_splits(ticker), lambda exc: False, missing_confirmations=1)
            if status != "ok":
                raise SystemExit(f"Split download failed for {ticker} after {attempts} attempts: {message}")
            rows.extend({"ticker": ticker, "date": d.strftime("%Y-%m-%d"), "ratio": r} for d, r in ratios.items())
        text = pd.DataFrame(rows, columns=["ticker", "date", "ratio"]).to_csv(index=False)
        write_bytes_atomic(path, text.encode("utf-8"))
        print(f"Downloaded and cached split dates: {path}")
    else:
        print(f"Using cached split dates: {path}")

    events = pd.read_csv(path, parse_dates=["date"])
    late = events[events["date"] > LAST_DATA_DATE]
    if not late.empty:
        raise SystemExit(f"Split after the last price date, not reflected consistently:\n{late}\nStopping.")
    return {t: events[events["ticker"] == t].set_index("date")["ratio"].astype(float) for t in UNIVERSE}


def load_filed_records() -> dict:
    """get_book_value_per_share() on the cached SEC facts, as in run_universe_fundamentals.py."""
    sec_dir = cache_dir() / "sec"
    fundamentals._TICKER_CIK_MAP = json.loads((sec_dir / "company_tickers_map.json").read_text(encoding="utf-8"))
    fundamentals.get_company_facts = make_cached_company_facts(fundamentals.get_cik, sec_dir / "companyfacts")
    return {ticker: fundamentals.get_book_value_per_share(ticker) for ticker in UNIVERSE}


# ---------------------------------------------------------------------------
# Strategy series
# ---------------------------------------------------------------------------

def build_version(momentum: pd.DataFrame, value: pd.DataFrame, monthly_returns: pd.DataFrame) -> dict:
    """{strategy: (gross returns, weights)} for one version of the Value inputs."""
    scores = {"Momentum": momentum, "Value": value, "Combined": calculate_combined_score(momentum, value)}
    return {name: backtest_strategy_with_weights(score, monthly_returns, top_n=TOP_N)
            for name, score in scores.items()}


def common_dates(version: dict) -> pd.DatetimeIndex:
    """Dates where all three strategies hold positions, the fairness rule of the published scripts."""
    common = None
    for returns, _ in version.values():
        common = returns.index if common is None else common.intersection(returns.index)
    return common[common <= OUT_OF_SAMPLE_END]


def period_turnover(weights: pd.DataFrame, period: str, dates: pd.DatetimeIndex, history: pd.DatetimeIndex) -> pd.Series:
    """In sample, January 2021 is a purchase from cash; out of sample, January 2025 rebalances December 2024."""
    measured_on = dates if period == IS_LABEL else history
    return calculate_turnover(weights.loc[measured_on]).loc[dates]


def strategy_row(name: str, version: str, period: str, gross: pd.Series, turnover: pd.Series,
                 benchmark: pd.Series) -> dict:
    net = apply_transaction_costs(gross, turnover, cost_bps=COST_BPS)
    regression = alpha_regression(gross, benchmark)
    diff = bootstrap_sharpe_diff(gross, benchmark, n_sims=N_SIMS, seed=SEED)
    row = {"period": period, "months": len(gross), "strategy": name, "version": version}
    stats = summarize_risk(gross, name, benchmark_returns=benchmark)
    row.update({metric: stats[metric] for metric in METRICS})
    row.update({
        "alpha_tstat": regression["alpha_tstat"],
        "alpha_pvalue": regression["alpha_pvalue"],
        "avg_monthly_turnover": turnover.mean(),
        "net_total_return": (1 + net).prod() - 1,
        "net_sharpe_ratio": sharpe_ratio(net),
        "sharpe_diff_vs_benchmark": diff["point_diff"],
        "sharpe_diff_ci_lower": diff["lower"],
        "sharpe_diff_ci_upper": diff["upper"],
        "sharpe_diff_significant": diff["significant"],
    })
    return row


def holdings_text(weights: pd.DataFrame) -> pd.Series:
    """Each month's holdings as sorted tickers, so two versions can be compared as text."""
    return weights.apply(lambda row: " ".join(sorted(row.index[row > 0])), axis=1)


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

def published_failures(rows: pd.DataFrame) -> list[str]:
    """Gate 1: the rebuilt published series against the published CSVs, to 1e-9."""
    failures = []

    def check(label, recomputed, published):
        if abs(recomputed - published) > 1e-9:
            failures.append(f"{label}: recomputed {recomputed!r}, published {published!r}")

    files = {IS_LABEL: "results/strategy_comparison_full_period.csv", OOS_LABEL: "results/oos_summary.csv"}
    for period, path in files.items():
        table = pd.read_csv(path, index_col="label")
        rebuilt = rows[(rows["period"] == period) & rows["version"].isin([PUBLISHED, "unchanged"])].set_index("strategy")
        for name in STRATEGIES + ["Benchmark"]:
            for metric in METRICS:
                check(f"{path} {name} {metric}", rebuilt.loc[name, metric], table.loc[name, metric])
        if period == OOS_LABEL:
            for name in STRATEGIES:
                for metric in ["avg_monthly_turnover", "net_sharpe_ratio"]:
                    check(f"{path} {name} {metric}", rebuilt.loc[name, metric], table.loc[name, metric])
    return failures


def book_value_differences(as_filed: pd.DataFrame, stored: pd.DataFrame, months: pd.DataFrame) -> list[str]:
    """As-filed value of the filing in force against the stored value, to 1e-6, in the months marked True."""
    lines = []
    for ticker in months.columns:
        marked = months[ticker]
        gap = (as_filed[ticker].isna() != stored[ticker].isna())[marked]
        difference = (as_filed[ticker] - stored[ticker]).abs()[marked]
        wrong = difference[difference > 1e-6]
        if gap.any() or not wrong.empty:
            lines.append(f"{ticker}: {int(gap.sum())} of {int(marked.sum())} months with a value on one side only, "
                         f"{len(wrong)} months differ, largest difference {difference.max():.6g}")
    return lines


def restated_months(stored: pd.DataFrame, restated: pd.DataFrame) -> pd.DataFrame:
    """True in the months where restatement changes the stored value, including a value lost to NaN."""
    return ~((stored == restated) | (stored.isna() & restated.isna()))


def sample_month_ends(months: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Keeps the month ends that feed the sample: the row dated t uses book value at the end of t-1."""
    rows = months.index.get_indexer(dates) - 1
    in_sample = pd.Series(False, index=months.index)
    in_sample.iloc[rows] = True
    return months.mul(in_sample, axis=0).astype(bool)


def event_tickers(splits: dict) -> list[str]:
    return [t for t, ratios in splits.items() if (ratios.index >= EVENTS_FROM).any()]


def restated_book_failures(as_filed: pd.DataFrame, stored: pd.DataFrame, restated: pd.DataFrame,
                           splits: dict, dates: pd.DatetimeIndex) -> list[str]:
    """Gate 2: for each stock with an event that changes the sample, in the months restated (Amendment 9)."""
    changed = sample_month_ends(restated_months(stored, restated), dates)
    checked = [t for t in event_tickers(splits) if t in changed.columns and changed[t].any()]
    print(f"Gate 2 covers {checked}")
    return book_value_differences(as_filed, stored, changed[checked])


def no_event_failures(stored: pd.DataFrame, restated: pd.DataFrame, splits: dict) -> list[str]:
    """Gate 3: a stock with no event has a restated value equal to its stored value."""
    failures = []
    changed = restated_months(stored, restated)
    for ticker in [t for t in stored.columns if t not in event_tickers(splits)]:
        if changed[ticker].any():
            failures.append(f"{ticker}: {int(changed[ticker].sum())} months changed with no event")
    return failures


def stop_on_failures(label: str, failures: list[str]):
    if failures:
        print(f"\n{label} FAILED. Nothing was written. Mismatches:")
        for failure in failures:
            print("  " + failure)
        raise SystemExit(1)
    print(f"{label} passed.")


# ---------------------------------------------------------------------------
# Output frames
# ---------------------------------------------------------------------------

def period_of(dates: pd.DatetimeIndex) -> np.ndarray:
    return np.where(dates <= pd.Timestamp(IN_SAMPLE_END), IS_LABEL, OOS_LABEL)


def build_holdings(versions: dict, dates: pd.DatetimeIndex) -> pd.DataFrame:
    frames = []
    for name in REVISED:
        frame = pd.DataFrame({"date": dates, "period": period_of(dates), "strategy": name})
        for version in VERSIONS:
            frame[f"holdings_{version}"] = holdings_text(versions[version][name][1].loc[dates]).values
        for version in VERSIONS[1:]:
            frame[f"changed_{version}"] = frame[f"holdings_{version}"] != frame[f"holdings_{PUBLISHED}"]
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def build_monthly_returns(versions: dict, periods: dict, history: pd.DatetimeIndex, benchmark: pd.Series) -> pd.DataFrame:
    frames = []
    for period, dates in periods.items():
        series = [("Momentum", "unchanged", versions[PUBLISHED]["Momentum"])]
        series += [(name, version, versions[version][name]) for name in REVISED for version in VERSIONS]
        for name, version, (returns, weights) in series:
            gross = returns.loc[dates]
            net = apply_transaction_costs(gross, period_turnover(weights, period, dates, history), cost_bps=COST_BPS)
            frames.append(pd.DataFrame({"date": dates, "period": period, "strategy": name, "version": version,
                                        "gross_return": gross.values, "net_return": net.values}))
        frames.append(pd.DataFrame({"date": dates, "period": period, "strategy": "Benchmark", "version": "unchanged",
                                    "gross_return": benchmark.loc[dates].values, "net_return": np.nan}))
    return pd.concat(frames, ignore_index=True)


def build_pb(values: dict, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """P/B used by the row dated t (measured at the end of t-1), one row per date and ticker, blank where there is none."""
    columns = {f"pb_{version}": -frame.loc[dates].stack() for version, frame in values.items()}
    frame = pd.DataFrame(columns).rename_axis(["date", "ticker"]).reset_index()
    frame.insert(1, "period", period_of(pd.DatetimeIndex(frame["date"])))
    return frame


def build_events(splits: dict, stored: pd.DataFrame, restated: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Events since EVENTS_FROM, with the Value rows whose book value (at t-1) they change."""
    rows = []
    changed = restated_months(stored, restated).shift(1, fill_value=False).loc[dates]
    for ticker in event_tickers(splits):
        months = changed.index[changed[ticker]]
        ratios = splits[ticker]
        for date, ratio in ratios[ratios.index >= EVENTS_FROM].items():
            rows.append({
                "ticker": ticker, "event_date": date.strftime("%Y-%m-%d"), "ratio": ratio,
                "value_rows_changed": len(months),
                "first_row_changed": months[0].strftime("%Y-%m") if len(months) else "",
                "last_row_changed": months[-1].strftime("%Y-%m") if len(months) else "",
                "note": EVENT_NOTES.get(ticker, ""),
            })
    return pd.DataFrame(rows)


def print_continuity(records: dict, splits: dict):
    """Book value per share just before and after each event, as filed and restated."""
    print("\nBook value per share around each event (last filing before, first filing after):")
    for ticker in event_tickers(splits):
        ratios = splits[ticker]
        restated = restate_book_value(records[ticker], ratios)
        for date, ratio in ratios[ratios.index >= EVENTS_FROM].items():
            before = records[ticker]["filed_date"] <= date
            last, first = before[before].index[-1], before[~before].index[0]
            print(f"  {ticker:5s} {date.date()} ratio {ratio:g}: "
                  f"as filed {records[ticker].loc[last, 'book_value_per_share']:.3f} -> "
                  f"{records[ticker].loc[first, 'book_value_per_share']:.3f}; "
                  f"restated {restated.loc[last, 'book_value_per_share']:.3f} -> "
                  f"{restated.loc[first, 'book_value_per_share']:.3f}")


def print_results(summary: pd.DataFrame, holdings: pd.DataFrame, events: pd.DataFrame):
    print("\nEvents and the Value rows they change:")
    print(events.drop(columns="note").to_string(index=False))

    print("\nMonths with different top 5 holdings from the published version:")
    grouped = holdings.groupby(["period", "strategy"], sort=False)
    print(grouped[[f"changed_{v}" for v in VERSIONS[1:]]].sum().to_string())

    shown = ["period", "strategy", "version", "total_return", "annualized_return", "sharpe_ratio", "max_drawdown",
             "alpha", "alpha_tstat", "avg_monthly_turnover", "net_sharpe_ratio", "sharpe_diff_vs_benchmark",
             "sharpe_diff_ci_lower", "sharpe_diff_ci_upper", "sharpe_diff_significant"]
    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print("\n" + summary[shown].round(3).to_string(index=False))


def main():
    stop_if_outputs_exist()

    prices = load_prices()
    stored_book = load_book_value()
    monthly_returns = calculate_monthly_returns(prices)
    month_ends = stored_book.index

    records = load_filed_records()
    splits = load_splits()
    as_filed = filled_book_value({t: records[t] for t in stored_book.columns}, month_ends)
    filings = pd.DataFrame({t: filing_in_force(records[t], month_ends) for t in stored_book.columns})
    restated = restate_stored_book_value(stored_book, filings, splits)
    close = load_cached_close(prices.index)

    momentum = calculate_momentum(prices)
    values = {
        PUBLISHED: calculate_value_score(prices, stored_book),
        RESTATED_ADJ: calculate_value_score(prices, restated),
        RESTATED_CLOSE: calculate_value_score(close, restated),
    }
    versions = {version: build_version(momentum, value, monthly_returns) for version, value in values.items()}

    history = common_dates(versions[PUBLISHED])
    for version in VERSIONS[1:]:
        if not common_dates(versions[version]).equals(history):
            raise SystemExit(f"Version {version} covers different months from the published one. Stopping.")
    periods = {IS_LABEL: history[history <= IN_SAMPLE_END], OOS_LABEL: history[history >= OUT_OF_SAMPLE_START]}
    benchmark = calculate_benchmark_returns(monthly_returns)
    for period, dates in periods.items():
        print(f"{period:34s} {dates.min().date()} to {dates.max().date()} ({len(dates)} months)")

    rows = []
    for period, dates in periods.items():
        bench = benchmark.loc[dates]
        momentum_gross, momentum_weights = versions[PUBLISHED]["Momentum"]
        rows.append(strategy_row("Momentum", "unchanged", period, momentum_gross.loc[dates],
                                 period_turnover(momentum_weights, period, dates, history), bench))
        for name in REVISED:
            for version in VERSIONS:
                gross, weights = versions[version][name]
                rows.append(strategy_row(name, version, period, gross.loc[dates],
                                         period_turnover(weights, period, dates, history), bench))
        stats = summarize_risk(bench, "Benchmark", benchmark_returns=bench)
        rows.append({"period": period, "months": len(dates), "strategy": "Benchmark", "version": "unchanged",
                     **{metric: stats[metric] for metric in METRICS}})
    summary = pd.DataFrame(rows)

    stop_on_failures("Gate 1 (published series against the published CSVs, 1e-9)", published_failures(summary))
    stop_on_failures("Gate 2 (filing in force against the book_value table in restated months, 1e-6)",
                     restated_book_failures(as_filed, stored_book, restated, splits, history))
    stop_on_failures("Gate 3 (no change for stocks without an event)", no_event_failures(stored_book, restated, splits))

    print("\nCached against stored book value, all stocks and months (report only, Amendment 9):")
    all_months = pd.DataFrame(True, index=month_ends, columns=stored_book.columns)
    for line in book_value_differences(as_filed, stored_book, all_months):
        print("  " + line)

    holdings = build_holdings(versions, history)
    outputs = {
        "summary": summary,
        "monthly_returns": build_monthly_returns(versions, periods, history, benchmark),
        "holdings": holdings,
        "pb": build_pb(values, history),
        "events": build_events(splits, stored_book, restated, history),
    }
    print_continuity(records, splits)
    print_results(summary, holdings, outputs["events"])

    for name, frame in outputs.items():
        frame.to_csv(OUTPUTS[name], index=False, mode="x")
        print(f"Wrote {OUTPUTS[name]} ({len(frame)} rows)")


if __name__ == "__main__":
    main()
