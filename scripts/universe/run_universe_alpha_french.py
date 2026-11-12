"""
Amendment 16 (LIMITATIONS_PLAN.md), decisions 2 and 4: the benchmark regression and the
Kenneth French reference check. Everything here is exploratory and post-results.

It reads only saved files, so it needs no price or fundamentals cache:
  results/universe_study_portfolio_returns.csv          (monthly returns of every portfolio and benchmark)
  results/universe_study_spread_monthly_*.csv           (monthly quintile spreads of Momentum, Value, Combined)
  data/external/french/*.csv                            (French monthly factors, percent, stored unchanged)

Regression: for every portfolio (Momentum, Value, Combined; top decile and top quintile; gross and
net_drift) and every period, the monthly excess return over the Treasury bill rate is regressed on the
excess return of (a) the equal-weight benchmark that the registered test uses for that signal and
(b) the SPY reference. Newey-West 90% intervals, lags from the rule of Amendment 14. The headline
rows are gross, top decile, matched benchmark. Alpha is monthly alpha times 12.

Reference check: Pearson and Spearman correlation of each signal's monthly quintile spread with the
French UMD and HML factors, by period. Months are matched by calendar month. The study's row dated
2012-01-31 holds the return earned during January 2012, so it is matched with the French 201201 row.

Run from the repository root:
  python -m scripts.universe.run_universe_alpha_french --dry-run
  python -m scripts.universe.run_universe_alpha_french --write
With no flag the script exits. --write refuses to start if either output exists, then writes with mode "x".
"""
import argparse
import hashlib
import sys
from pathlib import Path

import pandas as pd

from src.factor_check import annualise_alpha, correlation_with_reference, read_french, regress_on_benchmark
from src.universe_study import FULL_PERIOD, NEW_TEST, RE_TEST

RETURNS_PATH = "results/universe_study_portfolio_returns.csv"
SPREAD_PATHS = {"Momentum": "results/universe_study_spread_monthly_momentum.csv",
                "Value": "results/universe_study_spread_monthly_value_combined.csv",
                "Combined": "results/universe_study_spread_monthly_value_combined.csv"}
FF3_PATH = "data/external/french/ff3_monthly_201101_202609.csv"
MOM_PATH = "data/external/french/mom_monthly_201101_202609.csv"
REGRESSION_OUT = "results/universe_study_alpha_regression.csv"
REFERENCE_OUT = "results/universe_study_french_correlation.csv"
BENCHMARK = {"Momentum": "Benchmark (Momentum usable)", "Value": "Benchmark (Value and Combined usable)",
             "Combined": "Benchmark (Value and Combined usable)"}
SPY = "SPY (reference)"
BASES = ["gross", "net_drift"]
SIZES = ["top_decile", "top_quintile"]
PERIODS = [NEW_TEST, RE_TEST, FULL_PERIOD]
EXPECTED_MONTHS = {NEW_TEST: 108, RE_TEST: 68, FULL_PERIOD: 176}


def period_rows(frame: pd.DataFrame, period: str) -> pd.DataFrame:
    return frame if period == FULL_PERIOD else frame[frame["period"] == period]


def regression_table(returns: pd.DataFrame) -> pd.DataFrame:
    """One row per period, strategy, size, basis and benchmark."""
    returns = returns.copy()
    returns["date"] = pd.to_datetime(returns["date"])
    rf = returns[returns["strategy"] == SPY].set_index("date")["rf_monthly"]
    rows = []
    for period in PERIODS:
        for strategy in ["Momentum", "Value", "Combined"]:
            for size in SIZES:
                portfolio = returns[(returns["strategy"] == strategy) & (returns["size"] == size)]
                for basis in BASES:
                    for bench_name in (BENCHMARK[strategy], SPY):
                        bench = returns[returns["strategy"] == bench_name]
                        # The benchmark is a plain equal-weight or SPY series: its gross return is used
                        # for every basis, so that alpha is measured against the passive alternative.
                        y = period_rows(portfolio, period).set_index("date")[basis] - rf
                        x = period_rows(bench, period).set_index("date")["gross"] - rf
                        out = regress_on_benchmark(y.dropna(), x.dropna())
                        rows.append({
                            "period": period, "strategy": strategy, "size": size, "basis": basis,
                            "benchmark": bench_name, "months": out["months"], "lags": out["lags"],
                            "alpha_annual": annualise_alpha(out["alpha"]),
                            "alpha_annual_ci_90_lower": annualise_alpha(out["alpha_lower"]),
                            "alpha_annual_ci_90_upper": annualise_alpha(out["alpha_upper"]),
                            "alpha_t": out["alpha_t"], "beta": out["beta"], "beta_se": out["beta_se"],
                            "r_squared": out["r_squared"],
                            "alpha_excludes_zero": bool(out["alpha_lower"] > 0 or out["alpha_upper"] < 0),
                            "headline_test": bool(basis == "gross" and size == "top_decile"
                                                  and bench_name == BENCHMARK[strategy]),
                        })
    return pd.DataFrame(rows)


def reference_table(ff3: pd.DataFrame, mom: pd.DataFrame) -> pd.DataFrame:
    reference = {"UMD (French Mom)": mom["Mom"], "HML (French)": ff3["HML"]}
    rows = []
    for signal, path in SPREAD_PATHS.items():
        frame = pd.read_csv(path)
        frame = frame[frame["signal"] == signal]
        frame["date"] = pd.to_datetime(frame["date"])
        for period in PERIODS:
            spread = period_rows(frame, period).set_index("date")["quintile_spread"]
            for name, factor in reference.items():
                out = correlation_with_reference(spread, factor)
                rows.append({"period": period, "signal": signal, "reference": name, **out})
    return pd.DataFrame(rows)


def check_counts(regression: pd.DataFrame, reference: pd.DataFrame) -> list[str]:
    failures = []
    for period, expected in EXPECTED_MONTHS.items():
        if set(regression.loc[regression["period"] == period, "months"]) != {expected}:
            failures.append(f"regression months in {period} are not all {expected}")
        if set(reference.loc[reference["period"] == period, "months"]) != {expected}:
            failures.append(f"reference months in {period} are not all {expected}")
    if len(regression) != 72 or len(reference) != 18:
        failures.append(f"row counts {len(regression)} and {len(reference)}, expected 72 and 18")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if not (args.dry_run or args.write):
        print("No flag given. Use --dry-run or --write.")
        return
    existing = [p for p in (REGRESSION_OUT, REFERENCE_OUT) if Path(p).exists()]
    if args.write and existing:
        sys.exit(f"Refusing to start, these exist: {existing}")
    returns = pd.read_csv(RETURNS_PATH)
    ff3 = read_french(FF3_PATH, ["Mkt-RF", "SMB", "HML", "RF"])
    mom = read_french(MOM_PATH, ["Mom"])
    regression = regression_table(returns)
    reference = reference_table(ff3, mom)
    failures = check_counts(regression, reference)
    if failures:
        sys.exit("Checks failed:\n" + "\n".join(failures))
    pd.set_option("display.width", 220, "display.max_columns", 30)
    print(regression[regression["headline_test"]].round(4).to_string(index=False))
    print(reference.round(3).to_string(index=False))
    if args.write:
        for frame, path in ((regression, REGRESSION_OUT), (reference, REFERENCE_OUT)):
            with open(path, "x", newline="") as handle:
                frame.to_csv(handle, index=False)
            print(path, len(pd.read_csv(path)), hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12])


if __name__ == "__main__":
    main()
