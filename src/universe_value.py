"""
Value and Combined path for Phase 4 (LIMITATIONS_PLAN.md, Amendments 8 to 10).

Book value per share follows the fixed rule in src/book_value_rule.py and is
restated to the price's share basis by the filing-date rule in
src/split_adjust.py. Value uses the split-adjusted close, which is not adjusted
for dividends. calculate_value_score() and calculate_combined_score() are
called unchanged.

The usable set for Value and Combined is defined by the fixed rule: names
usable for Momentum with a book value at the end of t-1. It is reconciled to
the Phase 3 coverage file by name, month by month (Amendment 10, item 1).
"""
from fractions import Fraction

import pandas as pd

from src.book_value_rule import fixed_book_value_records, suspected_units_errors
from src.factors import calculate_value_score, calculate_combined_score
from src.split_adjust import restate_book_value
from src.universe import cache_dir, write_bytes_atomic

SPLIT_CUTOFF = "2026-10-28"   # Amendment 10, item 3: the cached closes carry adjustments up to this date
JUMP_FACTOR = 2.0             # Amendment 8: a move above this in a month is listed
MAX_DENOMINATOR = 20          # a ratio is read as an ordinary split if it is a simple fraction, such as 3:2 or 1:20


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
    """({ticker: fixed-rule records}, suspected units errors with their ticker) from a facts reader."""
    records, errors = {}, []
    for ticker in tickers:
        facts = read_facts(ticker)
        records[ticker] = fixed_book_value_records(facts)
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
