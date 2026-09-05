from src.data_loader import get_price_history_multi
from src.database import create_tables, save_prices

UNIVERSE = [
    "AAPL", "MSFT", "JPM", "JNJ", "XOM",
    "PG", "KO", "WMT", "HD", "UNH",
    "CAT", "V", "DIS", "NEE", "LIN",
    "LMT", "RTX"
]

START_DATE = "2020-01-01"
END_DATE = "2024-12-31"


if __name__ == "__main__":
    print(f"Fetching prices for {len(UNIVERSE)} tickers from {START_DATE} to {END_DATE}...")

    create_tables()
    prices = get_price_history_multi(UNIVERSE, START_DATE, END_DATE)
    save_prices(prices)

    print("Pipeline complete.")