import requests
import pandas as pd

HEADERS = {"User-Agent": "Ronaldo ronaldothexz@gmail.com"}

# Ticker -> CIK mapping, fetched once and reused
_TICKER_CIK_MAP = None


def _load_ticker_cik_map() -> dict:
    """Fetch and cache the SEC's full ticker -> CIK mapping."""
    global _TICKER_CIK_MAP
    if _TICKER_CIK_MAP is None:
        url = "https://www.sec.gov/files/company_tickers.json"
        response = requests.get(url, headers=HEADERS)
        data = response.json()
        _TICKER_CIK_MAP = {
            entry["ticker"]: str(entry["cik_str"]).zfill(10)
            for entry in data.values()
        }
    return _TICKER_CIK_MAP


def get_cik(ticker: str) -> str:
    """Look up a ticker's 10-digit zero-padded CIK."""
    cik_map = _load_ticker_cik_map()
    return cik_map[ticker]


def get_company_facts(ticker: str) -> dict:
    """Fetch the full XBRL company facts JSON for a ticker."""
    cik = get_cik(ticker)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    response = requests.get(url, headers=HEADERS)
    return response.json()


def extract_concept(facts: dict, concept: str, unit: str = "USD", taxonomy: str = "us-gaap") -> pd.DataFrame:
    """
    Extract a single XBRL concept as a clean DataFrame with columns:
    end_date, filed_date, value.

    Different companies sometimes report the same underlying figure under
    different XBRL tags or taxonomies. If the requested concept isn't found,
    an empty DataFrame is returned rather than raising an error, so callers
    can try a fallback tag.

    Some reporting periods get refiled/restated and appear more than once
    in the raw data. We keep only the most recently filed version of each
    period, then sort by the actual reporting period date so results read
    in correct chronological order.
    """
    try:
        entries = facts["facts"][taxonomy][concept]["units"][unit]
    except KeyError:
        empty = pd.DataFrame(columns=["end_date", "filed_date", "value"])
        empty["end_date"] = pd.to_datetime(empty["end_date"])
        empty["filed_date"] = pd.to_datetime(empty["filed_date"])
        return empty
    records = [
        {"end_date": e["end"], "filed_date": e["filed"], "value": e["val"]}
        for e in entries
    ]
    df = pd.DataFrame(records)
    df["end_date"] = pd.to_datetime(df["end_date"])
    df["filed_date"] = pd.to_datetime(df["filed_date"])

    df = df.sort_values("filed_date").drop_duplicates(subset="end_date", keep="last")
    df = df.sort_values("end_date").reset_index(drop=True)

    return df


def get_shares_outstanding(facts: dict) -> pd.DataFrame:
    """
    Get shares outstanding by combining both the us-gaap and dei tags,
    rather than treating one as a strict fallback for the other. Some
    companies populate one tag far more consistently than the other, so
    taking the union of both sources (keeping the most recently filed
    value for any overlapping dates) gives materially better coverage
    than trying one tag and only falling back if it's completely empty.

    Rows with a non-positive share count are dropped as invalid data —
    a company can never legitimately report zero or negative shares
    outstanding, so such values reflect a filing/tagging error rather
    than a real state.
    """
    gaap_shares = extract_concept(facts, "CommonStockSharesOutstanding", unit="shares")
    dei_shares = extract_concept(facts, "EntityCommonStockSharesOutstanding", unit="shares", taxonomy="dei")

    combined = pd.concat([gaap_shares, dei_shares], ignore_index=True)
    if combined.empty:
        return combined

    combined = combined[combined["value"] > 0]

    combined = combined.sort_values("filed_date").drop_duplicates(subset="end_date", keep="last")
    combined = combined.sort_values("end_date").reset_index(drop=True)

    return combined

def get_stockholders_equity(facts: dict) -> pd.DataFrame:
    """
    Get stockholders' equity by combining the standard tag and the
    "including noncontrolling interest" variant, rather than treating
    one as a strict fallback for the other. Some companies (e.g. those
    with partially-owned subsidiaries) populate the NCI-inclusive tag
    far more consistently than the standard tag, so taking the union of
    both gives materially better coverage.
    """
    standard = extract_concept(facts, "StockholdersEquity")
    including_nci = extract_concept(facts, "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")

    combined = pd.concat([standard, including_nci], ignore_index=True)
    if combined.empty:
        return combined

    combined = combined.sort_values("filed_date").drop_duplicates(subset="end_date", keep="last")
    combined = combined.sort_values("end_date").reset_index(drop=True)

    return combined


def get_book_value_per_share(ticker: str) -> pd.DataFrame:
    """
    Compute historical book value per share for a ticker by combining
    stockholders' equity and shares outstanding from SEC filings.

    Equity and shares outstanding are sometimes reported as of slightly
    different dates within the same reporting period (e.g. shares
    outstanding reported as of a filing's cover-page date, a few weeks
    after the fiscal quarter-end used for equity). An exact-date match
    would silently miss these pairs, so we match each equity date to the
    nearest available shares date within a 45-day tolerance window instead.

    Returns
    -------
    pd.DataFrame
        Columns: end_date, filed_date, book_value_per_share
    """
    facts = get_company_facts(ticker)
    equity = get_stockholders_equity(facts)
    shares = get_shares_outstanding(facts)

    if equity.empty or shares.empty:
        return pd.DataFrame(columns=["end_date", "filed_date", "book_value_per_share"])

    equity = equity.sort_values("end_date")
    shares = shares.sort_values("end_date").rename(
        columns={"value": "shares_value", "filed_date": "shares_filed_date"}
    )

    merged = pd.merge_asof(
        equity, shares,
        on="end_date",
        direction="nearest",
        tolerance=pd.Timedelta(days=45)
    )
    merged = merged.dropna(subset=["shares_value"])

    merged["book_value_per_share"] = merged["value"] / merged["shares_value"]
    merged["filed_date"] = merged[["filed_date", "shares_filed_date"]].max(axis=1)

    return merged[["end_date", "filed_date", "book_value_per_share"]]


def get_book_value_for_universe(tickers: list[str]) -> dict:
    """
    Fetch book value per share history for multiple tickers.

    Returns
    -------
    dict
        {ticker: DataFrame} — one book-value-per-share DataFrame per ticker.
        Tickers that fail to fetch (e.g. missing EDGAR data) are skipped,
        with a warning printed rather than halting the whole run.
    """
    results = {}
    for ticker in tickers:
        try:
            bvps = get_book_value_per_share(ticker)
            results[ticker] = bvps
            print(f"{ticker}: {len(bvps)} book value data points")
        except Exception as e:
            print(f"{ticker}: FAILED — {e}")
    return results


if __name__ == "__main__":
    UNIVERSE = [
        "AAPL", "MSFT", "JPM", "JNJ", "XOM",
        "PG", "KO", "WMT", "HD", "UNH",
        "CAT", "V", "DIS", "NEE", "LIN",
        "LMT", "RTX"
    ]

    all_bvps = get_book_value_for_universe(UNIVERSE)

    print(f"\nSuccessfully fetched: {len(all_bvps)} of {len(UNIVERSE)} tickers")