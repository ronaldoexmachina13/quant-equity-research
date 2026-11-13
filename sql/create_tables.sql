-- ============================================================================
-- create_tables.sql
-- Reference schema for quant-equity-research, matching src/database.py exactly
-- (verified against the real file, not assumed).
--
-- Four tables. prices and book_value are raw-data caches: prices from yfinance,
-- and forward-filled book value per share from SEC EDGAR. portfolio_weights and
-- performance hold the 17-stock study's outputs. Derived quantities (momentum
-- score, P/B) are computed in pandas and persisted only as results/*.csv. See
-- sql/README.md.
-- ============================================================================

CREATE TABLE IF NOT EXISTS prices (
    date        TEXT NOT NULL,
    ticker      TEXT NOT NULL,
    adj_close   REAL NOT NULL,
    PRIMARY KEY (date, ticker)
);

CREATE TABLE IF NOT EXISTS book_value (
    date                    TEXT NOT NULL,
    ticker                  TEXT NOT NULL,
    book_value_per_share    REAL NOT NULL,
    PRIMARY KEY (date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_prices_ticker     ON prices(ticker);
CREATE INDEX IF NOT EXISTS idx_book_value_ticker ON book_value(ticker);

-- ----------------------------------------------------------------------------
-- Output tables written by src/database.py (save_portfolio_weights and
-- save_performance), which run_strategy_comparison.py calls.
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS portfolio_weights (
    date        TEXT NOT NULL,
    ticker      TEXT NOT NULL,
    strategy    TEXT NOT NULL,
    weight      REAL NOT NULL,
    PRIMARY KEY (date, ticker, strategy)
);

CREATE TABLE IF NOT EXISTS performance (
    date              TEXT NOT NULL,
    strategy          TEXT NOT NULL,
    portfolio_value   REAL NOT NULL,
    daily_return      REAL,
    PRIMARY KEY (date, strategy)
);

CREATE INDEX IF NOT EXISTS idx_weights_strategy_date     ON portfolio_weights(strategy, date);
CREATE INDEX IF NOT EXISTS idx_performance_strategy_date ON performance(strategy, date);
