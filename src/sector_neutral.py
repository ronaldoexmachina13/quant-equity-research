"""
Sector-neutral Value (LIMITATIONS_PLAN.md, Amendments 16 and 17). Exploratory and post-results.

Why. The registered Value signal ranks every stock on negative price to book across the whole index.
Banks and energy companies usually have low price to book, so the cheapest decile can end up as a
sector bet. Standardising the score inside each sector, month by month, ranks a stock against its
sector peers instead, so a sector that is cheap as a whole no longer fills the top group.

Rules fixed in Amendment 17: names with no sector are left out, a sector needs at least 10 scored
names in the month to be ranked, and the standardisation is the one in calculate_combined_score(),
the sample standard deviation. Left-out names are counted, not hidden.
"""
import pandas as pd

from src.signal_eval import standardise

MIN_NAMES_PER_SECTOR = 10


def sector_neutral_score(score: pd.DataFrame, sectors: pd.Series, min_names: int = MIN_NAMES_PER_SECTOR) -> tuple:
    """
    Returns (neutral, counts). `score` has one row per date and one column per ticker. `sectors` maps ticker
    to sector, with missing values for unknown sectors. In each row the scored names are standardised
    within their sector. `counts` has one row per date: names_scored, no_sector, small_sector, kept, sectors_ranked.
    """
    neutral = pd.DataFrame(index=score.index, columns=score.columns, dtype=float)
    rows = []
    for date, row in score.iterrows():
        scored = row.dropna()
        sector = sectors.reindex(scored.index)
        no_sector = int(sector.isna().sum())
        known = scored[sector.notna()]
        sizes = sector.dropna().map(sector.dropna().value_counts())
        big = sizes[sizes >= min_names].index
        kept = known.loc[big]
        for name, members in kept.groupby(sector.loc[big]):
            neutral.loc[date, members.index] = standardise(members)
        rows.append({"date": date, "names_scored": len(scored), "no_sector": no_sector,
                     "small_sector": len(known) - len(kept), "kept": len(kept),
                     "sectors_ranked": int(sector.loc[big].nunique())})
    return neutral, pd.DataFrame(rows)


def restrict_to_names(signal: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    """The signal on exactly the names that `reference` has a value for. Used for the control of Amendment 17, decision 5."""
    return signal.where(reference.notna())
