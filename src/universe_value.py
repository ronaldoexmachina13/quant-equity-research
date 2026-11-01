"""
Value and Combined path for Phase 4 (LIMITATIONS_PLAN.md, Amendments 8 to 11).

Book value per share follows the fixed rule in src/book_value_rule.py, with its
validity rule for units errors (Amendment 11, decision 1), and is
restated to the price's share basis by the filing-date rule in
src/split_adjust.py. Value uses the split-adjusted close, which is not adjusted
for dividends. calculate_value_score() and calculate_combined_score() are
called unchanged.

The usable set for Value and Combined is defined by the fixed rule: names
usable for Momentum with a book value at the end of t-1. It is reconciled to
the Phase 3 coverage file by name, month by month (Amendment 10, item 1).
"""
from fractions import Fraction
from pathlib import Path

import pandas as pd

from src.book_value_rule import valid_book_value_records, suspected_units_errors
from src.factors import calculate_value_score, calculate_combined_score
from src.signal_eval import (
    rank_ic, quintile_spread, monthly_statistic, monthly_counts, fama_macbeth_slopes, summarize_signal,
    series_summary, MIN_NAMES_PER_MONTH,
)
from src.split_adjust import restate_book_value
from src.universe import cache_dir, write_bytes_atomic
from src.universe_study import counts_frame, series_frame

SPLIT_CUTOFF = "2026-10-28"   # Amendment 10, item 3: the cached closes carry adjustments up to this date
JUMP_FACTOR = 2.0             # Amendment 8: a move above this in a month is listed
MAX_DENOMINATOR = 20          # a ratio is read as an ordinary split if it is a simple fraction, such as 3:2 or 1:20
EXTREME_MOVE_FACTOR = 100     # Amendment 11, decision 4: names above this are excluded in a labelled sensitivity
WINSOR_LOWER = 0.01           # Amendment 11, decision 3: cross-sectional percentiles of P/B, sensitivity only
WINSOR_UPPER = 0.99
LOW_PB = 0.1                  # Amendment 11, finding: P/B below this is listed. Report only

# Amendment 12, decision 3: both lists are fixed there and are never recomputed.
EXTREME_MOVE_LIST = ["AA", "AAP", "AEP", "ALK", "AMCR", "ANF", "ATO", "CCL", "CHTR", "CLF", "CLX", "CMG", "CNX", "COR",
                     "CRM", "CSX", "CTVA", "FTI", "GEN", "LUV", "PKG", "SPGI", "SW", "WYNN"]
EXTREME_RECORD_LIST = ["AA", "AAP", "AEP", "ALK", "AMCR", "AMD", "ANF", "ATO", "CB", "CCL", "CHTR", "CIEN", "CMG", "CNX",
                       "CRM", "CSX", "CTVA", "ENPH", "EOG", "FTI", "FTNT", "GEN", "IDXX", "LUV", "MAR", "NCLH", "PKG",
                       "SLE", "SPG", "SPGI", "URI", "WST", "WYNN"]
AMENDMENT_12_LIST = sorted(set(EXTREME_MOVE_LIST) | set(EXTREME_RECORD_LIST))

HEADLINE, WINSORISED, EXCLUDING_24, EXCLUDING_37 = "headline", "winsorised_pb", "excl_24", "excl_37"
SIGNAL_SETS = [HEADLINE, WINSORISED, EXCLUDING_24, EXCLUDING_37]
OUTPUT_PARTS = ["monthly_counts", "ic_monthly", "spread_monthly", "signal_summary"]
JUMP_REPORT = "bv_jumps"
RESULTS_DIR = Path("results")
SUMMARY_COLUMNS = ["test", "signal", "period", "months", "mean", "ci_90_lower", "ci_90_upper", "share_positive",
                   "excludes_zero", "annualised_mean", "annualised_ci_90_lower", "annualised_ci_90_upper"]
JUMP_REPORT_COLUMNS = ["record_type", "ticker", "month", "date", "previous", "value", "factor", "months_since_previous",
                       "balance_sheet", "cover_page", "ratio", "restated_before", "restated_after"]


def split_path(ticker: str):
    return cache_dir() / "reference" / "splits" / f"{ticker}.csv"


def write_split_file(ticker: str, ratios: pd.Series):
    """One file per ticker, written only after a successful download, so a header alone means no splits."""
    frame = pd.DataFrame({"date": ratios.index.strftime("%Y-%m-%d"), "ratio": ratios.values})
    write_bytes_atomic(split_path(ticker), frame.to_csv(index=False).encode("utf-8"))


def load_split_history(tickers: list[str]) -> tuple[dict, list[str]]:
    """({ticker: ratios by date}, tickers with no file). A missing file is never read as no splits."""
    history, missing = {}, []
    for ticker in tickers:
        path = split_path(ticker)
        if not path.exists():
            missing.append(ticker)
            continue
        frame = pd.read_csv(path)
        history[ticker] = pd.Series(frame["ratio"].astype(float).values, index=pd.to_datetime(frame["date"]), dtype=float)
    return history, missing


def apply_split_cutoff(history: dict, cutoff: str = SPLIT_CUTOFF) -> tuple[dict, pd.DataFrame]:
    """Splits on or before the cut-off, and a list of the later ones, which are ignored."""
    kept, ignored = {}, []
    for ticker, ratios in history.items():
        kept[ticker] = ratios[ratios.index <= cutoff]
        ignored += [{"ticker": ticker, "date": d, "ratio": r} for d, r in ratios[ratios.index > cutoff].items()]
    return kept, pd.DataFrame(ignored, columns=["ticker", "date", "ratio"])


def build_records(tickers: list[str], read_facts) -> tuple[dict, pd.DataFrame]:
    """({ticker: valid records, blanks included}, suspected units errors with their ticker) from a facts reader."""
    records, errors = {}, []
    for ticker in tickers:
        facts = read_facts(ticker)
        records[ticker] = valid_book_value_records(facts)
        found = suspected_units_errors(facts)
        if not found.empty:
            errors.append(found.assign(ticker=ticker))
    columns = ["ticker", "filed_date", "balance_sheet", "cover_page", "factor"]
    return records, pd.concat(errors, ignore_index=True)[columns] if errors else pd.DataFrame(columns=columns)


def restate_all(records: dict, splits: dict) -> dict:
    return {ticker: restate_book_value(bv, splits[ticker]) for ticker, bv in records.items()}


def value_usable_mask(momentum_mask: pd.DataFrame, book_value: pd.DataFrame) -> pd.DataFrame:
    """Usable for Momentum, with a book value at the end of t-1. Rows dated t, as in momentum_mask."""
    available = book_value.shift(1).reindex(index=momentum_mask.index, columns=momentum_mask.columns).notna()
    return momentum_mask & available


def value_signal(close: pd.DataFrame, book_value: pd.DataFrame, mask: pd.DataFrame) -> pd.DataFrame:
    """calculate_value_score() unchanged, on the mask's dates and tickers and restricted to the usable names."""
    score = calculate_value_score(close, book_value)
    return score.reindex(index=mask.index, columns=mask.columns).where(mask)


def combined_signal(momentum: pd.DataFrame, value: pd.DataFrame) -> pd.DataFrame:
    """calculate_combined_score() unchanged. Each leg is already masked to its own usable names (reading 3)."""
    return calculate_combined_score(momentum, value)


# ---------------------------------------------------------------------------
# Labelled sensitivities (Amendment 11, decisions 3 and 4). No headline uses these
# ---------------------------------------------------------------------------

def extreme_move_names(jumps: pd.DataFrame, factor: float = EXTREME_MOVE_FACTOR) -> list[str]:
    """Names in the jump report with a move above `factor`. The rest of the report excludes nothing."""
    return sorted(jumps.loc[jumps["factor"] > factor, "ticker"].unique())


def winsorise_pb(value: pd.DataFrame, lower: float = WINSOR_LOWER, upper: float = WINSOR_UPPER) -> pd.DataFrame:
    """
    A Value score with P/B capped at the percentiles of each month's usable
    names. Rows keep their timing: a row dated t holds P/B from t-1, and its
    percentiles come from that row only. Ranks change only at the tails.
    """
    pb = -value
    return -pb.clip(lower=pb.quantile(lower, axis=1), upper=pb.quantile(upper, axis=1), axis=0)


def excluding_names(signal: pd.DataFrame, names: list[str]) -> pd.DataFrame:
    """The signal with these names blank in every month, same shape. Must run before any standardising."""
    return signal.drop(columns=names, errors="ignore").reindex(columns=signal.columns)


def sensitivity_signals(momentum: pd.DataFrame, value: pd.DataFrame, extreme_names: list[str]) -> dict:
    """
    {sensitivity: {"Value": signal, "Combined": signal}}. Under winsorised_pb
    the Value signal is for the Fama-MacBeth test, where raw P/B is standardised.
    Under excluding_extreme_moves the names leave both legs before Combined is
    standardised. That list is known only after the sample, so this version
    measures dependence on those names and is not an investable rule.
    """
    winsorised = winsorise_pb(value)
    kept_momentum, kept_value = excluding_names(momentum, extreme_names), excluding_names(value, extreme_names)
    return {
        "winsorised_pb": {"Value": winsorised, "Combined": combined_signal(momentum, winsorised)},
        "excluding_extreme_moves": {"Value": kept_value, "Combined": combined_signal(kept_momentum, kept_value)},
    }


def signal_sets(momentum: pd.DataFrame, value: pd.DataFrame) -> dict:
    """
    {set: {"Momentum": signal, "Value": signal, "Combined": signal}} for the
    headline and the three labelled extras. Excluded names leave both legs
    before Combined is standardised, under both lists.
    """
    def excluded(names: list[str]) -> dict:
        chosen = sensitivity_signals(momentum, value, names)["excluding_extreme_moves"]
        return {"Momentum": excluding_names(momentum, names), **chosen}

    return {
        HEADLINE: {"Momentum": momentum, "Value": value, "Combined": combined_signal(momentum, value)},
        WINSORISED: {"Momentum": momentum, **sensitivity_signals(momentum, value, [])["winsorised_pb"]},
        EXCLUDING_24: excluded(EXTREME_MOVE_LIST),
        EXCLUDING_37: excluded(AMENDMENT_12_LIST),
    }


# ---------------------------------------------------------------------------
# Stage 3 outputs and frames
# ---------------------------------------------------------------------------

def value_combined_outputs(folder: Path = RESULTS_DIR) -> dict:
    """
    {(set, part): path} for every file of the Value and Combined run: four
    files for each set, and the jump report under its registered name.
    """
    paths = {}
    for name in SIGNAL_SETS:
        ending = "_value_combined" if name == HEADLINE else f"_value_combined_{name}"
        paths.update({(name, part): folder / f"universe_study_{part}{ending}.csv" for part in OUTPUT_PARTS})
    paths[("report", JUMP_REPORT)] = folder / f"universe_study_{JUMP_REPORT}.csv"
    return paths


def existing_outputs(paths) -> list[str]:
    return sorted(str(path) for path in paths if Path(path).exists())


def slope_summary(signal: str, slopes: dict, periods: dict, n_sims: int = 5000, seed: int = 42) -> pd.DataFrame:
    """One row per test and period for slope series, in the layout of summarize_signal()."""
    rows = [{"test": test, "signal": signal, "period": period,
             **series_summary(series.reindex(dates), n_sims=n_sims, seed=seed)}
            for period, dates in periods.items() for test, series in slopes.items()]
    return pd.DataFrame(rows).reindex(columns=SUMMARY_COLUMNS)


def signal_set_frames(signals: dict, returns: pd.DataFrame, coverage: pd.DataFrame, periods: dict,
                      value_slopes_only: bool = False, n_sims: int = 5000, seed: int = 42,
                      min_names: int = MIN_NAMES_PER_MONTH) -> dict:
    """
    The four output frames of one signal set. Value and Combined each get rank
    IC, quintile spread and single-signal Fama-MacBeth, and Momentum and Value
    together get the joint Fama-MacBeth. With value_slopes_only, Value keeps its
    two Fama-MacBeth tests only (Amendment 11, decision 3, as answered).
    """
    joint = fama_macbeth_slopes({name: signals[name] for name in ("Momentum", "Value")}, returns, min_names)
    extra_slopes = {"Value": {"fama_macbeth_joint": joint["Value"]}, "Combined": {}}

    ic_frames, spread_frames, summaries = [], [], []
    for name in ("Value", "Combined"):
        slopes = {"fama_macbeth_single": fama_macbeth_slopes({name: signals[name]}, returns, min_names)[name],
                  **extra_slopes[name]}
        if name == "Value" and value_slopes_only:
            summaries.append(slope_summary(name, slopes, periods, n_sims, seed))
            continue
        ic = monthly_statistic(signals[name], returns, rank_ic, min_names)
        spread = monthly_statistic(signals[name], returns, quintile_spread, min_names)
        ic_frames.append(series_frame(ic, name, "rank_ic"))
        spread_frames.append(series_frame(spread, name, "quintile_spread"))
        summaries.append(summarize_signal(name, ic, spread, slopes, periods, n_sims=n_sims, seed=seed)[SUMMARY_COLUMNS])
    summaries.append(slope_summary("Momentum", {"fama_macbeth_joint": joint["Momentum"]}, periods, n_sims, seed))

    return {
        "monthly_counts": counts_frame(monthly_counts(signals["Value"], returns), coverage, "value_combined"),
        "ic_monthly": pd.concat(ic_frames, ignore_index=True),
        "spread_monthly": pd.concat(spread_frames, ignore_index=True),
        "signal_summary": pd.concat(summaries, ignore_index=True),
    }


def signal_set_failures(label: str, signals: dict, returns: pd.DataFrame,
                        min_names: int = MIN_NAMES_PER_MONTH) -> list[str]:
    """Every month: enough names, Value and Combined on the same names, and no name without a return."""
    counts = monthly_counts(signals["Value"], returns)
    combined = signals["Combined"].notna().sum(axis=1)
    failures = []
    for date, row in counts.iterrows():
        month = date.strftime("%Y-%m")
        if row["usable"] < min_names:
            failures.append(f"{label} {month}: {row['usable']} usable names, below {min_names}")
        if row["usable"] != combined[date]:
            failures.append(f"{label} {month}: Value has {row['usable']} names, Combined {combined[date]}")
        if row["no_return"] != 0:
            failures.append(f"{label} {month}: {row['no_return']} names with no return, so the universe note would be false")
    return failures


def registered_list_failures(jumps: pd.DataFrame) -> list[str]:
    """The names recomputed from the jump report must equal the list fixed in Amendment 12. A check, never a new list."""
    found = extreme_move_names(jumps)
    return [] if found == EXTREME_MOVE_LIST else [f"found {found}, registered {EXTREME_MOVE_LIST}"]


def jump_report_frame(jumps: pd.DataFrame, units: pd.DataFrame, checks: pd.DataFrame) -> pd.DataFrame:
    """
    The jump report: every move, every suspected units error, and large
    restated steps at events with a non-simple ratio, which are the spin-offs
    of Amendment 11, decision 5. Reported, never corrected or excluded.
    """
    steps = checks[checks["large_step"] & ~checks["ordinary_ratio"]]
    size = steps["restated_step"].where(steps["restated_step"] >= 1, 1 / steps["restated_step"])
    frames = [
        jumps.assign(record_type="move"),
        units.assign(record_type="units_error", date=pd.to_datetime(units["filed_date"]).dt.strftime("%Y-%m-%d")),
        steps.assign(record_type="spin_off_step", factor=size),
    ]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame(columns=JUMP_REPORT_COLUMNS)
    return pd.concat(frames, ignore_index=True).reindex(columns=JUMP_REPORT_COLUMNS)


# ---------------------------------------------------------------------------
# Reconciliation with the Phase 3 coverage file
# ---------------------------------------------------------------------------

def _names(row: pd.Series) -> str:
    return " ".join(row.index[row])


def reconcile_usable(phase3: pd.DataFrame, used: pd.DataFrame) -> pd.DataFrame:
    """One row per month: Phase 3 count, names lost, names gained and the count used."""
    lost, gained = phase3 & ~used, used & ~phase3
    return pd.DataFrame({
        "month": phase3.index.strftime("%Y-%m"),
        "phase3": phase3.sum(axis=1).values,
        "lost": lost.sum(axis=1).values,
        "gained": gained.sum(axis=1).values,
        "used": used.sum(axis=1).values,
        "lost_names": lost.apply(_names, axis=1).values,
        "gained_names": gained.apply(_names, axis=1).values,
    })


def reconciliation_failures(table: pd.DataFrame, coverage: pd.DataFrame, signal_counts: pd.Series) -> list[str]:
    """
    Every month must close exactly: the Phase 3 count equals the coverage file,
    Phase 3 minus lost plus gained equals the count used, and the count used
    equals the names that actually have a signal.
    """
    expected = coverage.set_index("month")["usable_value_combined"]
    counts = pd.Series(signal_counts.values, index=signal_counts.index.strftime("%Y-%m"))
    failures = []
    for row in table.itertuples():
        if row.phase3 != expected.get(row.month):
            failures.append(f"{row.month}: Phase 3 count {row.phase3}, coverage file {expected.get(row.month)}")
        if row.phase3 - row.lost + row.gained != row.used:
            failures.append(f"{row.month}: {row.phase3} - {row.lost} + {row.gained} is not {row.used}")
        if row.used != counts.get(row.month):
            failures.append(f"{row.month}: {row.used} names used, {counts.get(row.month)} with a signal")
    return failures


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def book_value_jumps(book_value: pd.DataFrame, factor: float = JUMP_FACTOR) -> pd.DataFrame:
    """
    Moves above `factor`, up or down, between a month and the previous month
    with a value. A move across a gap is listed with the gap's length, so a
    series cannot hide a jump behind missing months. Listed, never excluded.
    """
    columns = ["ticker", "month", "previous", "value", "factor", "months_since_previous"]
    rows = []
    for ticker in book_value.columns:
        series = book_value[ticker].dropna()
        if len(series) < 2:
            continue
        ratio = series / series.shift(1)
        size = ratio.where(ratio >= 1, 1 / ratio)
        positions = pd.Series(range(len(book_value)), index=book_value.index).reindex(series.index)
        for date in size.index[size > factor]:
            at = series.index.get_loc(date)
            rows.append({"ticker": ticker, "month": date.strftime("%Y-%m"), "previous": series.iloc[at - 1],
                         "value": series.iloc[at], "factor": size[date],
                         "months_since_previous": int(positions.iloc[at] - positions.iloc[at - 1])})
    return pd.DataFrame(rows, columns=columns)


def pb_range(value: pd.DataFrame, dates: pd.DatetimeIndex | None = None, low: float = LOW_PB) -> dict:
    """Range of the P/B behind a Value signal, over all its months or only `dates`. Report only."""
    rows = -(value if dates is None else value.loc[dates])
    pb = rows.stack().dropna()
    below = rows < low
    return {"name_months": len(pb), "min": pb.min(), "p1": pb.quantile(0.01), "median": pb.median(),
            "p99": pb.quantile(0.99), "max": pb.max(), "below_low": int(below.sum().sum()),
            "months_below_low": int(below.any(axis=1).sum()), "months": len(rows)}


def pb_cases(value: pd.DataFrame, low: float = LOW_PB, top: int = 20) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Name-months with P/B below `low`, and the `top` highest, lowest and highest first. Listed, never excluded."""
    pb = (-value).stack().dropna().rename("pb").rename_axis(["date", "ticker"]).reset_index()
    pb["month"] = pb["date"].dt.strftime("%Y-%m")
    pb = pb[["month", "ticker", "pb"]]
    return pb[pb["pb"] < low].sort_values("pb").reset_index(drop=True), pb.nlargest(top, "pb").reset_index(drop=True)


def is_ordinary_ratio(ratio: float) -> bool:
    """False for ratios such as 1.589, which are usually a spin-off or merger adjustment and not a split."""
    return abs(float(Fraction(ratio).limit_denominator(MAX_DENOMINATOR)) - ratio) < 1e-6


def split_event_check(records: dict, splits: dict) -> pd.DataFrame:
    """
    The filing-date rule on every split: the last filing on or before the
    split and the first after it, as filed and restated. A restated step above
    JUMP_FACTOR suggests the rule did not fit, for example a filing made after
    the split that still uses the old share count. Reported, never repaired.
    """
    rows = []
    for ticker, bv in records.items():
        bv = bv.dropna(subset=["book_value_per_share"])  # a blank from the validity rule has no value to step from
        if bv.empty:
            continue
        restated = restate_book_value(bv, splits[ticker]).sort_values("filed_date", kind="stable")
        ordered = bv.loc[restated.index]
        for date, ratio in splits[ticker].items():
            before = (ordered["filed_date"] <= date).values
            row = {"ticker": ticker, "date": date.strftime("%Y-%m-%d"), "ratio": ratio,
                   "ordinary_ratio": is_ordinary_ratio(ratio), "as_filed_before": float("nan"),
                   "as_filed_after": float("nan"), "restated_before": float("nan"),
                   "restated_after": float("nan"), "restated_step": float("nan"), "large_step": False}
            if before.any() and (~before).any():
                last, first = before.nonzero()[0][-1], (~before).nonzero()[0][0]
                row["as_filed_before"] = ordered["book_value_per_share"].iloc[last]
                row["as_filed_after"] = ordered["book_value_per_share"].iloc[first]
                row["restated_before"] = restated["book_value_per_share"].iloc[last]
                row["restated_after"] = restated["book_value_per_share"].iloc[first]
                step = row["restated_after"] / row["restated_before"]
                row["restated_step"] = step
                row["large_step"] = bool(max(step, 1 / step) > JUMP_FACTOR)
            rows.append(row)
    return pd.DataFrame(rows)
