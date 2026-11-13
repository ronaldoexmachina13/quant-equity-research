-- ============================================================================
-- portfolio_and_regime_queries.sql
--
-- These queries reference portfolio_weights and performance, which are
-- written by run_strategy_comparison.py. Running this file against a database
-- that script has not populated fails with "no such table".
--
-- No sector/company table exists in this schema, so a sector-concentration
-- query isn't included here -- that would need a new companies(ticker,
-- sector) table and its own ingestion step, which is a real future addition,
-- not something to fake with a query against data that isn't there.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Monthly turnover by strategy.
-- A ticker held at the previous rebalance date and still held now contributes 0 to
-- turnover; a ticker that was not held at the previous date contributes 1. A ticker
-- that leaves and comes back counts as an entry when it comes back. The previous date
-- is the previous date of the same strategy, not the previous row of the ticker.
-- Matches the README's definition: "a stock that stays held doesn't get charged again."
-- ----------------------------------------------------------------------------
WITH rebalance_dates AS (
    SELECT
        strategy,
        date,
        LAG(date) OVER (PARTITION BY strategy ORDER BY date) AS prev_date
    FROM (SELECT DISTINCT strategy, date FROM portfolio_weights)
),
membership AS (
    SELECT
        w.strategy,
        w.ticker,
        w.date,
        CASE WHEN p.ticker IS NULL THEN 1 ELSE 0 END AS is_entry
    FROM portfolio_weights AS w
    JOIN rebalance_dates AS d
        ON d.strategy = w.strategy AND d.date = w.date
    LEFT JOIN portfolio_weights AS p
        ON p.strategy = w.strategy AND p.ticker = w.ticker AND p.date = d.prev_date
),
changes AS (
    SELECT
        strategy,
        date,
        SUM(is_entry)  AS entries,
        COUNT(*)       AS total_held
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
-- the rest of the project. Compare the output with the Sharpe ratios in
-- results/strategy_comparison_2021_2022.csv and strategy_comparison_2023_2024.csv.
-- This query annualises with the arithmetic mean of the monthly returns times 12, while the
-- published Sharpe ratios compound the returns (src/risk.py), so the two are expected to differ
-- a little. It is a check on direction and rough size, not on the third decimal.
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
