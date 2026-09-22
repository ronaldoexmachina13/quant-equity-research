-- ============================================================================
-- create_tables.sql
-- Reference schema for quant-equity-research, matching src/database.py exactly
-- (verified against the real file, not assumed).
--
-- Two tables. Both are raw-data caches: prices from yfinance, and forward-filled
-- book value per share from SEC EDGAR. All derived quantities (momentum score,
-- P/B, portfolio weights, backtest performance) are currently computed in
-- pandas and only ever persisted as results/*.csv, not written back to SQLite.
-- See sql/README.md for what that implies and what Tier B would change.
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
-- Tier B additions (require src/database.py to be patched — see
-- src_patch/database_py_additions.md). Not yet in the live database until
-- run_strategy_comparison.py is re-run after that patch is applied.
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
