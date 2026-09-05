import yfinance as yf
import pandas as pd


def get_price_history(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Fetch historical adjusted close prices for a single ticker.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol, e.g. "AAPL"
    start_date : str
        Start date in "YYYY-MM-DD" format
    end_date : str
        End date in "YYYY-MM-DD" format

    Returns
    -------
    pd.DataFrame
        DataFrame with Date index and a single "Adj Close" column
    """
    data = yf.download(ticker, start=start_date, end=end_date, auto_adjust=False)
    prices = data[["Adj Close"]]
    return prices


if __name__ == "__main__":
    # Quick manual test: fetch Apple's prices for a short window
    df = get_price_history("AAPL", "2024-01-01", "2024-02-01")
    print(df.head())
    print(f"\nRows returned: {len(df)}")