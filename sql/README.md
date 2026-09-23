# SQL analytical layer

The SQLite database stores the raw inputs (`prices`, `book_value`) and the backtest outputs (`portfolio_weights`, `performance`). The queries in this folder reproduce the main parts of the analysis directly in SQL, as an independent check on the Python pipeline.

## Files

- `create_tables.sql`: schema reference for all four tables, matching `src/database.py`.
- `factor_construction_in_sql.sql`: 12-1 momentum and Price-to-Book computed from `prices` and `book_value` with window functions and a join, plus a data-coverage diagnostic. Output matches `src/factors.py` (for example, AAPL 12-1 momentum at the end of December 2024: 0.2387 in SQL, 0.23873 in pandas).
- `portfolio_and_regime_queries.sql`: monthly turnover by strategy, regime-split (2021–2022 vs 2023–2024) Sharpe ratio and maximum drawdown, and month-by-month holdings overlap between Momentum and Value.

## How to run

Run the pipeline first (see "Reproducing this project end-to-end" in the main README). `run_strategy_comparison.py` populates `portfolio_weights` (720 rows: 48 months × 5 holdings × 3 strategies) and `performance` (192 rows: 48 months × 4 series). Then run any query file against `database/quant_research.db`, for example with the `sqlite3` command-line tool or DB Browser for SQLite.

## Design choices

- **What lives in SQL and what stays in pandas.** Raw data and final outputs are stored in the database, where they can be queried and audited. Signal construction and the backtest loop stay in Python, where they are unit-tested. The SQL queries recompute key results from the stored data so that the two implementations can be checked against each other.
- **Idempotent writes.** All save functions use `INSERT OR REPLACE` keyed on each table's primary key (date and ticker, plus strategy where relevant), so rerunning the pipeline updates rows rather than duplicating them.

## Known scope limit

There is no `companies` or sector table yet, so no sector-concentration query is included. Adding one needs a small ingestion step (a static ticker-to-sector mapping, since the universe is fixed at 17 names).
