"""Build universe_data.js, the data file behind the large-universe dashboard (index.html).

Reads only the committed result files in results/ and writes one new file.
It refuses to overwrite an existing file, in line with the project's rule that
results are never silently replaced. To regenerate, move the old file first.
"""
import json
import math
import sys
from pathlib import Path

import pandas as pd

RESULTS = Path("results")
OUT = Path("universe_data.js")


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


def main():
    if OUT.exists():
        sys.exit(f"{OUT} already exists. Move it first to regenerate.")

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


if __name__ == "__main__":
    main()
