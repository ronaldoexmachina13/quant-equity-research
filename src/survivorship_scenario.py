"""
Survivorship scenario table for the Momentum quintile spread (Amendment 19, decision 1).

Question: how large would the missing-names problem have to be, in a stated simple form, to move the
Momentum quintile spread away from zero? The saved result uses only names with price history. Names that
left the index, mostly acquired or bankrupt, are largely absent. If failed past losers are among the
missing names, group 1 (the lowest Momentum quintile) is too good in the saved data and the spread
(group 5 minus group 1) is too small.

Scenario rule, applied month by month to the saved group returns:

    group 1 adjusted = (1 - s) * group 1 saved + s * r_miss
    spread adjusted  = group 5 saved - group 1 adjusted
                     = saved spread + s * (group 1 saved - r_miss)

s is the share of the true group 1 assumed to be missing and r_miss the assumed monthly return of the
missing names. Both are ASSUMPTIONS CHOSEN FOR ILLUSTRATION, not estimated from data. No grid point is
preferred and every row is written. Group 5 is left as saved.

These functions only calculate. Reading and writing files is done by
scripts/universe/run_universe_survivorship_scenario.py, which refuses to write results unless
Amendment 19 is in docs/LIMITATIONS_PLAN.md.
"""
import numpy as np
import pandas as pd

from src.signal_eval import series_summary

SHARES_MISSING = [0.10, 0.20, 0.30]          # assumed share of the true group 1 that is missing
MISSING_RETURNS = [0.0, -0.02, -0.05]        # assumed monthly return of the missing names
NEW_TEST_END = pd.Timestamp("2020-12-31")
N_SIMS, SEED = 5000, 42                      # same as the registered bootstrap
NOTE = ("Scenario under stated assumptions, not an estimate and not a test. The assumed share and return of "
        "the missing names are illustrative. The adjustment is treated as known, group 5 and the group "
        "boundaries are left as saved, and names missing from group 5 are ignored.")


def period_months(dates):
    """The three registered windows as boolean masks over the monthly dates."""
    return {
        "New test (2012-2020)": dates <= NEW_TEST_END,
        "Re-test (2021-2026)": dates > NEW_TEST_END,
        "Full period (2012-2026)": np.ones(len(dates), dtype=bool),
    }


def adjusted_spread(group1, group5, share_missing, missing_return):
    """Group 5 minus group 1, with the assumed missing names mixed into group 1."""
    group1_adjusted = (1 - share_missing) * group1 + share_missing * missing_return
    return group5 - group1_adjusted


def reference_share_missing(coverage, mask):
    """For context only: the average share of index members with no usable price, by period. Not an input."""
    return float(coverage.loc[mask, "members_no_price_t1"].sum() / coverage.loc[mask, "members"].sum())


def scenario_table(quintiles: pd.DataFrame, coverage: pd.DataFrame) -> pd.DataFrame:
    """One row per period and scenario. `quintiles` and `coverage` are the saved CSVs, already read."""
    q = quintiles.copy()
    q["date"] = pd.to_datetime(q["date"])
    q = q[q["signal"] == "Momentum"].set_index("date").sort_index()
    cov = coverage.copy()
    cov["month"] = pd.to_datetime(cov["month"]) + pd.offsets.MonthEnd(0)   # saved as a month, quintile file uses month ends
    cov = cov.set_index("month").reindex(q.index)
    rows = []
    for period, mask in period_months(q.index).items():
        g1, g5 = q.loc[mask, "q1"], q.loc[mask, "q5"]
        reference = reference_share_missing(cov, mask)
        cases = [(0.0, np.nan)] + [(s, r) for s in SHARES_MISSING for r in MISSING_RETURNS]
        for share, ret in cases:
            spread = adjusted_spread(g1, g5, share, 0.0 if np.isnan(ret) else ret)
            summary = series_summary(spread, n_sims=N_SIMS, seed=SEED)
            rows.append({
                "signal": "Momentum", "period": period, "months": summary["months"],
                "assumed_share_missing_in_group1": share, "assumed_monthly_return_missing": ret,
                "spread_mean_monthly": summary["mean"], "spread_ci_90_lower": summary["ci_90_lower"],
                "spread_ci_90_upper": summary["ci_90_upper"], "spread_mean_annualised": summary["mean"] * 12,
                "reference_share_members_without_price": reference, "note": NOTE,
            })
    return pd.DataFrame(rows)


def gate_failures(table: pd.DataFrame, saved_summary: pd.DataFrame) -> list[str]:
    """The no-adjustment rows must reproduce the saved Momentum quintile spread (tolerance 1e-9)."""
    saved = saved_summary[saved_summary["test"] == "quintile_spread"].drop_duplicates("period").set_index("period")
    base = table[table["assumed_share_missing_in_group1"] == 0.0].set_index("period")
    failures = []
    for period in base.index:
        for mine, theirs in [("spread_mean_monthly", "mean"), ("spread_ci_90_lower", "ci_90_lower"),
                             ("spread_ci_90_upper", "ci_90_upper")]:
            if abs(base.loc[period, mine] - saved.loc[period, theirs]) > 1e-9:
                failures.append(f"{period}: {mine} differs from the saved file")
    return failures
