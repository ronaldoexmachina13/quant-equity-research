-- ============================================================================
-- portfolio_and_regime_queries.sql
--
-- REQUIRES TIER B. These queries reference portfolio_weights and performance,
-- which do not exist until src/database.py is patched per
-- src_patch/database_py_additions.md AND run_strategy_comparison.py has been
-- re-run at least once afterward. Running this file against the database
-- before that will fail with "no such table" -- that failure is correct
-- behavior, not a bug in this file.
--
-- No sector/company table exists in this schema, so a sector-concentration
-- query isn't included here -- that would need a new companies(ticker,
-- sector) table and its own ingestion step, which is a real future addition,
-- not something to fake with a query against data that isn't there.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Monthly turnover by strategy.
-- A ticker held last month and still held this month contributes 0 to
-- turnover; a ticker entering or exiting contributes 1. Matches the README's
-- definition: "a stock that stays held doesn't get charged again."
-- ----------------------------------------------------------------------------
WITH membership AS (
    SELECT
        strategy,
        ticker,
        date,
        1 AS held,
        LAG(1, 1, 0) OVER (
            PARTITION BY strategy, ticker ORDER BY date
        ) AS held_prev_month
    FROM portfolio_weights
),
changes AS (
    SELECT
        strategy,
        date,
        SUM(CASE WHEN held_prev_month = 0 THEN 1 ELSE 0 END) AS entries,
        COUNT(*)                                              AS total_held
    FROM membership
    GROUP BY strategy, date
)
SELECT
    strategy,
    date,
    entries,
    total_held,
    ROUND(1.0 * entries / NULLIF(total_held, 0), 4) AS turnover_fraction
FROM changes
ORDER BY strategy, date;


-- ----------------------------------------------------------------------------
-- 2. Annualized Sharpe ratio by strategy and regime (2021-2022 vs 2023-2024),
-- computed in SQL from daily_return. Flat 2% annual risk-free rate, matching
-- the rest of the project. Compare this output directly against the numbers
-- already in strategies.html's Robustness tab -- they should match closely;
-- if they don't, find out why before anyone else does.
-- ----------------------------------------------------------------------------
WITH regime_returns AS (
    SELECT
        strategy,
        CASE
            WHEN date BETWEEN '2021-01-01' AND '2022-12-31' THEN '2021-2022'
            WHEN date BETWEEN '2023-01-01' AND '2024-12-31' THEN '2023-2024'
        END AS regime,
        daily_return
    FROM performance
    WHERE date BETWEEN '2021-01-01' AND '2024-12-31'
      AND daily_return IS NOT NULL
)
SELECT
    strategy,
    regime,
    COUNT(*) AS n_periods,
    ROUND(AVG(daily_return) * 12, 4) AS annualized_return,
    ROUND(
        (AVG(daily_return) * 12 - 0.02) / NULLIF(
            SQRT(
                (SUM(daily_return * daily_return) - SUM(daily_return) * SUM(daily_return) / COUNT(*))
                / NULLIF(COUNT(*) - 1, 0)
            ) * SQRT(12),
        0),
    4) AS sharpe_ratio
FROM regime_returns
WHERE regime IS NOT NULL
GROUP BY strategy, regime
ORDER BY strategy, regime;


-- ----------------------------------------------------------------------------
-- 3. Max drawdown by strategy and regime.
-- ----------------------------------------------------------------------------
WITH regime_perf AS (
    SELECT
        strategy,
        date,
        portfolio_value,
        CASE
            WHEN date BETWEEN '2021-01-01' AND '2022-12-31' THEN '2021-2022'
            WHEN date BETWEEN '2023-01-01' AND '2024-12-31' THEN '2023-2024'
        END AS regime
    FROM performance
),
running_peak AS (
    SELECT
        strategy,
        regime,
        date,
        portfolio_value,
        MAX(portfolio_value) OVER (
            PARTITION BY strategy, regime ORDER BY date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_peak_value
    FROM regime_perf
    WHERE regime IS NOT NULL
)
SELECT
    strategy,
    regime,
    ROUND(MIN((portfolio_value - running_peak_value) / running_peak_value), 4) AS max_drawdown
FROM running_peak
GROUP BY strategy, regime
ORDER BY strategy, regime;


-- ----------------------------------------------------------------------------
-- 4. Momentum vs Value holdings overlap, by month.
-- Backs the README's claim: "momentum and value overlapped on 3 of their 5
-- holdings" for December 2024. This generalizes that one spot-check to every
-- month in the backtest.
-- ----------------------------------------------------------------------------
SELECT
    m.date,
    COUNT(*) AS overlapping_tickers,
    GROUP_CONCAT(m.ticker) AS shared_holdings
FROM portfolio_weights m
JOIN portfolio_weights v
    ON m.date = v.date
    AND m.ticker = v.ticker
    AND m.strategy = 'momentum'
    AND v.strategy = 'value'
GROUP BY m.date
ORDER BY m.date;
