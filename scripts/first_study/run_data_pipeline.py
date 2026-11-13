import sys
from src.data_loader import get_price_history_multi
from src.database import create_tables, save_prices
from config import UNIVERSE, START_DATE, END_DATE
from src.output_guard import refuse_if_table_has_rows


if __name__ == "__main__":
    refuse_if_table_has_rows("prices", sys.argv)
    print(f"Fetching prices for {len(UNIVERSE)} tickers from {START_DATE} to {END_DATE}...")

    create_tables()
    prices = get_price_history_multi(UNIVERSE, START_DATE, END_DATE)
    save_prices(prices)

    print("Pipeline complete.")