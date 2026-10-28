-- ============================================================================
-- universe_at_date.sql
-- Members of the reconstructed S&P 500 at the close of :as_of_date (ISO date),
-- from table index_membership in database/universe_feasibility.db.
--
-- start_date: effective date of the addition, NULL if the name was already a
--             member before the recorded change history.
-- end_date:   last day as a member (removal date minus one day), NULL for
--             current members.
--
-- Phase 3 evaluates month t on the members at the calendar end of month t-1,
-- so :as_of_date is that date (evaluation_months.universe_date).
-- ============================================================================
SELECT DISTINCT ticker
FROM index_membership
WHERE (start_date IS NULL OR start_date <= :as_of_date)
  AND (end_date IS NULL OR end_date >= :as_of_date)
