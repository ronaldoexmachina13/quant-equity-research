import json

import pandas as pd

from config import UNIVERSE
from src.database import load_book_value
from src.factors import load_prices, calculate_momentum


def compute_stocks_data() -> dict:
    """
    Compute the dynamic, backtest-derived fields for every ticker in
    UNIVERSE: latest price, latest momentum, latest Price/Book, and how
    many of the backtest's months each strategy actually held it.

    Deliberately does NOT compute or touch a ticker's name or sector --
    those are static reference facts (like COMPANY_NAMES in
    portfolio.html), not something derived from the backtest, and stay
    hand-maintained in stocks.html itself.
    """
    prices = load_prices()
    book_value = load_book_value()
    momentum = calculate_momentum(prices)

    monthly_prices = prices.resample("ME").last()
    pb_ratio = monthly_prices / book_value  # NaN where no book value exists (e.g. V)

    with open("results/portfolio_timeline.json") as f:
        timeline = json.load(f)
    holdings = timeline["holdings"]

    total_months = len(holdings["momentum"])  # same common-dates count for all 3 strategies

    counts = {strategy: {t: 0 for t in UNIVERSE} for strategy in ["momentum", "value", "combined"]}
    for strategy, months in holdings.items():
        for month, tickers in months.items():
            for t in tickers:
                counts[strategy][t] += 1

    # Same counts for the out-of-sample months (Jan 2025 - Aug 2026), kept
    # separate so the page can show them without mixing the two periods.
    with open("results/portfolio_timeline_oos.json") as f:
        holdings_oos = json.load(f)["holdings"]
    total_months_oos = len(holdings_oos["momentum"])
    counts_oos = {strategy: {t: 0 for t in UNIVERSE} for strategy in ["momentum", "value", "combined"]}
    for strategy, months in holdings_oos.items():
        for month, tickers in months.items():
            for t in tickers:
                counts_oos[strategy][t] += 1

    latest_price_row = prices.iloc[-1]
    latest_momentum_row = momentum.iloc[-1]
    latest_pb_row = pb_ratio.iloc[-1]

    computed = {}
    for t in UNIVERSE:
        pb = latest_pb_row.get(t)
        computed[t] = {
            "latest_price": round(float(latest_price_row[t]), 2),
            "latest_momentum_12_1": round(float(latest_momentum_row[t]), 3),
            "latest_pb": None if pd.isna(pb) else round(float(pb), 2),
            "momentum_months_selected": counts["momentum"][t],
            "value_months_selected": counts["value"][t],
            "combined_months_selected": counts["combined"][t],
            "total_months_evaluated": total_months,
            "momentum_months_selected_oos": counts_oos["momentum"][t],
            "value_months_selected_oos": counts_oos["value"][t],
            "combined_months_selected_oos": counts_oos["combined"][t],
            "total_months_oos": total_months_oos,
        }
    return computed


if __name__ == "__main__":
    computed = compute_stocks_data()
    with open("results/stocks_data.json", "w") as f:
        json.dump(computed, f, indent=2)
    print(f"Computed stocks data for {len(computed)} tickers")
    print("Saved to results/stocks_data.json")