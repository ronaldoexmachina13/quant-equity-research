# LIMITATIONS_PLAN.md: pre-registration of work on the README limitations

Registered: 2026-10-23, before any of the work below is run.
Scope: addresses the limitations listed in README.md (flat risk-free rate, simple cost model, no statistical significance, coarse robustness, small universe, short sample).
Rule: this file is committed before any code is written. Existing entries are never edited. Changes are appended as dated amendments.

## General principles
- Everything in Phase 1 is a labelled sensitivity or diagnostic. It does not change the strategies and does not replace any published number. Original results stay in place and the new results are shown beside them.
- No parameter of the strategies (lookbacks, top 5, equal weights, monthly rebalance, 10 bps) is changed in Phase 1.
- All variants that are run are reported, whatever the result.
- New outputs go to new files. No existing file in `results/` is modified.

## Phase 0: consistency check (read only)
Compare every statistic quoted in README.md and the HTML pages (Sharpe, alpha, t-statistics, total returns) with the corresponding CSV in `results/`. List mismatches. Known item to check: the README states the largest alpha t-statistic as 0.94, while a pre-correction status note recorded 1.13. Output: a short list of discrepancies, with no edits.

## Phase 1: risk-free rate, cost sensitivity, power analysis

### 1A. Period-specific risk-free rate
- Question: how much do the Sharpe ratios, Sortino ratios and alphas change when the flat 2% is replaced by the actual 3-month Treasury bill rate?
- Hypothesis: levels move materially (roughly +1% to +3% of annual excess return depending on the period) but the ranking of strategies and benchmark within each period is mostly unchanged, since all series are charged the same rate.
- Data: FRED series TB3MS (3-month Treasury bill secondary market rate, monthly, percent per annum), downloaded from FRED. Save the raw series to `results/tbill_3m_monthly.csv`. Use the value for each month as the risk-free rate applied to that month, converted to a monthly rate as (1 + y/100)^(1/12) - 1. State this convention in the script.
- Method: recompute Sharpe, Sortino and the alpha regression (excess returns on benchmark excess returns, statsmodels OLS) for Momentum, Value, Combined and Benchmark over: in-sample 2021-2024, 2021-2022, 2023-2024, and out-of-sample Jan 2025 to Aug 2026. Show the flat-2% value and the T-bill value side by side.
- Output: `results/rf_sensitivity.csv` (period, strategy, metric, flat_2pct, tbill).
- Reading rules, fixed now: (a) if the benchmark still has the highest out-of-sample Sharpe under T-bill rates, the main conclusion is unchanged; (b) any change in the ranking of strategies within a period is reported explicitly in the README, not omitted; (c) no alpha is called significant unless |t| > 1.96, as before.

### 1B. Transaction-cost sensitivity
- Question: at what cost level does each strategy's Sharpe fall to the benchmark's, and how much does the benchmark's own rebalancing cost matter?
- Method: re-run the existing backtest logic with one-way costs of 0, 5, 10, 25 and 50 bps, in-sample and out-of-sample separately. Apply the same cost rate to the benchmark, using its own monthly turnover from rebalancing to equal weights. Report the break-even cost for each strategy (cost at which its Sharpe equals the benchmark's, or "none within 0 to 50 bps").
- Output: `results/cost_sensitivity.csv`.
- The 10 bps case must reproduce the existing `transaction_cost_impact.csv` figures for the strategies. If it does not, stop and report why.
- Reading rule: costs are a sensitivity. The headline 10 bps assumption does not change.

### 1C. Statistical power analysis
- Question: how large would a strategy's annualised alpha or Sharpe gap need to be to be detectable with the data available, and how long a sample would be needed for the observed effects?
- Method: using the monthly active return series (strategy minus benchmark) and its standard deviation, compute (i) the minimum detectable annualised active return at 5% two-sided significance and 80% power for n = 48, 68 and about 170 months, using MDE = (z_0.975 + z_0.80) * sd / sqrt(n), and (ii) the number of months needed to detect the observed mean active return at the same significance and power. Label clearly that the standard deviation is estimated from the same sample and the figures are illustrative.
- Output: `results/power_analysis.csv`.
- Purpose: to explain, not to rescue, the finding that nothing is significant. The conclusion that no result is statistically significant stays unchanged.

### Phase 1 deliverables
New scripts at the repository root following the existing naming style, new functions in `src/risk.py` where reusable, unit tests with hand-made inputs, and the three new CSVs. No README or HTML edits by Claude Code. Ronaldo commits.

## Phase 2: full robustness grid (outline, to be pre-registered in detail before running)
- Grid: portfolio size (top 3, 5, 8, 10), rebalance frequency (monthly, quarterly), momentum lookback (6-1, 9-1, 12-1), cost (5, 10, 25 bps). Every cell is reported, as a table and a heat map. No selection of a preferred cell.
- Additional diagnostics: rolling 24-month Sharpe, drawdown chart, VaR and Expected Shortfall, hit rate.

## Phase 3: data feasibility check for Version 0.6 (outline)
- Uses no returns and no strategy results, so it cannot bias the design.
- Questions: (1) how many historical S&P 500 members from 2012 can be reconstructed from the public constituent change history; (2) how many have price history available in yfinance; (3) how many have usable SEC book value, and how coverage varies by sector and year.
- Output: a coverage report only. Its result decides whether top quintile or top decile is realistic.

## Phase 4: Version 0.6 (outline, own pre-registration required)
- Point-in-time S&P 500 universe from about 2012 to 2026; frozen v0.5 signal definitions with no tuning; new portfolio size (top quintile or decile) fixed before any run.
- Evidence design: 2012-2020 is the new test (never examined by this specification). 2021-2026 on the larger universe is reported as a re-test, not as out-of-sample, because the period is already known.
- Signal-level tests: rank information coefficient, quintile spread, Fama-MacBeth regression.
- Coverage reporting per date, and a disclosed count of members without prices. Survivorship bias is reduced, not eliminated.
- Expectation recorded in advance: value (P/B) may look weak over 2012-2020. If so, it is reported as found.

## Amendment 1 (2026-10-23, before any Phase 1 code was written or run)

Reason: Phase 0 found that the original text of this plan used a 1.96 threshold "as before", while the project has always used the 90% level (|t| above 1.65; see the significant_at_90pct column, README.md and test_significance.py). The wording was an error in the plan, not a change of method. No Phase 1 result existed when this amendment was written.

Changes:
1. Rule 1A(c) is replaced by: an alpha is called significant at the project's usual 90% level if |t| > 1.65. The script also prints whether any |t| exceeds 1.96, marked as information only.
2. In 1C, significance is set at 10% two-sided (z = 1.645) with 80% power, consistent with the rest of the project. The same figures at 5% two-sided (z = 1.96) are reported alongside, marked as information only.

Clarifications of 1A (implementation choices, no change to the question or the data):
3. Sharpe ratio with a time-varying rate: (strategy annualised return minus the compounded annualised T-bill return over the same months) divided by the annualised volatility of the strategy's own returns. The annualisation convention must be the same as the existing functions in src/risk.py. With a flat 2% series this reproduces the existing formula exactly, which is the reproduction check. Sortino and the alpha regression follow the same approach, with month t's rate as the target and as the deduction.
4. Benchmark rows report Sharpe and Sortino only. Alpha against itself is zero by construction.
5. One extra row per period, with strategy "Risk-free", reports the annualised rate: 0.02 in the flat column and the actual T-bill rate in the T-bill column.
6. The script is named run_rf_sensitivity.py.
7. The TB3MS monthly average is applied to the same month's return, as registered. It does not affect which stocks are held, so it is not look-ahead.

## Amendment 2 (2026-10-23, before any Phase 1B code was written or run)

Reason: while planning 1B, it was found that calculate_turnover() counts only changes in target weights. It does not count the trades that rebalance held names back to equal weight after prices drift. The benchmark's only trades are such drift trades. Charging the benchmark for drift but not the strategies would be asymmetric and would flatter the strategies. No Phase 1B result existed when this amendment was written.

Changes and clarifications to 1B:
1. Two turnover bases for the strategies. (a) Existing basis: calculate_turnover(). It must reproduce transaction_cost_impact.csv and oos_summary.csv, or the script stops. (b) Drift-inclusive basis, labelled as such, which also counts the trades that rebalance held names after drift. The benchmark is always charged on drift-based turnover (rebalancing to equal weights each month).
2. Drift definition: the pre-trade weight at month t is the month t-1 target weight drifted by month t-1 returns and renormalised. Turnover is 0.5 times the sum of absolute differences between the month t target and the pre-trade weights. NaN returns are treated as 0. The first month is a purchase from cash. Only month t-1 returns are used, so there is no look-ahead.
3. Break-even cost: the one-way cost between 0 and 50 bps at which the strategy's Sharpe equals the benchmark's, with both net of the same cost, on the flat 2% basis. If there is no crossing, the result is recorded as "below benchmark at 0 bps" or "above benchmark at 50 bps".
4. Periods: full in-sample (2021-2024) and out of sample (Jan 2025 to Aug 2026). In sample, the first month is a purchase from cash. Out of sample, January 2025 is a rebalance from the December 2024 holdings, as in the existing scripts.
5. Output: results/cost_sensitivity.csv in long format, one row per period, strategy, turnover basis and cost level, with the benchmark Sharpe, the Sharpe difference, the break-even cost and a note.
6. Reading rules, fixed now: (a) the headline 10 bps assumption on the existing basis is unchanged; (b) both bases are reported, and neither is chosen after seeing the results; (c) the drift-inclusive basis is the like-for-like comparison with the benchmark, and the existing basis is reported because it reproduces the published numbers; (d) expectation recorded in advance: drift-inclusive turnover is higher for the strategies, so their break-even costs will be lower than on the existing basis; where a strategy is already below the benchmark at 0 bps, no break-even exists and this is reported as such.

## Amendment 3 (2026-10-23, before any Phase 1C code was written or run)

Reason: the original 1C text does not say which periods supply the standard deviation, which test the power figures refer to, or how the hypothetical sample length is labelled. These are recorded now. No Phase 1C result existed when this amendment was written.

Clarifications to 1C:
1. Periods: the monthly active return series (strategy minus equal-weight benchmark, flat 2% basis) is taken for three periods: in sample 2021-2024 (n = 48), out of sample Jan 2025 to Aug 2026 (n = 20), and the two combined (n = 68). The standard deviation is estimated separately for each period.
2. Test: the figures refer to a test of the mean monthly active return against zero. They are not the beta-adjusted alpha regression, whose t-statistics are reported elsewhere. This is stated in every output row.
3. Annualisation: the annualised figure is 12 times the monthly figure, the same arithmetic convention as the alpha regression.
4. n = 170 months is a hypothetical sample length (about the length of a 2012 to 2026 study) and is labelled as hypothetical in the output. It is not a result.
5. Months needed: the figure answers "how long a sample would be needed if the true mean active return equalled the observed one". The observed mean is itself noisy, so this is illustrative and is labelled as such. A zero or negative observed mean is reported as such and never as a failure.
6. Power uses the standard two-sided approximation (z_alpha + z_power) and ignores the far tail.
7. Reading rules, fixed now: (a) the conclusion that no result is statistically significant stays unchanged whatever the power figures show; (b) the figures are used only to explain why the tests have little power and how large an effect would be needed, not to re-interpret any observed result; (c) if the minimum detectable effect for n = 68 exceeds the largest observed annualised active return, this is stated in the README as the reason no result is significant.

## Phase 2 detailed design: robustness grid (2026-10-23, before any Phase 2 code was written or run)

This entry replaces the grid description in the Phase 2 outline above. Differences from the outline: the cost dimension is dropped, because Phase 1B already covers costs from 0 to 50 bps; the extra diagnostics (rolling Sharpe, drawdown chart, VaR and Expected Shortfall, hit rate) are separated into a later descriptive step, Phase 2B, which tests no hypothesis and will be specified when we reach it.

### Question and hypothesis
- Question: does the conclusion "no active strategy beats the benchmark on a risk-adjusted basis by a margin distinguishable from chance" survive reasonable changes to portfolio size, rebalancing frequency and the momentum lookback?
- Hypothesis recorded in advance: the conclusion is robust, meaning the sign of each strategy's Sharpe difference against the benchmark does not depend on one particular specification. This could fail, and a failure is reported as found.

### Grid (every cell is run and reported)
- Strategies: Momentum, Value, Combined.
- Portfolio size (equal-weighted top N): 3, 5, 8, 10 stocks out of 17.
- Rebalancing: monthly (the existing method, which resets equal weights among the selected names each month) and quarterly (selection refreshed every third month, in January, April, July and October, with holdings carried between refreshes and drifting with prices). The quarterly schedule starts in January 2021 and continues unbroken into the out-of-sample window. Only this one quarterly phase is run. Phase sensitivity (refreshing in February or March instead) is a stated limitation, not tested.
- Momentum lookback: 6-1, 9-1 and 12-1 months (skip month fixed at 1). Applies to Momentum and Combined only. Combined uses the same lookback in its momentum component. Value has no lookback.
- Cells: Momentum 24, Value 8, Combined 24, which is 56 per period.
- Base specification (the published headline, unchanged): top 5, monthly, 12-1. It is flagged in the output and no other cell replaces it.

### Periods
- In sample: Jan 2021 to Dec 2024 (48 months), the same window for every cell regardless of lookback.
- Out of sample: Jan 2025 to Aug 2026 (20 months), computed for the same cells as a stability check and reported separately. This is a second look at data already seen, and it is labelled as such. The pre-registered out-of-sample test remains the single official test and its published figures stand.
- No cell in either period is used to choose, change or promote a specification.

### Benchmark and costs
- The benchmark in each cell is equal weight across all 17 stocks, rebalanced at the same frequency as that cell (monthly or quarterly, drifting in between), so that differences reflect stock selection and not rebalancing. The official monthly benchmark stays the headline.
- Flat 2% risk-free rate, as in the published results.
- Net figures use 10 bps one-way on the drift-inclusive turnover basis for strategies and benchmark alike (Amendment 2), so both are charged the same way. Gross figures are reported too.

### Outputs (new files only; existing files are never overwritten)
- `results/robustness_grid.csv`: one row per period, strategy and cell, with the settings, an is_base_case flag, gross and net Sharpe for strategy and like-for-like benchmark, the differences, average turnover, annualised return, volatility and maximum drawdown.
- `results/robustness_grid_summary.csv`: one row per period and strategy, with the number of cells, the share of cells with a positive net Sharpe difference, the median, minimum and maximum difference, the base-case difference, and the share of cells whose sign differs from the base case.

### Reproduction gates (the script stops without writing if any fails)
- The base cell, monthly, top 5, 12-1 for Momentum and Combined, must reproduce the published gross Sharpe ratios for strategies and benchmark in `strategy_comparison_full_period.csv` and `oos_summary.csv`.
- The monthly top 8 cell at 12-1 must reproduce `strategy_comparison_concentration.csv`.
- Unit tests with hand-made inputs must cover the quarterly schedule, the drift of held positions between refreshes, and turnover that is zero in non-refresh months.

### Reading rules, fixed now
1. The headline specification is not replaced by any cell.
2. No per-cell significance test is run. With 112 cells across the two periods, some cells would show a positive difference by chance alone, so individual cells are not read. The figures that are read are the share of cells with a positive difference, the median difference and the share of sign flips.
3. A strategy's result is called stable in a period if the sign of its net Sharpe difference matches the base case in at least 75% of its cells, and fragile otherwise. It is called consistent across periods if the in-sample and out-of-sample median differences have the same sign.
4. Every cell is reported, including unfavourable ones, in the CSV and in a table in the README.
5. Expectations recorded in advance: as the portfolio size approaches 17, the difference against the benchmark moves towards zero, because the portfolio approaches the benchmark; quarterly rebalancing lowers turnover and so helps net Sharpe for Momentum and Combined more than for Value.
6. Neither the grid nor any other analysis in this plan will be used to search for a better specification. If a later change to the strategies is wanted, it needs its own pre-registration.

## Amendment 5 (2026-10-23, before any Phase 2 code was written or run)

Reason: the Phase 2 implementation plan was reviewed against the design above, and four points were settled. No Phase 2 result existed when this amendment was written.

1. Extra reproduction gates, in addition to those registered: the base cell's net Sharpe at 10 bps on the drift-inclusive basis must match the corresponding rows of results/cost_sensitivity.csv, for the strategies and the monthly benchmark, to 1e-9; and the grid must contain exactly 56 cells per period, over 48 and 20 months.
2. Definitions: share_sign_differs_from_base is computed over all of a strategy's cells in the period, including the base cell, which always matches itself. A cell with a net Sharpe difference of exactly zero is counted as not positive. If the base-case difference is exactly zero, stability is reported as undefined.
3. Eligible universe: Value and Combined can only select among names with a valid book value (14 to 16 of the 17 names each month, because V has no usable book value and HD and DIS have gaps), while the benchmark holds all 17. Expectation 5 of the Phase 2 design (the difference moves towards zero as the portfolio size approaches 17) therefore applies to Momentum, and need not hold for Value and Combined, whose top 10 never approaches the whole benchmark. This is a feature of the published design and is not changed.
4. The summary file robustness_grid_summary.csv gains two descriptive columns, eligible_names_min and eligible_names_max, giving the smallest and largest number of names with a valid score in any month of the period for that strategy. They are computed from the data, not typed in.

Note (2026-10-23): the Phase 2 detailed design above is the fourth dated entry in this file, and there is no Amendment 4. The label Amendment 5 is kept as written, to avoid editing registered text.

## Phase 3 detailed design: data feasibility check for a larger universe (2026-10-23, before any Phase 3 code was written or run)

This entry replaces the Phase 3 outline above. It is registered now so that the design is fixed in advance, and it has not been run. Phase 4 (a point-in-time universe study) remains a documented future step with its own pre-registration.

### Question
Can a point-in-time S&P 500 universe from 2012 be rebuilt from free public data well enough to support a signal-level study, and how much of it would be missing?

### Hard constraint
Phase 3 computes no returns, no signal values and no strategy performance. Prices are used only to count whether the data needed exists. This means that nothing in Phase 3 can bias a later design.

### Sources
- Membership: the public Wikipedia page "List of S&P 500 companies" (current constituents, with GICS sector) and its table of changes to the list (additions and removals with dates). The current list is walked backwards through the changes to rebuild membership by date. No other source is used to fill gaps.
- Prices: yfinance, downloaded from 2011-01-01 to 2026-09-01 (end exclusive) to allow a 12-month warm-up before 2012.
- Fundamentals: SEC EDGAR company facts, through the existing functions in src/fundamentals.py (get_book_value_per_share and forward_fill_book_value with the 6-month cap). The book-value rule is reused, not re-implemented.
- Ticker to CIK: the SEC ticker file, as the existing code does. Names that cannot be mapped are counted, not dropped silently.

### Isolation from the published results
Phase 3 writes to a separate database file (database/universe_feasibility.db, gitignored) and a gitignored cache folder for raw downloads. It does not write to the tables prices or book_value in database/quant_research.db, and it does not modify any existing results file.

### SQL
The membership is stored as a table index_membership (ticker, start_date, end_date) in the separate database. "Members at date t" is one SQL query, stored in sql/universe_at_date.sql, and the monthly coverage counts are produced by joining that query with the availability tables. This is the genuine use of SQL in this phase.

### Definitions, fixed now
- Evaluation months: January 2012 to August 2026 (176 months).
- Universe in month t: members at the end of month t-1, so a stock added during month t is not in month t's universe.
- Signal inputs available (momentum): month-end adjusted prices exist for t-1 and t-12.
- Book value available (value): a book value per share from a filing dated on or before the end of t-1 and not older than 6 months (the existing forward-fill rule), and a price for t-1.
- Usable for Value and Combined: member, signal inputs available and book value available. Usable for Momentum: member and signal inputs available.
- Return observable: a month-end price also exists for t. This is NOT required for usability, because requiring it would drop stocks that were delisted or acquired during month t and would build survivorship bias into the universe. It is measured separately, as the delisting gap: the number of usable names whose month-t return cannot be observed.
- A download that fails with an error is retried (at most three times) and is never counted as missing data. Only a confirmed empty result is counted as missing. Persistent errors are listed separately.
- Prices are matched to a membership window only inside that window, and tickers whose price history starts after their membership start, or has a gap inside it, are flagged. This guards against ticker reuse and ticker changes.

### Outputs (new files only; existing files are never overwritten)
- results/universe_membership.csv: ticker, company, current GICS sector (current members only, otherwise blank), start_date, end_date, source row.
- results/universe_coverage_monthly.csv: for each month, the number of members, with signal inputs, with a CIK, with book value, usable for Momentum, usable for Value and Combined, and the delisting gap.
- results/universe_coverage_by_year.csv: the same, averaged by year, split into members that stayed in the index to the end and members that were removed at some point. This split is the survivorship diagnostic.
- results/universe_coverage_by_sector.csv: coverage by current GICS sector, for current members, with removed names in an "unknown" row.
- results/universe_exclusions.csv: an audit list of every name that is excluded or partly covered, with its membership dates and the reason (no CIK, no prices, partial prices, no book value, persistent download error).

### Validation gates (the script stops and reports instead of writing a conclusion if one fails)
1. The reconstructed membership must contain the 17 stocks of the published study as members for the whole of their documented membership in the evaluation window.
2. For those 17 stocks, over the months that overlap with the existing database, the availability of prices and of book value computed by the new stage must match the existing prices and book_value tables month by month. V must show no book value, as in the published study.
3. The reconstructed number of members must be between 480 and 520 in every month. A month outside this range is flagged as unreliable and excluded from the thresholds below.

### Decision rules, fixed now
1. Portfolio size: a decile portfolio is feasible in a month if at least 200 names are usable for Value and Combined, and a quintile portfolio if at least 100 are. Fewer than 100 means the universe is too thin for that month.
2. Study window: the earliest month from which the applicable threshold holds in every later month. The result is reported as a start date, not chosen by hand.
3. Survivorship flag: a calendar year is flagged as impaired if more than 20% of member-months in that year have no usable price data, or if the share usable among removed members is more than 15 percentage points below the share among members that stayed.
4. Delisting gap: any year in which usable names with no month-t return exceed 1% of usable names is flagged, and a delisting-return treatment would be needed before any later returns study.
5. If thresholds 1 and 2 are met for at least 10 years, a larger-universe study is recommended as a possible future step. If not, the report says the data does not support one and lists what would be needed. Either outcome is reported as found.

### Deliverables
New scripts at the repository root, resumable and cached, in the existing naming style; unit tests with hand-made inputs for the membership reconstruction (a short invented list of changes whose result is checked by hand) and for the usability rules; and the five output files above. No README, HTML or LIMITATIONS_PLAN.md edits by Claude Code. Ronaldo commits.

## Phase 2B detailed design: risk diagnostics (2026-10-23, before any Phase 2B code was written or run)

This entry specifies the descriptive step mentioned in the Phase 2 design. Rolling Sharpe is dropped from it, because the Portfolio Timeline page already shows rolling 12-month Sharpe and volatility.

### Purpose
Descriptive tail-risk and consistency measures from the project roadmap (Value at Risk, Expected Shortfall, hit rate) and a drawdown chart. No hypothesis is tested. Nothing in this step changes a strategy or a published result.

### Definitions, fixed now
- Returns: the published monthly gross returns of Momentum, Value, Combined and the monthly-rebalanced equal-weight Benchmark, in the base specification (top 5, monthly, 12-1 where applicable). These are the same series the earlier scripts use.
- Periods: in sample (48 months) and the full 68 months for Value at Risk and Expected Shortfall. For the hit rates, worst and best month and the drawdown series, out of sample (20 months) is reported as well. Value at Risk and Expected Shortfall are not reported for 20 months alone, because 20 observations leave a single observation in the 5% tail.
- Historical Value at Risk at 95%: the monthly return at the 5th percentile of the period's returns (numpy percentile with linear interpolation), reported as a positive loss. A figure of 6.0% means that in 5% of months the return was -6.0% or worse.
- Expected Shortfall at 95%: the average loss over the months whose return is at or below that 5th percentile value, reported as a positive loss.
- Intervals: 90% bootstrap intervals for Value at Risk and Expected Shortfall (5,000 resamples with replacement, seed 42), as in the existing bootstrap code.
- Hit rate, two versions: the share of months with a positive return, and the share of months in which a strategy's return exceeded the benchmark's (strategies only).
- Also reported: worst month, best month and the number of months.
- Drawdown series: the underwater curve (cumulative value divided by its running maximum, minus 1), month by month, for each strategy and the benchmark. In sample starts at 1.0 in January 2021, and out of sample starts at 1.0 at the end of December 2024, consistent with the existing out-of-sample growth chart.

### Outputs (new files only; existing files are never overwritten)
- results/risk_diagnostics.csv: one row per period and strategy, with the measures above.
- results/drawdown_series.csv: one row per period, month and strategy.

### Reproduction gates (the script stops without writing if any fails)
1. The returns must reproduce the published Sharpe ratios at the flat 2% rate for the strategies and the benchmark, in sample and out of sample, and the saved out-of-sample monthly returns, to 1e-9.
2. The maximum drawdown computed from the new drawdown series must match the published maximum drawdown for every strategy and the benchmark, in sample and out of sample, to 1e-9.
3. Unit tests with hand-made inputs must cover Value at Risk and Expected Shortfall on a short list whose percentile and tail average can be checked by hand, both hit rates, and the drawdown of a hand-made path.

### Reading rules, fixed now
1. The measures are descriptive. No test between strategies is run.
2. With 48 and 68 monthly observations the 5% tail rests on about two or three months, so the intervals are expected to be wide. Expectation recorded in advance: the 90% intervals of the strategies and the benchmark overlap for both Value at Risk and Expected Shortfall, so no strategy is described as having lower or higher tail risk than another on this evidence.
3. Hit rates are read against 50%. The difference from 50% is not tested.
4. The drawdown chart shows what happened. The published maximum drawdown figures are unchanged.
5. After the results exist, a panel is added to the Sensitivity tab of the dashboard through the generator, with no hand-typed figures.

## Amendment 6 (2026-10-28, before any Phase 3 code was written or run)

The Phase 3 implementation plan showed several points of the registered design to be open to more than one reading. This amendment fixes the reading before any code runs. No threshold, gate limit or decision rule of the Phase 3 entry is changed.

1. Month-end price. "A month-end price exists" for calendar month m means a price on the last trading day of m. The trading calendar is taken from the downloaded data: the last date in the month on which at least half of the downloaded tickers have a price. The same rule applies to t-1, t-12 and t. Reason: under the alternative reading (any price in the month) a stock delisted early in month t would look observable, and the delisting gap would be understated. Gate 2 checks that the rule gives the same result as the existing tables for the 17 study stocks.
2. Book value. The existing forward_fill_book_value is used unchanged. Its cap is 180 days, which is how "6 months" is read in this phase.
3. Membership rebuild. An addition dated d gives start_date = d. A removal dated d gives end_date = d minus one day. A current member with no recorded addition gets a NULL start_date (before the recorded history). A name added again gets a second interval. Inconsistent rows (removing a ticker that is not present, adding one already present) are counted and printed, never repaired. Universe in month t is the set of members on the calendar end of month t-1.
4. Gate 1. For each of the 17 study stocks, membership must cover the universe of every month t from 2021-01 (the first in-sample month) to 2026-08, with no gap. Each interval is printed for review. Gates 1 and 2 stop the run and no file is written to results/. Gate 3 is as registered: a month outside 480 to 520 members is flagged unreliable (reliable = 0 in the monthly file) and the run continues. The by-year file uses reliable months only and reports the number of unreliable months.
5. Errors and missing data. A download is confirmed empty only if yfinance returns YFPricesMissingError or YFTzMissingError on two separate attempts, or the SEC returns HTTP 404. Rate limits, network errors and other codes are retried up to three times with backoff and, if they persist, are listed as errors and never counted as missing. SEC requests are limited to 8 per second.
6. Survivorship split. A ticker counts as removed if any of its membership intervals ends before 2026-08-31, including names that were later added again. Everything else counts as stayed. The by-year file also reports the share of member-months with no price at t-1 and the share with no signal inputs. The delisting gap is reported separately for names usable for Momentum and names usable for Value and Combined. The exclusions file adds the reason "partial book value" to the registered reasons.
7. Reuse of src/fundamentals.py. get_company_facts is replaced at run time by a cached version with the same signature, and the ticker to CIK map is cached. get_book_value_per_share and forward_fill_book_value run unchanged. The four module-level lines at the end of src/fundamentals.py (an import and a debug call that contacts the SEC on every import) are deleted. No function behaviour changes, and the change is committed on its own.
8. Cache location. The cache folder is set by the environment variable UNIVERSE_CACHE_DIR and defaults to data_cache/ inside the repository (gitignored). Because the repository sits inside OneDrive, the run uses a folder outside OneDrive. The database path database/universe_feasibility.db is as registered.
