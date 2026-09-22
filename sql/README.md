# SQL — analytical queries

## Status

- **Tier A (done, works today):** `factor_construction_in_sql.sql` computes
  momentum and Price-to-Book directly from the real `prices`/`book_value`
  tables. Runs against the database as it exists right now.
- **Tier B (needs one code change first):** `portfolio_and_regime_queries.sql`
  computes turnover, regime-split Sharpe/drawdown, and momentum/value holdings
  overlap. This requires `src/database.py` to be patched — see
  `../src_patch/database_py_additions.md` — and `run_strategy_comparison.py`
  re-run once after that, so `portfolio_weights` and `performance` actually
  exist as tables. **Do the patch first.** Running this file against the
  unpatched database will fail with "no such table," correctly.

## Why two tiers, not one file

The database originally stored only raw inputs (`prices`, `book_value`); all
derived output (signals, weights, performance) lived only in `results/*.csv`,
computed in pandas. That's a legitimate design for a solo project, but it
meant SQL wasn't doing analytical work, only caching. Tier A proves SQL can do
real signal-construction work on the data that was already there. Tier B
extends the database itself, following the existing `save_prices`/
`save_book_value` idempotent pattern, so the turnover/regime/overlap queries
are backed by real tables instead of describing ones that don't exist.

## Files

- `create_tables.sql` — full schema reference: the two original tables,
  verified against `src/database.py`, plus the two Tier B tables (present in
  this file now; only present in the live database after the patch is applied).
- `factor_construction_in_sql.sql` — 12-1 momentum, P/B, and a coverage
  diagnostic. Run this and diff its output against `src/factors.py`'s results
  — if they disagree, that's worth finding now, not in an interview.
- `portfolio_and_regime_queries.sql` — turnover by strategy, regime-split
  Sharpe and max drawdown, and momentum/value holdings overlap by month.
  Requires Tier B.

## Known scope limit

No `companies`/sector table exists, so no sector-concentration query is
included. Adding one would need a small new ingestion step (ticker → sector
mapping, probably a static CSV given the universe is fixed at 17 names) — a
reasonable "what's next" item, not something worth faking with a query against
data that isn't in the database.

## How to use this credibly in an interview

Be able to explain *why* Tier B exists as a separate step, not just that it
does: it's the difference between "I used SQLite" and "I made a real call
about what belongs in the database versus what stays in pandas, and I can
tell you why." That's a stronger answer than either extreme (everything in
SQL, or nothing in SQL) would be.
