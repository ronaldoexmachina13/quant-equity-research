"""
Fixed book value rule for Phase 4 (LIMITATIONS_PLAN.md, Amendment 9 and
Amendment 10, item 2). Used only by the universe study. src/fundamentals.py is
not changed, and its extract_concept and 45-day share matching are reused.

The existing functions choose between two tags by row order when both carry
the same date and filing date. Here the choice is fixed:
- equity: standard stockholders' equity, because market capitalisation values
  the claim of the parent's common shareholders. Equity including
  noncontrolling interest is used only for a period with no standard figure;
- shares: the balance sheet figure, with the cover page figure only for a date
  with no balance sheet figure;
- two records on one filing date: the one with the newest period end.
The last rule applies to book value records and not to the share list. A 10-K
files its balance sheet count and a later-dated cover count on the same day,
and keeping only the newer date would always discard the preferred figure.
"""
import pandas as pd

from src.fundamentals import extract_concept

EQUITY_TAG = "StockholdersEquity"
EQUITY_WITH_NCI_TAG = "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
BALANCE_SHEET_SHARES_TAG = "CommonStockSharesOutstanding"
COVER_PAGE_SHARES_TAG = "EntityCommonStockSharesOutstanding"
SHARE_MATCH_TOLERANCE = pd.Timedelta(days=45)  # same as get_book_value_per_share()
UNITS_ERROR_FACTOR = 100                       # Amendment 10, item 2
RECORD_COLUMNS = ["end_date", "filed_date", "book_value_per_share"]


def _preferred(primary: pd.DataFrame, fallback: pd.DataFrame) -> pd.DataFrame:
    """All primary rows, plus fallback rows for period ends the primary series does not have."""
    extra = fallback[~fallback["end_date"].isin(primary["end_date"])]
    frames = [frame for frame in (primary, extra) if not frame.empty]
    if not frames:
        return primary
    return pd.concat(frames, ignore_index=True).sort_values("end_date", kind="stable").reset_index(drop=True)


def fixed_equity(facts: dict) -> pd.DataFrame:
    """Equity by period end: standard where it exists, including a negative figure."""
    return _preferred(extract_concept(facts, EQUITY_TAG), extract_concept(facts, EQUITY_WITH_NCI_TAG))


def _positive_shares(facts: dict, tag: str, taxonomy: str) -> pd.DataFrame:
    shares = extract_concept(facts, tag, unit="shares", taxonomy=taxonomy)
    return shares[shares["value"] > 0]


def fixed_shares(facts: dict) -> pd.DataFrame:
    """Share counts by date: balance sheet where it exists, cover page otherwise."""
    return _preferred(_positive_shares(facts, BALANCE_SHEET_SHARES_TAG, "us-gaap"),
                      _positive_shares(facts, COVER_PAGE_SHARES_TAG, "dei"))


def fixed_book_value_records(facts: dict) -> pd.DataFrame:
    """
    Book value per share records under the fixed rule, in the same layout as
    get_book_value_per_share(), so forward_fill_book_value() runs on them
    unchanged. No two records share a filing date, so that function meets no tie.
    """
    equity, shares = fixed_equity(facts), fixed_shares(facts)
    if equity.empty or shares.empty:
        return pd.DataFrame(columns=RECORD_COLUMNS)

    shares = shares.rename(columns={"value": "shares_value", "filed_date": "shares_filed_date"})
    merged = pd.merge_asof(equity, shares, on="end_date", direction="nearest", tolerance=SHARE_MATCH_TOLERANCE)
    merged = merged.dropna(subset=["shares_value"])
    merged["book_value_per_share"] = merged["value"] / merged["shares_value"]
    merged = merged[merged["book_value_per_share"] > 0]
    merged["filed_date"] = merged[["filed_date", "shares_filed_date"]].max(axis=1)

    ordered = merged.sort_values(["filed_date", "end_date"], kind="stable")
    newest = ordered.drop_duplicates("filed_date", keep="last")
    return newest.sort_values("end_date").reset_index(drop=True)[RECORD_COLUMNS]


def suspected_units_errors(facts: dict) -> pd.DataFrame:
    """Filings where the two share tags differ by more than UNITS_ERROR_FACTOR. Listed, never corrected."""
    balance_sheet = _positive_shares(facts, BALANCE_SHEET_SHARES_TAG, "us-gaap")
    cover_page = _positive_shares(facts, COVER_PAGE_SHARES_TAG, "dei")
    if balance_sheet.empty or cover_page.empty:
        return pd.DataFrame(columns=["filed_date", "balance_sheet", "cover_page", "factor"])

    pairs = balance_sheet.merge(cover_page, on="filed_date", suffixes=("_balance", "_cover"))
    ratio = pairs["value_balance"].astype(float) / pairs["value_cover"].astype(float)
    pairs = pairs.assign(balance_sheet=pairs["value_balance"], cover_page=pairs["value_cover"],
                         factor=ratio.where(ratio >= 1, 1 / ratio))
    return pairs.loc[pairs["factor"] > UNITS_ERROR_FACTOR,
                     ["filed_date", "balance_sheet", "cover_page", "factor"]].reset_index(drop=True)
