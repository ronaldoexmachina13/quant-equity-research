import sqlite3

DB_PATH = "database/quant_research.db"


def get_connection():
    """
    Open a connection to the SQLite database.
    Creates the database file automatically if it doesn't exist yet.
    """
    return sqlite3.connect(DB_PATH)


def create_tables():
    """
    Create the prices table if it does not already exist.
    Safe to run multiple times — will not duplicate or overwrite the table.
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


if __name__ == "__main__":
    create_tables()
    print("Database and prices table created successfully.")