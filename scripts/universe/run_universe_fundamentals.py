"""
Phase 3, step 3 of 4: CIK mapping and book value availability from SEC EDGAR.

Reuses src/fundamentals.py unchanged (Amendment 6, item 7):
- the ticker to CIK map comes from the existing _load_ticker_cik_map() and
  get_cik() (including the XOM override); the map is cached on first use;
- company facts are downloaded once per CIK and cached; at run time
  fundamentals.get_company_facts is replaced by a cache-only reader with
  the same signature, so get_book_value_per_share and
  forward_fill_book_value run exactly as in the published study.

Only presence is stored: whether a book value exists at each calendar
month end. At most 8 SEC requests per second, with the existing User-Agent.
An HTTP 404 is a confirmed empty result; any other failure is retried up
to three times and then listed as an error, never counted as missing.
"""
import json
import sqlite3

import pandas as pd
import requests

import src.fundamentals as fundamentals
from src.universe import (
    FEASIBILITY_DB_PATH, FIRST_PRICE_MONTH, EVALUATION_END, SEC_MAX_REQUESTS_PER_SECOND,
    cache_dir, month_range, tickers_in_window, book_value_months, make_cached_company_facts,
    download_with_retries, RateLimiter, write_gzip_json, write_json, create_feasibility_tables,
)

COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"  # as in fundamentals.get_company_facts


class SecNotFound(Exception):
    """HTTP 404 from the SEC: the company has no XBRL company facts."""


def load_ticker_cik_map(limiter: RateLimiter):
    """Fill fundamentals._TICKER_CIK_MAP from the cache, or fetch it once with the existing function."""
    path = cache_dir() / "sec" / "company_tickers_map.json"
    if path.exists():
        fundamentals._TICKER_CIK_MAP = json.loads(path.read_text(encoding="utf-8"))
        print(f"Using cached SEC ticker map: {path}")
        return

    def fetch():
        limiter.wait()
        fundamentals._TICKER_CIK_MAP = None
        return fundamentals._load_ticker_cik_map()

    status, cik_map, attempts, message = download_with_retries(fetch, is_missing=lambda exc: False,
                                                               missing_confirmations=1)
    if status != "ok":
        raise SystemExit(f"SEC ticker file download failed after {attempts} attempts: {message}")
    write_json(path, cik_map)
    print(f"Downloaded and cached SEC ticker map ({len(cik_map)} tickers): {path}")


def map_tickers(tickers: list[str]) -> dict:
    """{ticker: cik or None}. Unmapped names are kept with None, never dropped."""
    mapping = {}
    for ticker in tickers:
        try:
            mapping[ticker] = fundamentals.get_cik(ticker)
        except KeyError:
            mapping[ticker] = None
    return mapping


def facts_paths(cik: str):
    folder = cache_dir() / "sec" / "companyfacts"
    return folder / f"CIK{cik}.json.gz", folder / f"CIK{cik}.empty.json"


def fetch_company_facts(cik: str, limiter: RateLimiter) -> dict:
    limiter.wait()
    response = requests.get(COMPANY_FACTS_URL.format(cik=cik), headers=fundamentals.HEADERS, timeout=120)
    if response.status_code == 404:
        raise SecNotFound(f"CIK {cik}: HTTP 404")
    response.raise_for_status()
    return response.json()


def download_all_facts(ciks: list[str], limiter: RateLimiter) -> dict:
    """Download company facts for every CIK not cached yet. Returns {cik: (status, attempts, message)} for this run."""
    run_status = {}
    pending = [c for c in ciks if not any(p.exists() for p in facts_paths(c))]
    print(f"{len(ciks) - len(pending)} of {len(ciks)} CIKs already cached; downloading {len(pending)}.")
    for i, cik in enumerate(pending, start=1):
        data_path, empty_path = facts_paths(cik)
        status, facts, attempts, message = download_with_retries(
            lambda: fetch_company_facts(cik, limiter), lambda exc: isinstance(exc, SecNotFound),
            missing_confirmations=1)
        if status == "ok":
            write_gzip_json(data_path, facts)
        elif status == "empty":
            write_json(empty_path, {"cik": cik, "attempts": attempts, "message": message})
        run_status[cik] = (status, attempts, message)
        print(f"  [{i}/{len(pending)}] CIK {cik}: {status}" + (f" ({message})" if status != "ok" else ""))
    return run_status


def facts_status(cik: str, run_status: dict):
    data_path, empty_path = facts_paths(cik)
    if data_path.exists():
        return "ok", None, None
    if empty_path.exists():
        return "empty", None, empty_path.read_text(encoding="utf-8")
    status, attempts, message = run_status.get(cik, ("error", None, "not attempted in this run"))
    return "error", attempts, message


def build_book_value_presence(mapping: dict, months: list[str]) -> tuple[list, dict]:
    """
    Book value presence rows (ticker, month) for every mapped ticker whose
    facts are cached, using the existing functions on cached facts.
    Returns (rows, errors) where errors maps ticker to a message.
    """
    fundamentals.get_company_facts = make_cached_company_facts(fundamentals.get_cik,
                                                               cache_dir() / "sec" / "companyfacts")
    rows, errors = [], {}
    for ticker, cik in sorted(mapping.items()):
        if cik is None:
            continue
        try:
            bv = fundamentals.get_book_value_per_share(ticker)
        except FileNotFoundError as exc:
            errors[ticker] = str(exc)
            continue
        except Exception as exc:
            errors[ticker] = f"book value computation failed: {type(exc).__name__}: {exc}"
            continue
        rows.extend((ticker, m) for m in book_value_months(bv, months, fundamentals.forward_fill_book_value))
    return rows, errors


if __name__ == "__main__":
    conn = sqlite3.connect(FEASIBILITY_DB_PATH)
    create_feasibility_tables(conn)
    intervals = pd.read_sql_query("SELECT * FROM index_membership", conn)
    if intervals.empty:
        raise SystemExit("index_membership is empty; run run_universe_membership.py first.")

    months = month_range(FIRST_PRICE_MONTH, EVALUATION_END)
    tickers = tickers_in_window(intervals, months)
    limiter = RateLimiter(SEC_MAX_REQUESTS_PER_SECOND)
    print(f"SEC step for {len(tickers)} tickers. Cache: {cache_dir() / 'sec'}")

    load_ticker_cik_map(limiter)
    mapping = map_tickers(tickers)
    unmapped = sorted(t for t, c in mapping.items() if c is None)
    ciks = sorted({c for c in mapping.values() if c is not None})
    print(f"Mapped to a CIK: {len(tickers) - len(unmapped)} tickers ({len(ciks)} distinct CIKs). "
          f"Unmapped: {len(unmapped)}")

    run_status = download_all_facts(ciks, limiter)

    conn.execute("DELETE FROM ticker_cik")
    conn.executemany("INSERT INTO ticker_cik VALUES (?, ?)", sorted(mapping.items()))
    conn.execute("DELETE FROM download_status WHERE source = 'sec_facts'")
    conn.executemany("INSERT INTO download_status VALUES ('sec_facts', ?, ?, ?, ?)",
                     [(cik, *facts_status(cik, run_status)) for cik in ciks])

    rows, bv_errors = build_book_value_presence(mapping, months)
    conn.execute("DELETE FROM book_value_month_end")
    conn.executemany("INSERT INTO book_value_month_end VALUES (?, ?)", rows)
    conn.execute("DELETE FROM download_status WHERE source = 'sec_book_value'")
    conn.executemany("INSERT INTO download_status VALUES ('sec_book_value', ?, 'error', NULL, ?)",
                     sorted(bv_errors.items()))
    conn.commit()

    counts = pd.read_sql_query(
        "SELECT status, COUNT(*) AS ciks FROM download_status WHERE source = 'sec_facts' GROUP BY status", conn)
    print("\nCompany facts status:\n" + counts.to_string(index=False))
    print(f"book_value_month_end: {len(rows)} ticker-months with book value, "
          f"{len({t for t, _ in rows})} tickers with at least one.")
    if bv_errors:
        print(f"\nTickers without a book value result because of an error ({len(bv_errors)}):")
        for ticker, message in sorted(bv_errors.items()):
            print(f"  {ticker}: {message}")
    print(f"\nUnmapped tickers ({len(unmapped)}): {', '.join(unmapped)}")
    conn.close()
    print("\nFundamentals step complete.")
