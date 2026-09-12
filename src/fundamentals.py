import requests
import pandas as pd

HEADERS = {"User-Agent": "Ronaldo ronaldothexz@gmail.com"}

# Ticker -> CIK mapping, fetched once and reused
_TICKER_CIK_MAP = None

# Manual overrides for tickers where SEC's company_tickers.json maps to the
# wrong or a non-historical CIK (e.g. due to a holding-company reorganization
# creating a new registrant under the same ticker). Confirmed via direct
# inspection of SEC's submissions API -- see project notes.
_CIK_OVERRIDES = {
    "XOM": "0000034088",  # Exxon Mobil Corp (pre-2026 Texas redomiciliation entity)
}


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
    if ticker in _CIK_OVERRIDES:
        return _CIK_OVERRIDES[ticker]
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

    Some reporting periods are re-disclosed as comparative figures in later
    filings (e.g. a 2013 10-K re-showing 2009 numbers for comparison), and
    can appear more than once in the raw data. We keep the EARLIEST filed
    version of each period -- the value as first disclosed to the market --
    rather than the latest, so `filed_date` reflects when the number was
    actually first knowable. Using the latest re-appearance instead would
    push `filed_date` years past the true disclosure date, corrupting any
    point-in-time analysis built on top of this function.
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

    df = df.sort_values("filed_date").drop_duplicates(subset="end_date", keep="first")
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

    A tiny number of merge_asof pairings can produce a non-positive or
    zero book-value-per-share (e.g. a zero/negative equity value, or a
    divide-by-near-zero share count from a bad pairing). These are
    dropped as invalid. Note: legitimately low positive book values (e.g.
    HD, which has run with thin book equity due to heavy share buybacks)
    are NOT filtered here -- only non-positive results are excluded.

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
    merged = merged[merged["book_value_per_share"] > 0]  # drop non-positive/zero-division artifacts only
    merged["filed_date"] = merged[["filed_date", "shares_filed_date"]].max(axis=1)

    return merged[["end_date", "filed_date", "book_value_per_share"]]


def forward_fill_book_value(bv_df: pd.DataFrame, target_dates, max_gap_months: int = 6) -> pd.DataFrame:
    """
    Forward-fill book value per share onto a target set of dates (e.g.
    month-ends), using each filing's `filed_date` as the point from which
    that value becomes usable -- a fundamental only becomes knowable once
    it's actually filed, not as of the fiscal period it describes.

    Only fills forward: a value is applied only to target dates on or
    after its filed_date, never before. This preserves point-in-time
    correctness and avoids look-ahead bias.

    A value is not carried forward past `max_gap_months` since its
    filed_date -- beyond that, we treat it as missing rather than stale.

    Parameters
    ----------
    bv_df : pd.DataFrame
        Output of get_book_value_per_share(). Columns: end_date, filed_date,
        book_value_per_share.
    target_dates : iterable of pd.Timestamp
        Dates to fill onto (e.g. month-end dates from your price data).
    max_gap_months : int
        Max months a value can be carried forward before being dropped.

    Returns
    -------
    pd.DataFrame
        Columns: date, book_value_per_share
    """
    if bv_df.empty:
        return pd.DataFrame({"date": list(target_dates), "book_value_per_share": pd.NA})

    bv = bv_df.sort_values("filed_date").reset_index(drop=True)

    rows = []
    for date in sorted(target_dates):
        available = bv[bv["filed_date"] <= date]
        if available.empty:
            rows.append((date, pd.NA))
            continue
        latest = available.iloc[-1]
        gap_days = (date - latest["filed_date"]).days
        if gap_days > max_gap_months * 30:
            rows.append((date, pd.NA))
        else:
            rows.append((date, latest["book_value_per_share"]))

    return pd.DataFrame(rows, columns=["date", "book_value_per_share"])


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


def build_pb_ratios(prices: pd.DataFrame, tickers: list[str], max_gap_months: int = 6) -> pd.DataFrame:
    """
    Compute historical Price-to-Book ratio for each ticker at each month-end,
    by combining month-end adjusted close prices with forward-filled book
    value per share from SEC filings.

    Note: for the Value factor, LOW P/B is attractive (opposite direction
    from momentum, where high score wins) -- this function returns the raw
    ratio only; ranking direction is handled at the portfolio-construction
    stage.

    Parameters
    ----------
    prices : pd.DataFrame
        Wide-format adjusted close prices (Date index, tickers as columns),
        as returned by factors.load_prices().
    tickers : list[str]
        Tickers to compute P/B for.
    max_gap_months : int
        Passed through to forward_fill_book_value() -- max staleness allowed
        for a book value figure before being treated as missing.

    Returns
    -------
    pd.DataFrame
        Wide-format P/B ratios: month-end Date index, tickers as columns.
        NaN where price or book value is unavailable.
    """
    monthly_prices = prices.resample("ME").last()
    target_dates = monthly_prices.index

    pb_columns = {}
    for ticker in tickers:
        bv = get_book_value_per_share(ticker)
        filled_bv = forward_fill_book_value(bv, target_dates, max_gap_months=max_gap_months)
        filled_bv = filled_bv.set_index("date")["book_value_per_share"]

        ticker_price = monthly_prices[ticker]
        pb_columns[ticker] = ticker_price / filled_bv

    pb_df = pd.DataFrame(pb_columns)
    pb_df.index.name = "date"
    return pb_df


if __name__ == "__main__":
    UNIVERSE = [
        "AAPL", "MSFT", "JPM", "JNJ", "XOM",
        "PG", "KO", "WMT", "HD", "UNH",
        "CAT", "V", "DIS", "NEE", "LIN",
        "LMT", "RTX"
    ]

    all_bvps = get_book_value_for_universe(UNIVERSE)

    print(f"\nSuccessfully fetched: {len(all_bvps)} of {len(UNIVERSE)} tickers")