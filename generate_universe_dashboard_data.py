"""Build the data files behind the large-universe dashboard.

  universe_data.js         headline results (index.html and the pages that read it)
  universe_sens_data.js    sensitivity results (universe-strategies.html)
  universe_stocks_data.js  one row per ticker ever in the index (universe-stocks.html, universe-timeline.html)
  universe_holdings_data.js  top-decile holdings by month (universe-timeline.html)

Reads only the committed result files in results/. An output that already exists
is left alone and reported, in line with the project's rule that files are never
silently replaced. To regenerate one, move the old file first.
"""
import json
import math
import sys
from pathlib import Path

import pandas as pd

RESULTS = Path("results")
OUT = Path("universe_data.js")
SENS_OUT = Path("universe_sens_data.js")
STOCKS_OUT = Path("universe_stocks_data.js")
HOLDINGS_OUT = Path("universe_holdings_data.js")


def clean(value):
    """NaN and numpy types become plain JSON values."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if hasattr(value, "item"):
        value = value.item()
    return round(value, 6) if isinstance(value, float) else value


def returns_series(frame, strategy, size, column):
    rows = frame[frame["strategy"] == strategy]
    if size is not None:
        rows = rows[rows["size"] == size]
    return rows.sort_values("date")[column].round(6).tolist()


def write_main():
    if OUT.exists():
        print(f"{OUT} already exists, left unchanged.")
        return

    returns = pd.read_csv(RESULTS / "universe_study_portfolio_returns.csv")
    summary = pd.read_csv(RESULTS / "universe_study_portfolio_summary.csv")

    base = returns[(returns["strategy"] == "Momentum") & (returns["size"] == "top_decile")]
    dates = sorted(base["date"].unique())
    split = int((base.sort_values("date")["period"] != "New test (2012-2020)").values.argmax())

    series = {}
    for signal in ["Momentum", "Value", "Combined"]:
        series[signal] = {}
        for size in ["top_decile", "top_quintile"]:
            series[signal][size] = {
                "gross": returns_series(returns, signal, size, "gross"),
                "net": returns_series(returns, signal, size, "net_drift"),
            }
    benchmarks = {}
    for key, name in [("Momentum", "Benchmark (Momentum usable)"),
                      ("Value and Combined", "Benchmark (Value and Combined usable)")]:
        benchmarks[key] = {
            "gross": returns_series(returns, name, None, "gross"),
            "net": returns_series(returns, name, None, "net_drift"),
        }
    spy = returns_series(returns, "SPY (reference)", None, "gross")
    for block in list(benchmarks.values()) + [{"spy": spy}]:
        for values in block.values():
            assert len(values) == len(dates), "series length differs from the date list"
    for signal in series.values():
        for size in signal.values():
            for values in size.values():
                assert len(values) == len(dates)

    ic_m = pd.read_csv(RESULTS / "universe_study_ic_monthly_momentum.csv")
    ic_vc = pd.read_csv(RESULTS / "universe_study_ic_monthly_value_combined.csv")
    ic_all = pd.concat([ic_m, ic_vc])
    ic = {}
    for signal in ["Momentum", "Value", "Combined"]:
        rows = ic_all[ic_all["signal"] == signal].sort_values("date")
        assert rows["date"].tolist() == dates
        ic[signal] = rows["rank_ic"].round(6).tolist()

    sig_all = pd.concat([
        pd.read_csv(RESULTS / "universe_study_signal_summary_momentum.csv"),
        pd.read_csv(RESULTS / "universe_study_signal_summary_value_combined.csv"),
    ])
    signal_tests = [
        {k: clean(r[k]) for k in ["test", "signal", "period", "months", "mean", "ci_90_lower", "ci_90_upper", "excludes_zero"]}
        for _, r in sig_all.iterrows()
    ]

    cols = {
        "period": "period", "strategy": "strategy", "size": "size", "basis": "basis",
        "headline_test": "headline", "months": "months", "total_return": "total",
        "annualized_return": "ann", "annualized_volatility": "vol", "sharpe_tbill": "sharpe",
        "max_drawdown": "dd", "avg_turnover_drift": "turnover", "sharpe_diff_tbill": "diff",
        "ci_90_lower_tbill": "lo", "ci_90_upper_tbill": "hi", "significant_tbill": "sig",
    }
    summary_rows = [{new: clean(r[old]) for old, new in cols.items()} for _, r in summary.iterrows()]

    head = summary[(summary["headline_test"] == True) & (summary["basis"] == "gross") & summary["sharpe_diff_tbill"].notna()]
    n_head = len(head)
    n_sig = int((head["significant_tbill"] == True).sum())
    print(f"headline portfolio intervals: {n_head}, excluding zero: {n_sig}")
    assert n_head == 18 and n_sig == 2

    cov = pd.read_csv(RESULTS / "universe_coverage_monthly.csv")
    cov = cov[cov["month"].isin([d[:7] for d in dates])].sort_values("month")
    coverage = {
        "months": cov["month"].tolist(),
        "members": cov["members"].tolist(),
        "momentum": cov["usable_momentum"].tolist(),
        "value_combined": cov["usable_value_combined"].tolist(),
    }
    assert len(coverage["months"]) == len(dates)

    surv = pd.read_csv(RESULTS / "universe_study_survivorship.csv")
    survivorship = [
        {k: clean(r[k]) for k in ["period", "universe_set", "group", "months", "names_per_month_avg", "annualised_mean"]}
        for _, r in surv.iterrows()
    ]

    data = {
        "dates": [d[:7] for d in dates], "split": split,
        "series": series, "benchmarks": benchmarks, "spy": spy,
        "ic": ic, "signalTests": signal_tests, "summary": summary_rows,
        "coverage": coverage, "survivorship": survivorship,
    }
    text = ("/* Written by generate_universe_dashboard_data.py from results/universe_study_*.csv "
            "and results/universe_coverage_monthly.csv. Do not edit by hand. */\n"
            "const UNIVERSE = " + json.dumps(data, separators=(",", ":")) + ";\n")
    with open(OUT, "x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(f"wrote {OUT} ({len(text) // 1024} KB), {len(dates)} months, split at index {split}")


def sens_rows(path, keys):
    frame = pd.read_csv(path)
    return [{k: clean(r[k]) for k in keys} for _, r in frame.iterrows()]


def write_sens():
    if SENS_OUT.exists():
        print(f"{SENS_OUT} already exists, left unchanged.")
        return
    test_keys = ["test", "signal", "period", "months", "mean", "ci_90_lower", "ci_90_upper", "excludes_zero"]
    summary_keys = ["period", "strategy", "size", "basis", "headline_test", "months", "total_return", "annualized_return",
                    "annualized_volatility", "sharpe_tbill", "max_drawdown", "avg_turnover_drift",
                    "sharpe_diff_tbill", "ci_90_lower_tbill", "ci_90_upper_tbill", "significant_tbill"]
    rename = dict(zip(summary_keys, ["period", "strategy", "size", "basis", "headline", "months", "total", "ann", "vol",
                                     "sharpe", "dd", "turnover", "diff", "lo", "hi", "sig"]))
    def summary(path):
        return [{rename[k]: v for k, v in row.items()} for row in sens_rows(path, summary_keys)]
    data = {
        "signalTests": {
            "winsorised": sens_rows(RESULTS / "universe_study_signal_summary_value_combined_winsorised_pb.csv", test_keys),
            "excl_24": sens_rows(RESULTS / "universe_study_signal_summary_value_combined_excl_24.csv", test_keys),
            "excl_37": sens_rows(RESULTS / "universe_study_signal_summary_value_combined_excl_37.csv", test_keys),
        },
        "summary": {
            "excl_24": summary(RESULTS / "universe_study_portfolio_summary_excl_24.csv"),
            "excl_37": summary(RESULTS / "universe_study_portfolio_summary_excl_37.csv"),
        },
    }
    text = ("/* Written by generate_universe_dashboard_data.py from the sensitivity files in results/. "
            "Do not edit by hand. */\nconst UNIVERSE_SENS = " + json.dumps(data, separators=(",", ":")) + ";\n")
    with open(SENS_OUT, "x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(f"wrote {SENS_OUT} ({len(text) // 1024} KB)")


def write_js(path, const, data, source):
    text = (f"/* Written by generate_universe_dashboard_data.py from {source}. Do not edit by hand. */\n"
            f"const {const} = " + json.dumps(data, separators=(",", ":")) + ";\n")
    with open(path, "x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(f"wrote {path} ({len(text) // 1024} KB)")


def write_stocks():
    source = RESULTS / "universe_study_stock_summary.csv"
    if STOCKS_OUT.exists():
        print(f"{STOCKS_OUT} already exists, left unchanged.")
        return
    if not source.exists():
        print(f"{source} is missing; run run_universe_holdings.py first. Skipping {STOCKS_OUT}.")
        return
    frame = pd.read_csv(source)
    cols = ["ticker", "company", "gics_sector", "start_date", "end_date", "group", "has_price_history",
            "months_usable_momentum", "months_usable_value", "avg_monthly_return",
            "months_held_momentum", "contribution_momentum", "months_held_value", "contribution_value",
            "months_held_combined", "contribution_combined"]
    rows = [[clean(r[c]) for c in cols] for _, r in frame.iterrows()]
    write_js(STOCKS_OUT, "UNIVERSE_STOCKS", {"columns": cols, "rows": rows}, str(source))


def write_holdings():
    source = RESULTS / "universe_study_holdings.csv"
    if HOLDINGS_OUT.exists():
        print(f"{HOLDINGS_OUT} already exists, left unchanged.")
        return
    if not source.exists():
        print(f"{source} is missing; run run_universe_holdings.py first. Skipping {HOLDINGS_OUT}.")
        return
    frame = pd.read_csv(source)
    months = sorted(frame["date"].unique())
    index = {m: i for i, m in enumerate(months)}
    holdings = {}
    for strategy, part in frame.groupby("strategy"):
        by_month = [[] for _ in months]
        for r in part.itertuples():
            by_month[index[r.date]].append([r.ticker, round(r._6, 4), round(r.score, 3)])
        holdings[strategy] = by_month
    write_js(HOLDINGS_OUT, "UNIVERSE_HOLDINGS", {"months": months, "columns": ["ticker", "return", "score"],
                                                  "holdings": holdings}, str(source))


def main():
    write_main()
    write_sens()
    write_stocks()
    write_holdings()


if __name__ == "__main__":
    main()
