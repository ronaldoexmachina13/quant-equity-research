-- ============================================================================
-- factor_construction_in_sql.sql
-- Computes the momentum and value signals directly in SQL, against the real
-- prices/book_value schema. This is deliberately doing signal construction,
-- not just aggregation -- it's meant to demonstrate that SQL can do real
-- analytical work here, not just cache data for pandas to read back out.
--
-- These queries operate on DAILY prices (yfinance) and derive month-end
-- snapshots inline, since neither table stores a pre-computed "month-end"
-- flag. If book_value is only ever written at month-end already (check this
-- against how generate_dashboard_data.py / factors.py build bv_df before
-- calling save_book_value), the month-end step in query 1 is still safe to
-- run -- it's a no-op on data that's already one row per ticker per month.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Momentum signal: 12-month return, skipping the most recent month ("12-1"),
--    computed at each month-end. This is the same signal src/factors.py builds
--    in pandas -- this query is meant as an independent verification of it,
--    not a replacement. If the two disagree, that's worth knowing before an
--    interview, not after.
-- ----------------------------------------------------------------------------
WITH month_end AS (
    SELECT
        ticker,
        date,
        adj_close,
        ROW_NUMBER() OVER (
            PARTITION BY ticker, strftime('%Y-%m', date)
            ORDER BY date DESC
        ) AS rn_in_month
    FROM prices
),
monthly_prices AS (
    SELECT ticker, date, adj_close
    FROM month_end
    WHERE rn_in_month = 1        -- keep only the last trading day of each month
),
lagged AS (
    SELECT
        ticker,
        date,
        adj_close,
        LAG(adj_close, 1)  OVER (PARTITION BY ticker ORDER BY date) AS price_1m_ago,
        LAG(adj_close, 12) OVER (PARTITION BY ticker ORDER BY date) AS price_12m_ago
    FROM monthly_prices
)
SELECT
    ticker,
    date,
    price_12m_ago,
    price_1m_ago,
    ROUND((price_1m_ago / price_12m_ago) - 1, 4) AS momentum_12_1
FROM lagged
WHERE price_1m_ago IS NOT NULL
  AND price_12m_ago IS NOT NULL
ORDER BY ticker, date;


-- ----------------------------------------------------------------------------
-- 2. Value signal: Price-to-Book at each month-end, joining month-end prices
--    to the point-in-time (already forward-filled) book value.
-- ----------------------------------------------------------------------------
WITH month_end AS (
    SELECT
        ticker,
        date,
        adj_close,
        ROW_NUMBER() OVER (
            PARTITION BY ticker, strftime('%Y-%m', date)
            ORDER BY date DESC
        ) AS rn_in_month
    FROM prices
),
monthly_prices AS (
    SELECT ticker, date, adj_close
    FROM month_end
    WHERE rn_in_month = 1
)
SELECT
    p.ticker,
    p.date,
    p.adj_close,
    b.book_value_per_share,
    ROUND(p.adj_close / NULLIF(b.book_value_per_share, 0), 4) AS price_to_book
FROM monthly_prices p
JOIN book_value b
    ON b.ticker = p.ticker
    AND b.date = p.date
ORDER BY p.ticker, p.date;


-- ----------------------------------------------------------------------------
-- 3. Coverage diagnostic: for each ticker, how many month-end dates have a
--    price but no matching book_value row. This is the SQL-native version of
--    the coverage table in the README (HD at 47/60, V at 0/60, etc.) -- run
--    this and compare the counts to what's currently written in the README
--    as a direct correctness check, not just a restatement of it.
-- ----------------------------------------------------------------------------
WITH month_end_prices AS (
    SELECT DISTINCT
        ticker,
        strftime('%Y-%m', date) AS year_month
    FROM prices
),
month_end_bv AS (
    SELECT DISTINCT
        ticker,
        strftime('%Y-%m', date) AS year_month
    FROM book_value
)
SELECT
    p.ticker,
    COUNT(*) AS months_with_price,
    COUNT(b.year_month) AS months_with_book_value,
    COUNT(*) - COUNT(b.year_month) AS months_missing_book_value
FROM month_end_prices p
LEFT JOIN month_end_bv b
    ON b.ticker = p.ticker
    AND b.year_month = p.year_month
GROUP BY p.ticker
ORDER BY months_missing_book_value DESC;
