-- ============================================================================
-- universe_coverage.sql
-- Phase 3 coverage queries against database/universe_feasibility.db.
-- Each query is headed by a "-- name:" line and run by src/universe.py.
--
-- Availability tables hold presence only, never a price or book value:
--   price_month_end(ticker, month)       a price on the last trading day of month
--   book_value_month_end(ticker, month)  book value at the calendar month end under
--                                        the existing 180-day forward-fill rule
--   ticker_cik(ticker, cik)              cik NULL if the ticker cannot be mapped
-- Table temp.members is filled per month from sql/universe_at_date.sql.
-- ============================================================================

-- name: insert_member_month_flags
-- One row per member of month t's universe (members at the end of t-1).
INSERT INTO member_month_flags
    (month, ticker, has_price_t1, has_signal_inputs, has_cik, has_book_value, has_price_t)
SELECT
    :month,
    m.ticker,
    p1.ticker IS NOT NULL,
    p1.ticker IS NOT NULL AND p12.ticker IS NOT NULL,
    c.cik IS NOT NULL,
    p1.ticker IS NOT NULL AND b.ticker IS NOT NULL,
    pt.ticker IS NOT NULL
FROM temp.members AS m
LEFT JOIN price_month_end AS p1  ON p1.ticker = m.ticker  AND p1.month = :month_t1
LEFT JOIN price_month_end AS p12 ON p12.ticker = m.ticker AND p12.month = :month_t12
LEFT JOIN price_month_end AS pt  ON pt.ticker = m.ticker  AND pt.month = :month
LEFT JOIN book_value_month_end AS b ON b.ticker = m.ticker AND b.month = :month_t1
LEFT JOIN ticker_cik AS c ON c.ticker = m.ticker;

-- name: create_usability_view
-- Usability rules of the Phase 3 design, in one place.
-- Return observable (has_price_t) is not part of usability; a usable name
-- without it is counted in the delisting gap.
CREATE VIEW member_month_usability AS
SELECT
    month,
    ticker,
    has_price_t1,
    has_signal_inputs,
    has_cik,
    has_book_value,
    has_price_t,
    has_signal_inputs                                      AS usable_momentum,
    has_signal_inputs AND has_book_value                   AS usable_value_combined,
    has_signal_inputs AND NOT has_price_t                  AS delisting_gap_momentum,
    has_signal_inputs AND has_book_value AND NOT has_price_t AS delisting_gap_value_combined
FROM member_month_flags;

-- name: mark_reliable_months
-- Gate 3: a month is reliable if its member count is within the registered range.
UPDATE evaluation_months
SET reliable = (
    SELECT COUNT(*) BETWEEN :members_min AND :members_max
    FROM member_month_flags AS f
    WHERE f.month = evaluation_months.month
);

-- name: monthly_counts
SELECT
    e.month,
    e.universe_date,
    COUNT(u.ticker)                                  AS members,
    e.reliable,
    COALESCE(SUM(u.has_price_t1), 0)                 AS with_price_t1,
    COALESCE(SUM(u.has_signal_inputs), 0)            AS with_signal_inputs,
    COALESCE(SUM(u.has_cik), 0)                      AS with_cik,
    COALESCE(SUM(u.has_book_value), 0)               AS with_book_value,
    COALESCE(SUM(u.usable_momentum), 0)              AS usable_momentum,
    COALESCE(SUM(u.usable_value_combined), 0)        AS usable_value_combined,
    COALESCE(SUM(u.delisting_gap_momentum), 0)       AS delisting_gap_momentum,
    COALESCE(SUM(u.delisting_gap_value_combined), 0) AS delisting_gap_value_combined,
    COALESCE(SUM(1 - u.has_price_t1), 0)             AS members_no_price_t1,
    COALESCE(SUM(1 - u.has_signal_inputs), 0)        AS members_no_signal_inputs
FROM evaluation_months AS e
LEFT JOIN member_month_usability AS u ON u.month = e.month
GROUP BY e.month
ORDER BY e.month;

-- name: monthly_counts_by_group
-- Survivorship split: stayed vs removed (Amendment 6, item 6).
SELECT
    u.month,
    g.survivor_group,
    COUNT(*)                          AS members,
    SUM(u.has_price_t1)               AS with_price_t1,
    SUM(u.has_signal_inputs)          AS with_signal_inputs,
    SUM(u.has_cik)                    AS with_cik,
    SUM(u.has_book_value)             AS with_book_value,
    SUM(u.usable_momentum)            AS usable_momentum,
    SUM(u.usable_value_combined)      AS usable_value_combined,
    SUM(u.delisting_gap_momentum)     AS delisting_gap_momentum,
    SUM(u.delisting_gap_value_combined) AS delisting_gap_value_combined,
    SUM(1 - u.has_price_t1)           AS members_no_price_t1,
    SUM(1 - u.has_signal_inputs)      AS members_no_signal_inputs
FROM member_month_usability AS u
JOIN ticker_group AS g ON g.ticker = u.ticker
GROUP BY u.month, g.survivor_group
ORDER BY u.month, g.survivor_group;

-- name: counts_by_sector
-- Current GICS sector for current members, "unknown" for everyone else.
-- Reliable months only (gate 3).
SELECT
    g.sector_group                    AS sector,
    COUNT(DISTINCT u.ticker)          AS tickers,
    COUNT(*)                          AS member_months,
    SUM(u.has_price_t1)               AS with_price_t1,
    SUM(u.has_signal_inputs)          AS with_signal_inputs,
    SUM(u.has_cik)                    AS with_cik,
    SUM(u.has_book_value)             AS with_book_value,
    SUM(u.usable_momentum)            AS usable_momentum,
    SUM(u.usable_value_combined)      AS usable_value_combined,
    SUM(u.delisting_gap_momentum)     AS delisting_gap_momentum,
    SUM(u.delisting_gap_value_combined) AS delisting_gap_value_combined
FROM member_month_usability AS u
JOIN ticker_group AS g ON g.ticker = u.ticker
JOIN evaluation_months AS e ON e.month = u.month AND e.reliable = 1
GROUP BY g.sector_group
ORDER BY g.sector_group;
