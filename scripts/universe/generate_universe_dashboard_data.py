"""Build the data files behind the large-universe dashboard.

  universe_data.js         headline results (index.html and the pages that read it)
  universe_sens_data.js    sensitivity results (signals.html)
  universe_stocks_data.js  one row per ticker ever in the index (holdings.html, data.html)
  universe_holdings_data.js  top-decile holdings by month (holdings.html)
  universe_extras_data.js  quintile returns and interval robustness (signals.html, Amendment 14)
  universe_controls_data.js  alpha regression, French factor check and sector-neutral Value (Amendments 16 and 17)

Reads only the committed result files in results/. An output that already exists
is left alone and reported, in line with the project's rule that files are never
silently replaced. To regenerate one, move the old file first.
"""
import json
import math
from pathlib import Path

import pandas as pd

RESULTS = Path("results")
OUT = Path("assets/universe_data.js")
SENS_OUT = Path("assets/universe_sens_data.js")
STOCKS_OUT = Path("assets/universe_stocks_data.js")
HOLDINGS_OUT = Path("assets/universe_holdings_data.js")
EXTRAS_OUT = Path("assets/universe_extras_data.js")
CONTROLS_OUT = Path("assets/universe_controls_data.js")
FACTOR4_OUT = Path("assets/universe_factor4_data.js")


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
    write_js(STOCKS_OUT, "UNIVERSE_STOCKS", {"columns": cols, "rows": rows}, source.as_posix())


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
        # Columns are read by name. itertuples() renames "return" (a Python keyword) to a position-based
        # name, which would silently point at another column if the file's column order changed.
        for date, ticker, held_return, score in zip(part["date"], part["ticker"], part["return"], part["score"]):
            by_month[index[date]].append([ticker, round(held_return, 4), round(score, 3)])
        holdings[strategy] = by_month
    write_js(HOLDINGS_OUT, "UNIVERSE_HOLDINGS", {"months": months, "columns": ["ticker", "return", "score"],
                                                  "holdings": holdings}, source.as_posix())


def write_extras():
    quintiles = RESULTS / "universe_study_quintile_returns.csv"
    robustness = RESULTS / "universe_study_inference_robustness.csv"
    if EXTRAS_OUT.exists():
        print(f"{EXTRAS_OUT} already exists, left unchanged.")
        return
    missing = [p for p in (quintiles, robustness) if not p.exists()]
    if missing:
        print(f"{missing[0]} is missing; run run_universe_extras.py first. Skipping {EXTRAS_OUT}.")
        return
    q_keys = ["signal", "period", "quintile", "months", "mean_monthly", "mean_annualised", "monotonicity"]
    r_keys = ["test", "signal", "period", "months", "mean", "autocorrelation_lag1", "nw_lags", "nw_t_stat", "block_length",
              "iid_ci_90_lower", "iid_ci_90_upper", "iid_excludes_zero", "nw_ci_90_lower", "nw_ci_90_upper", "nw_excludes_zero",
              "block_ci_90_lower", "block_ci_90_upper", "block_excludes_zero"]
    data = {"quintiles": sens_rows(quintiles, q_keys), "robustness": sens_rows(robustness, r_keys)}
    write_js(EXTRAS_OUT, "UNIVERSE_EXTRAS", data, "the quintile and robustness files in results/")


def write_controls():
    alpha = RESULTS / "universe_study_alpha_regression.csv"
    french = RESULTS / "universe_study_french_correlation.csv"
    summary = RESULTS / "universe_study_sector_neutral_portfolio_summary.csv"
    counts = RESULTS / "universe_study_sector_neutral_counts.csv"
    signals = RESULTS / "universe_study_sector_neutral_signal_summary.csv"
    registered = RESULTS / "universe_study_portfolio_summary.csv"
    if CONTROLS_OUT.exists():
        print(f"{CONTROLS_OUT} already exists, left unchanged.")
        return
    missing = [p for p in (alpha, french, summary, counts, signals, registered) if not p.exists()]
    if missing:
        print(f"{missing[0]} is missing; run its script first. Skipping {CONTROLS_OUT}.")
        return
    a_keys = ["period", "strategy", "size", "basis", "benchmark", "months", "lags", "alpha_annual", "alpha_annual_ci_90_lower",
              "alpha_annual_ci_90_upper", "alpha_t", "beta", "beta_se", "r_squared", "alpha_excludes_zero", "headline_test"]
    f_keys = ["period", "signal", "reference", "months", "pearson", "pearson_lower", "pearson_upper", "spearman"]
    s_keys = ["period", "strategy", "size", "basis", "months", "sharpe_tbill", "benchmark_sharpe_tbill", "sharpe_diff_tbill",
              "ci_90_lower_tbill", "ci_90_upper_tbill", "significant_tbill"]
    neutral = pd.read_csv(summary)
    neutral = neutral[neutral["sharpe_diff_tbill"].notna() & (neutral["basis"] == "gross")]
    saved = pd.read_csv(registered)
    saved = saved[saved["strategy"].isin(["Value", "Combined"]) & (saved["basis"] == "gross") & saved["sharpe_diff_tbill"].notna()]
    rows = [{**{k: clean(r[k]) for k in s_keys}, "variant": "published"} for _, r in saved.iterrows()]
    rows += [{**{k: clean(r[k]) for k in s_keys}, "variant": r["variant"]} for _, r in neutral.iterrows()]
    c = pd.read_csv(counts)
    s = pd.read_csv(signals)
    data = {
        "alpha": sens_rows(alpha, a_keys), "french": sens_rows(french, f_keys), "sector": rows,
        "counts": {"months": int(len(c)), "scored_mean": clean(float(c["names_scored"].mean())),
                   "no_sector_mean": clean(float(c["no_sector"].mean())), "small_sector_mean": clean(float(c["small_sector"].mean())),
                   "kept_mean": clean(float(c["kept"].mean())), "kept_min": int(c["kept"].min()),
                   "no_sector_first_year": clean(float(c[c["date"].str[:4] == "2012"]["no_sector"].sum() / c[c["date"].str[:4] == "2012"]["names_scored"].sum())),
                   "no_sector_last_year": clean(float(c[c["date"].str[:4] == "2026"]["no_sector"].sum() / c[c["date"].str[:4] == "2026"]["names_scored"].sum()))},
        "signal_tests": {v: {"tests": int((s["variant"] == v).sum()), "exclude_zero": int(s[s["variant"] == v]["excludes_zero"].sum())}
                         for v in sorted(s["variant"].unique())},
    }
    write_js(CONTROLS_OUT, "UNIVERSE_CONTROLS", data, "the alpha, French and sector-neutral files in results/")


def write_factor4():
    source = RESULTS / "universe_study_alpha_factor4.csv"
    if FACTOR4_OUT.exists():
        print(f"{FACTOR4_OUT} already exists, left unchanged.")
        return
    if not source.exists():
        print(f"{source} is missing; run run_universe_alpha_factor4.py first. Skipping {FACTOR4_OUT}.")
        return
    keys = ["variant", "period", "strategy", "size", "basis", "months", "lags", "alpha_annual", "alpha_annual_ci_90_lower",
            "alpha_annual_ci_90_upper", "alpha_t", "r_squared", "alpha_excludes_zero", "beta_Mkt-RF", "beta_Mkt-RF_se",
            "beta_SMB", "beta_SMB_se", "beta_HML", "beta_HML_se", "beta_Mom", "beta_Mom_se"]
    write_js(FACTOR4_OUT, "UNIVERSE_FACTOR4", sens_rows(source, keys), "results/universe_study_alpha_factor4.csv")


def main():
    write_main()
    write_sens()
    write_stocks()
    write_holdings()
    write_extras()
    write_controls()
    write_factor4()


if __name__ == "__main__":
    main()
