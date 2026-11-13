from src.data_loader import get_price_history_multi
from src.database import create_tables, save_prices
from config import UNIVERSE, START_DATE, END_DATE


if __name__ == "__main__":
    print(f"Fetching prices for {len(UNIVERSE)} tickers from {START_DATE} to {END_DATE}...")

    create_tables()
    prices = get_price_history_multi(UNIVERSE, START_DATE, END_DATE)
    save_prices(prices)

    print("Pipeline complete.")