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


def extract_concept(facts: dict, concept: str, unit: str = "USD") -> pd.DataFrame:
    """
    Extract a single XBRL concept (e.g. StockholdersEquity) as a clean DataFrame
    with columns: end_date, filed_date, value.

    Some reporting periods get refiled/restated and appear more than once in
    the raw data. We keep only the most recently filed version of each period
    (removing the older duplicate), then sort by the actual reporting period
    date so the results read in correct chronological order.
    """
    try:
        entries = facts["facts"]["us-gaap"][concept]["units"][unit]
    except KeyError:
        return pd.DataFrame(columns=["end_date", "filed_date", "value"])

    records = [
        {"end_date": e["end"], "filed_date": e["filed"], "value": e["val"]}
        for e in entries
    ]
    df = pd.DataFrame(records)
    df["end_date"] = pd.to_datetime(df["end_date"])
    df["filed_date"] = pd.to_datetime(df["filed_date"])

    # Remove duplicate periods, keeping the most recently filed version of each
    df = df.sort_values("filed_date").drop_duplicates(subset="end_date", keep="last")

    # Now sort by the actual reporting period so results are in correct order
    df = df.sort_values("end_date").reset_index(drop=True)

    return df


if __name__ == "__main__":
    facts = get_company_facts("AAPL")

    equity = extract_concept(facts, "StockholdersEquity")
    shares = extract_concept(facts, "CommonStockSharesOutstanding", unit="shares")

    print("Stockholders Equity — most recent 3:")
    print(equity.tail(3))

    print("\nShares Outstanding — most recent 3:")
    print(shares.tail(3))