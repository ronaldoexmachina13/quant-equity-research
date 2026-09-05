from src.database import get_connection

conn = get_connection()
cursor = conn.cursor()

# How many total rows, and how many distinct tickers/dates?
cursor.execute("SELECT COUNT(*) FROM prices")
print("Total rows:", cursor.fetchone()[0])

cursor.execute("SELECT COUNT(DISTINCT ticker) FROM prices")
print("Distinct tickers:", cursor.fetchone()[0])

cursor.execute("SELECT MIN(date), MAX(date) FROM prices")
print("Date range:", cursor.fetchone())

# Spot-check: Apple's most recent 5 prices
cursor.execute("""
    SELECT date, adj_close FROM prices
    WHERE ticker = 'AAPL'
    ORDER BY date DESC
    LIMIT 5
""")
print("\nAAPL — most recent 5 rows:")
for row in cursor.fetchall():
    print(row)

conn.close()