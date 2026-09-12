import sqlite3
import pandas as pd

DB_PATH = "database/quant_research.db"


def get_connection():
    """
    Open a connection to the SQLite database.
    Creates the database file automatically if it doesn't exist yet.
    """
    return sqlite3.connect(DB_PATH)


def create_tables():
    """
    Create the prices and book_value tables if they do not already exist.
    Safe to run multiple times — will not duplicate or overwrite tables.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            adj_close REAL NOT NULL,
            PRIMARY KEY (date, ticker)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS book_value (
            date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            book_value_per_share REAL NOT NULL,
            PRIMARY KEY (date, ticker)
        )
    """)

    conn.commit()
    conn.close()


def save_prices(prices_df):
    """
    Save a wide-format prices DataFrame (Date index, one column per ticker)
    into the prices table. Safe to run multiple times — existing
    (date, ticker) rows are overwritten, not duplicated.

    Parameters
    ----------
    prices_df : pd.DataFrame
        DataFrame with a Date index and one column per ticker,
        as returned by get_price_history_multi().
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Reshape from wide format (one column per ticker) to long format
    # (one row per date-ticker pair) — this matches our table structure.
    long_df = prices_df.reset_index().melt(
        id_vars=prices_df.index.name or "Date",
        var_name="ticker",
        value_name="adj_close"
    )
    long_df.columns = ["date", "ticker", "adj_close"]
    long_df = long_df.dropna(subset=["adj_close"])
    long_df["date"] = long_df["date"].astype(str)

    rows = long_df[["date", "ticker", "adj_close"]].values.tolist()

    cursor.executemany("""
        INSERT OR REPLACE INTO prices (date, ticker, adj_close)
        VALUES (?, ?, ?)
    """, rows)

    conn.commit()
    conn.close()
    print(f"Saved {len(rows)} price rows to the database.")


def save_book_value(bv_df):
    """
    Save a wide-format book-value-per-share DataFrame (Date index, one
    column per ticker) into the book_value table. Same idempotent pattern
    as save_prices() — existing (date, ticker) rows are overwritten, not
    duplicated.

    Parameters
    ----------
    bv_df : pd.DataFrame
        DataFrame with a Date index and one column per ticker, containing
        forward-filled book value per share (e.g. built by combining
        fundamentals.get_book_value_per_share() and
        fundamentals.forward_fill_book_value() for each ticker in the
        universe, aligned to the same month-end dates used for prices).
    """
    conn = get_connection()
    cursor = conn.cursor()

    long_df = bv_df.reset_index().melt(
        id_vars=bv_df.index.name or "date",
        var_name="ticker",
        value_name="book_value_per_share"
    )
    long_df.columns = ["date", "ticker", "book_value_per_share"]
    long_df = long_df.dropna(subset=["book_value_per_share"])
    long_df["date"] = long_df["date"].astype(str)

    rows = long_df[["date", "ticker", "book_value_per_share"]].values.tolist()

    cursor.executemany("""
        INSERT OR REPLACE INTO book_value (date, ticker, book_value_per_share)
        VALUES (?, ?, ?)
    """, rows)

    conn.commit()
    conn.close()
    print(f"Saved {len(rows)} book value rows to the database.")


def load_book_value():
    """
    Load all stored book value per share from the database, reshaped into
    wide format (Date index, one column per ticker) — matches the format
    factors.load_prices() returns, so the two can be combined directly.

    Returns
    -------
    pd.DataFrame
        Wide-format book value per share: Date index, tickers as columns.
    """
    conn = get_connection()
    long_df = pd.read_sql_query("SELECT date, ticker, book_value_per_share FROM book_value", conn)
    conn.close()

    long_df["date"] = pd.to_datetime(long_df["date"])
    wide_df = long_df.pivot(index="date", columns="ticker", values="book_value_per_share")
    wide_df = wide_df.sort_index()
    return wide_df


if __name__ == "__main__":
    create_tables()
    print("Database, prices table, and book_value table created successfully.")