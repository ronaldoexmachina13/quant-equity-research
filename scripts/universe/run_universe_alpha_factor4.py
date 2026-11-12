"""
Amendment 18 (LIMITATIONS_PLAN.md): four-factor alpha regression. Exploratory and post-results.

Reads only saved files:
  results/universe_study_portfolio_returns.csv                       (registered portfolios)
  results/universe_study_sector_neutral_portfolio_returns.csv        (sector-neutral and same-names variants)
  data/external/french/*.csv                                         (French Mkt-RF, SMB, HML, Mom; percent, unchanged)

For each portfolio, the monthly return minus the saved Treasury bill rate (rf_monthly) is regressed on
Mkt-RF, SMB, HML and Mom (decimals). Newey-West 90% intervals, lags by the rule of Amendment 14, no
small-sample correction. Alpha is monthly alpha times 12. The French RF column is not used.
Every fit is also compared with an independent statsmodels fit; a difference above 1e-8 stops the run.

Run from the repository root:
  python -m scripts.universe.run_universe_alpha_factor4 --dry-run
  python -m scripts.universe.run_universe_alpha_factor4 --write
With no flag the script exits. --write refuses to start if the output exists, then writes with mode "x".
"""
import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from src.factor_check import annualise_alpha, read_french, regress_on_factors
from src.signal_extras import newey_west_lags
from src.universe_study import FULL_PERIOD, NEW_TEST, RE_TEST

RETURNS_PATH = "results/universe_study_portfolio_returns.csv"
VARIANT_PATH = "results/universe_study_sector_neutral_portfolio_returns.csv"
FF3_PATH = "data/external/french/ff3_monthly_201101_202609.csv"
MOM_PATH = "data/external/french/mom_monthly_201101_202609.csv"
OUT = "results/universe_study_alpha_factor4.csv"
FACTORS = ["Mkt-RF", "SMB", "HML", "Mom"]
BASES = ["gross", "net_drift"]
SIZES = ["top_decile", "top_quintile"]
PERIODS = [NEW_TEST, RE_TEST, FULL_PERIOD]
EXPECTED_MONTHS = {NEW_TEST: 108, RE_TEST: 68, FULL_PERIOD: 176}
TOLERANCE = 1e-8


def period_rows(frame: pd.DataFrame, period: str) -> pd.DataFrame:
    return frame if period == FULL_PERIOD else frame[frame["period"] == period]


def portfolio_list(published: pd.DataFrame, variants: pd.DataFrame):
    """Yield (variant label, strategy, size, frame of that portfolio's monthly rows)."""
    for strategy in ["Momentum", "Value", "Combined"]:
        for size in SIZES:
            yield "published", strategy, size, published[(published["strategy"] == strategy) & (published["size"] == size)]
    for variant in ["control_same_names", "sector_neutral"]:
        for strategy in ["Value", "Combined"]:
            for size in SIZES:
                frame = variants[(variants["variant"] == variant) & (variants["strategy"] == strategy)
                                 & (variants["size"] == size)]
                yield variant, strategy, size, frame


def statsmodels_check(y: pd.Series, factors: pd.DataFrame, ours: dict) -> float:
    """Largest absolute difference from an independent statsmodels HAC fit (alpha, loadings, standard errors)."""
    import statsmodels.api as sm
    both = pd.concat([y.rename("y"), factors], axis=1).dropna()
    fit = sm.OLS(both["y"].values, sm.add_constant(both[FACTORS].values)).fit(
        cov_type="HAC", cov_kwds={"maxlags": ours["lags"], "use_correction": False})
    diffs = [abs(fit.params[0] - ours["alpha"]), abs(fit.bse[0] - ours["alpha_se"])]
    for i, name in enumerate(FACTORS, start=1):
        diffs += [abs(fit.params[i] - ours[f"beta_{name}"]), abs(fit.bse[i] - ours[f"beta_{name}_se"])]
    return float(max(diffs))


def factor4_table(published: pd.DataFrame, variants: pd.DataFrame, french: pd.DataFrame):
    rows, worst = [], 0.0
    for variant, strategy, size, frame in portfolio_list(published, variants):
        frame = frame.copy()
        frame["date"] = pd.to_datetime(frame["date"])
        for period in PERIODS:
            sub = period_rows(frame, period).set_index("date")
            for basis in BASES:
                y = (sub[basis] - sub["rf_monthly"]).dropna()
                out = regress_on_factors(y, french[FACTORS])
                worst = max(worst, statsmodels_check(y, french[FACTORS], out))
                row = {"variant": variant, "period": period, "strategy": strategy, "size": size, "basis": basis,
                       "months": out["months"], "lags": out["lags"],
                       "alpha_annual": annualise_alpha(out["alpha"]),
                       "alpha_annual_ci_90_lower": annualise_alpha(out["alpha_lower"]),
                       "alpha_annual_ci_90_upper": annualise_alpha(out["alpha_upper"]),
                       "alpha_t": out["alpha_t"], "r_squared": out["r_squared"],
                       "alpha_excludes_zero": bool(out["alpha_lower"] > 0 or out["alpha_upper"] < 0)}
                for name in FACTORS:
                    row[f"beta_{name}"] = out[f"beta_{name}"]
                    row[f"beta_{name}_se"] = out[f"beta_{name}_se"]
                rows.append(row)
    return pd.DataFrame(rows), worst


def check_table(table: pd.DataFrame, worst: float) -> list[str]:
    failures = []
    if len(table) != 84:
        failures.append(f"{len(table)} rows, expected 84")
    for period, expected in EXPECTED_MONTHS.items():
        if set(table.loc[table["period"] == period, "months"]) != {expected}:
            failures.append(f"months in {period} are not all {expected}")
    if worst > TOLERANCE:
        failures.append(f"statsmodels difference {worst:.2e} exceeds {TOLERANCE:.0e}")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if not (args.dry_run or args.write):
        print("No flag given. Use --dry-run or --write.")
        return
    if args.write and Path(OUT).exists():
        sys.exit(f"Refusing to start, this exists: {OUT}")
    ff3 = read_french(FF3_PATH, ["Mkt-RF", "SMB", "HML", "RF"])
    mom = read_french(MOM_PATH, ["Mom"])
    french = ff3[["Mkt-RF", "SMB", "HML"]].join(mom["Mom"], how="inner")
    published = pd.read_csv(RETURNS_PATH)
    variants = pd.read_csv(VARIANT_PATH)
    table, worst = factor4_table(published, variants, french)
    failures = check_table(table, worst)
    if failures:
        sys.exit("Checks failed:\n" + "\n".join(failures))
    print(f"statsmodels check: largest difference {worst:.2e} (limit {TOLERANCE:.0e})")
    pd.set_option("display.width", 240, "display.max_columns", 30)
    show = table[(table["basis"] == "gross") & (table["size"] == "top_decile") & (table["period"] == FULL_PERIOD)]
    print(show.drop(columns=["size", "basis", "period", "lags", "alpha_excludes_zero"]).round(3).to_string(index=False))
    if args.write:
        with open(OUT, "x", newline="") as handle:
            table.to_csv(handle, index=False)
        print(OUT, len(pd.read_csv(OUT)), hashlib.sha256(Path(OUT).read_bytes()).hexdigest()[:12])


if __name__ == "__main__":
    main()
