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

## Amendment 7 (2026-10-28, before any Phase 3 result existed)

The first run of run_universe_membership.py stopped when it parsed the cached Wikipedia page, before any table was written to the database and before any gate preview had been printed. The cause is that Wikipedia no longer carries the table of changes on the page "List of S&P 500 companies". It now sits on the page "Historical components of the S&P 500". The table has the same id (changes), the same columns (Effective Date, Added with Ticker and Security, Removed with Ticker and Security, Reason, Refs) and the same date format as before. At the time of writing it lists 348 changes dated 2011 or later.

Both pages are Wikipedia, so the registered source is unchanged in kind. This amendment changes where the second table is read from. Current constituents and their GICS sector still come from "List of S&P 500 companies". The table of changes comes from "Historical components of the S&P 500". Both pages are cached on first retrieval and the cached files are what the code reads. The cached copy of the second page was saved on 2026-10-28 with Invoke-WebRequest and the same User-Agent as the rest of the project. No other part of the Phase 3 design, Amendment 6 or the decision rules is changed.

## Phase 4 detailed design: signal and portfolio tests on the rebuilt S&P 500 universe (2026-10-31, before any Phase 4 code was written or run)

This entry replaces the Phase 4 outline above. It uses the coverage measured in Phase 3, which found at least 300 names usable for Value and Combined in every month from January 2012 to August 2026, and found every calendar year impaired by survivorship. This design is therefore built around what free data can and cannot support.

### Question and hypothesis
- Question: do the three signals of the published study (Momentum 12-1, Value as negative P/B, and Combined), with their definitions unchanged, show a measurable relationship with next-month returns across roughly 300 to 500 large US stocks over 2012 to 2026, and do portfolios built from them differ from an equal-weight benchmark of the same stocks?
- The signal-level tests are the primary evidence. The portfolio tests are secondary, because a portfolio result depends on more assumptions than a signal result does.
- Hypothesis recorded in advance: Momentum shows a small positive information coefficient. Value, as measured by P/B, may show a weak or negative one over 2012 to 2020, a period in which cheap-on-book stocks lagged. Combined lies between the two. Any of these could fail, and a failure is reported as found.

### Hard constraints
- Free data only. No paid source is used in this phase.
- Survivorship bias is reduced and not removed. Companies that were acquired or went bankrupt mostly have no price history on Yahoo Finance (Phase 3: the share of members with usable data is 26% for removed names against 85% for names that stayed in 2012). The universe in every month therefore consists of the names that have data. This is stated on every output.
- The direction of the bias is not known in advance. Portfolios and benchmark are both drawn from the same surviving names, so their difference is less affected than their levels. Absolute returns and Sharpe levels are not read as evidence of performance.
- No signal definition, lookback, weighting, rebalancing rule or cost assumption of the published study is changed. Any change needs its own pre-registration.

### Universe and data
- Evaluation months: January 2012 to August 2026 (176 months), the window found in Phase 3.
- Universe in month t: members at the end of month t-1, using the membership rebuilt in Phase 3, restricted to names usable under the Phase 3 definitions (month-end price and signal inputs at t-1 and t-12; for Value and Combined also a book value that meets the existing 6-month forward-fill rule).
- A month is used for a signal only if at least 100 names are usable for it (Phase 3 rule 1). Every month met this.
- Return of a stock in month t: the change in adjusted close from the end of t-1 to the end of t, with the same convention as the published study. A name with no price at the end of month t has no return and is dropped from that month's returns. The number of such names is reported every month, and no delisting return is imputed.
- Risk-free rate: the actual monthly 3-month Treasury bill series already saved in results/tbill_3m_monthly.csv (it covers the whole period), used for all Sharpe ratios. A flat 2% is reported next to it for comparison with the published study, because a flat 2% would be wrong for 2012 to 2015, when bill rates were close to zero.
- Names flagged in Phase 3 as having a price history that starts after their membership start are used only from the first month with a price. Ticker reuse that cannot be detected this way is a stated limitation.

### Signals (frozen)
- Momentum: price at t-1 divided by price at t-12, minus 1, from src/factors.py (calculate_momentum, 12 and 1).
- Value: negative price-to-book at the end of t-1, from src/factors.py (calculate_value_score, with the published one-month lag).
- Combined: the average of the cross-sectional z-scores of the two, from src/factors.py (calculate_combined_score). A name missing either signal has no Combined score in that month.
- No sector adjustment. P/B differs systematically between sectors (asset-light technology against banks, for example), which is a limitation and is not corrected here.
- The existing functions are reused, not re-implemented.

### Periods
- New test: January 2012 to December 2020 (108 months). This specification has never been run on these months, since the published study starts in 2021.
- Re-test: January 2021 to August 2026 (68 months) on the larger universe. These months are already known from the published study, so this is reported as a re-test and not as out-of-sample evidence.
- The full period is shown for reference. No result from any period is used to choose or change a specification.

### Signal-level tests (primary evidence)
For each signal and each period, computed from the monthly cross-section of usable names:
1. Rank information coefficient (IC): the Spearman rank correlation between the signal at t-1 and the return in month t. Reported as the mean monthly IC, its 90% bootstrap interval (5,000 resamples, the same method as the rest of the project), the share of months with a positive IC and the number of months.
2. Quintile spread: the equal-weight return of the top fifth of names by signal minus that of the bottom fifth, each month. Reported as the mean monthly spread, annualised, with a 90% bootstrap interval.
3. Fama-MacBeth regressions: each month, the cross-sectional return on the standardised signal; the slopes are averaged over the period with a 90% bootstrap interval. Run for each signal alone, and for Momentum and Value together.

### Portfolio tests (secondary)
- Top decile (headline, because Phase 3 shows at least 200 usable names in every month) and top quintile, equal weight, monthly rebalancing, for Momentum, Value and Combined. Both sizes are always run and reported.
- Benchmark: equal weight across all usable names in the same month, rebalanced monthly. SPY is shown as a reference only.
- Costs: 10 bps one-way on turnover, as in the published study. Gross and net figures are both reported.
- Metrics: total return, annualised return and volatility, Sharpe ratio (Treasury bill and flat 2%), maximum drawdown, average monthly turnover, and the Sharpe difference against the benchmark with a 90% paired bootstrap interval.
- Survivorship diagnostic (descriptive): the average equal-weight monthly return of names that were later removed from the index against names that stayed, by period. It shows how much the missing names could matter. It is not a correction.

### Outputs (new files only; existing files are never overwritten)
- results/universe_study_monthly_counts.csv: per month, the universe size, the number usable for each signal, and the number of names with no return in the month.
- results/universe_study_ic_monthly.csv and results/universe_study_spread_monthly.csv: the monthly series behind the signal tests.
- results/universe_study_signal_summary.csv: IC, quintile spread and Fama-MacBeth results by signal and period.
- results/universe_study_portfolio_returns.csv: monthly gross and net returns by strategy, portfolio size and benchmark.
- results/universe_study_portfolio_summary.csv: portfolio metrics by period.
- results/universe_study_survivorship.csv: the removed against stayed comparison.

### Reproduction gates (the scripts stop without writing if any fails)
1. Restricted to the 17 study stocks and January 2021 to December 2024, the new pipeline's Momentum, Value and Combined top-5 monthly portfolios must reproduce the published gross Sharpe ratios in results/strategy_comparison_full_period.csv.
2. For the 17 stocks, the month-end prices used must equal the existing prices table.
3. Hand-checked unit tests must cover the rank IC, the quintile assignment (including ties and months with fewer names), the quintile spread, the Fama-MacBeth slope, and the treatment of names with no return in month t.

### Reading rules, fixed now
1. A signal is said to show evidence of a relationship in a period if the 90% interval of its mean IC excludes zero. A signal is said to be consistent if the sign of its mean IC is the same in the new test and in the re-test. There are three signals and two periods, so six primary tests. No correction for multiple testing is applied, all six are reported, and none is read alone.
2. Because of survivorship, a positive result is described as consistent with the signal having a relationship with returns among surviving large caps, and never as alpha, outperformance or evidence that a strategy works. A negative or null result is reported as found.
3. The portfolio Sharpe differences are read only alongside the signal tests, and are not significant unless the 90% paired bootstrap interval excludes zero.
4. Expectations recorded in advance, not targets: Value may be weak or negative over 2012 to 2020; Momentum and Combined have higher turnover than Value, so costs reduce their net results more; the Sharpe difference against the benchmark is small for the decile and quintile portfolios because both are diversified.
5. The published 17-stock results, the pre-registered out-of-sample test and every earlier figure stand unchanged. Nothing in this phase replaces them.
6. This phase will not be used to search for a better specification. If one is wanted, it needs a separate pre-registration, and a rank-based Combined, a sector-neutral Value or other variants will be labelled exploratory.

### Deliverables
New code in src/ (signal evaluation functions with unit tests using hand-made inputs) and new scripts at the repository root in the existing naming style, resumable where they download, plus the output files above. No README, HTML or LIMITATIONS_PLAN.md edits by Claude Code. Ronaldo commits. The dashboard is rebuilt around these results only after they exist.

## Amendment 8 (2026-10-31, before any Phase 4 result existed and before the split check was written or run)

Checks made while planning the Phase 4 code showed that the price-to-book ratio used by Value divides Yahoo's adjusted close, which is rewritten backwards for every later stock split and dividend, by book value per share as filed, which stays on the share count in force when it was filed. For a stock that splits after the filing, P/B is too low by the split ratio, so the stock looks cheap in the months before the split. This is a defect in how the frozen definition (negative P/B) was implemented and not a change of definition, in the same way as the timing correction recorded in OUT_OF_SAMPLE_PLAN.md, Amendment 1. Phase 3 is not affected, because it only counted whether data existed. Momentum is not affected, because it uses price ratios only.

### What the planning checks found (no return and no strategy result was computed)
- Splits and similar events since 2019 among the 17 study stocks, from yfinance: AAPL 4-for-1 on 2020-08-31, NEE 4-for-1 on 2020-10-27, RTX 1.589 on 2020-04-03 (a merger and spin-off effect, not an ordinary split), WMT 3-for-1 on 2024-02-26.
- Effect on the published study: WMT shows a P/B about three times too low from January 2021 to March 2024, and was held by Value in 39 of the 48 in-sample months. NEE is affected in January and February 2021 only. AAPL and RTX are not affected, because the first filing after each event came after the 180-day limit or after the event.
- The published Value and Combined results may therefore be affected. This has not been measured at the time of this amendment.
- Using adjusted close also lowers older prices by later dividends, which shifts P/B for every dividend payer, including in the out-of-sample months. This is a second, smaller source of the same inconsistency.
- HD's book value per share moves by up to 5.5 times in a month without any split, because its book equity is small. The fix below does not address this, and HD remains a known distortion for Value.

### Split sensitivity on the 17 study stocks (a labelled sensitivity)
- New script run_value_split_check.py and new tested functions in src/split_adjust.py. Split dates are downloaded once from yfinance and cached. No existing file or function is changed.
- Restatement rule: each filed book value record is divided by the product of all splits dated after its filing date (not after its period end), and the existing 180-day forward fill is then applied unchanged. Price and book value are then on the same share basis, so the split ratio cancels and no information from after the date is used. Events reported by yfinance are applied mechanically and listed, including the RTX event.
- Three versions of Value and Combined are reported side by side, in sample and out of sample, using the same top 5, monthly rebalancing, 10 bps costs and flat 2% rate as the published study: (1) published, as computed now; (2) restated book value with the adjusted close, which isolates the effect of splits; (3) restated book value with the split-adjusted close that is not adjusted for dividends, which also removes the dividend effect. All three are reported whatever the result.
- Outputs, all new files: results/value_split_summary.csv, value_split_monthly_returns.csv, value_split_holdings.csv (both sets of top 5 each month, with a changed flag), value_split_pb.csv and value_split_events.csv.
- The script stops without writing if: the published series rebuilt from the database differs from results/strategy_comparison_full_period.csv or results/oos_summary.csv by more than 1e-9; as-filed book value from the cached SEC facts, forward filled, differs from the book_value table by more than 1e-6 for any of the 17; or any stock without an event has a restated book value different from the as-filed one.
- Scope: the published figures and the pre-registered out-of-sample test stand unchanged. Whether the published figures are corrected is decided after the result is seen and is recorded in its own dated entry before any rerun of the published pipeline.

### Consequences for Phase 4
1. Value and Combined in Phase 4 use the split-consistent definition (version 3 above) for every stock in the universe. Phase 4 never reports a Value or Combined result computed with the unrestated definition as evidence.
2. Before Phase 4 uses the filing-date rule on the wider universe, it is checked on every stock with a split in the universe. A restated book value series that still moves by more than a factor of 2 in a month, with or without a split, is listed in an output file and reported. Such names are not excluded and no threshold is tuned.
3. Reproduction gate 1 of the Phase 4 entry is run with the published (unrestated) definition on the 17 stocks, because it tests that the pipeline reproduces the published code. Its result is not reported as evidence.

### Tolerances (these were not fixed in the Phase 4 entry)
- Gate 2: for each of the 17 stocks, the ratio of the cached price to the existing prices table is constant within 1e-5 across the overlapping months, and all level differences are printed. A constant level difference is expected from dividend adjustment between downloads.
- Gate 1: each gross Sharpe ratio is within 1e-4 of the published figure.

### Readings of points the Phase 4 entry left open
1. Timing: a score row dated t already uses data only through the end of t-1, and is paired with the return dated t. No extra lag is added.
2. Month-end prices are prices on the last trading day of the month only.
3. Combined: Momentum is restricted to names usable for Momentum and Value to names usable for Value before calculate_combined_score is called, as in the published treatment.
4. Quintiles and deciles: names are assigned using all usable names at t-1, before any return is looked at, by average rank and the rule ceil(rank x q / N), so tied names share a group. Deciles use q = 10.
5. A held name with no return in month t is dropped, and the month's portfolio return is the mean of the remaining holdings. Turnover uses the target weights.
6. Benchmark: because the usable sets differ, there are two equal-weight benchmarks. Momentum is compared with its own usable universe, Value and Combined with theirs.
7. Costs: every net figure is reported on both turnover bases of Amendment 2.
8. Periods: one continuous run from January 2012, sliced afterwards. January 2021 is a rebalance and not a purchase from cash.
9. The annualised spread is the mean monthly spread times 12, as in Amendment 3. Intervals use 5,000 resamples and seed 42.
10. Fama-MacBeth: signals are standardised across all usable names at t-1, then an ordinary least squares regression with an intercept is run on the names that have a return. The two-signal version uses names with both signals, standardised over that joint set. Raw P/B is not winsorised, because the definition is frozen.
11. Every output file carries a universe_note column stating that the universe consists of names with available data and is affected by survivorship.
- Additions: SPY for 2012 to 2020 is downloaded once to a separate reference folder and checked against the saved 2021 to 2026 series. A new function bootstrap_sharpe_diff_tbill is added to src/risk.py for paired Sharpe differences with a Treasury bill rate, resampling the same months for strategy, benchmark and bill rate. No existing function changes.

## Amendment 9 (2026-10-31, before any Phase 4 result existed and before any restated Value result had been seen)

Gate 2 of the split check registered in Amendment 8 failed, and the script stopped without writing any result file. This amendment records the finding and fixes the rules that follow from it.

### Finding
- Rebuilding book value per share from the cached SEC facts, with the existing functions in src/fundamentals.py, does not reproduce the stored book_value table for 5 of the 17 study stocks over the 80 overlapping months: RTX (60 months differ, largest difference 6.0%), KO (26 months, 9.2%), LIN (14 months, 4.5%), LMT (9 months, 0.9%) and JNJ (3 months, 2.0%). Every month has a value on both sides, so coverage matches and only the values differ. WMT and NEE, the two stocks that the split restatement changes in the sample, pass.
- The likely cause, found by read-only diagnostics and partly unproven, is two tie situations in the existing code that are resolved by row order. First, forward_fill_book_value sorts on filing date only, so two periods filed on the same date are not ordered. Taking the newest period reproduces JNJ's stored values exactly. Second, get_stockholders_equity keeps one of two equity series, standard stockholders' equity or equity including noncontrolling interest, when both are filed on the same date with different values, and the sort does not settle which. Neither fixed rule reproduces the stored table for the stocks with equity-tag ties, which suggests the stored table reflects an arbitrary row order. Why the order differs between the original download and the cached facts (a newer SEC file or the library version) was not established.
- Consequence: the published Value and Combined results depend on an arbitrary choice in the stored book values, in addition to the split problem of Amendment 8. The published figures stand and remain reproducible from the stored database table, which is the input of record, but they cannot be rebuilt from the cached SEC facts. This will be disclosed as a limitation.

### Split check (replaces the base book value of Amendment 8, nothing else changes)
- The base for all three versions is the stored book_value table, not a rebuild from cached records, so that the comparison isolates the effect of the split restatement and of the Close price.
- For each month, the filing in force is identified from the cached records with the existing forward-fill rule (the latest filing date on or before the month end, within 180 days). The stored value of that month is divided by the product of all splits dated after that filing date.
- Gate 2 of Amendment 8 is replaced by: for each stock with an event that changes at least one month of the sample, the as-filed value of the filing in force, taken from the cached records, equals the stored table value within 1e-6 for the months it applies to. Mismatches for the other stocks are printed and reported, and do not stop the run. Gate 3 is unchanged: a stock with no event has a restated value equal to its stored value.
- The three versions, the output files, the Gate 1 tolerance and the statement of scope are as in Amendment 8.

### Book value rule for Phase 4 (fixed before Stage 2)
1. When two filings have the same filing date, the one with the newest period end is used.
2. Standard stockholders' equity is used. Equity including noncontrolling interest is used only when the standard series is absent for that filing. Reason: market capitalisation values the claim of the parent's common shareholders, so the per-share book value should exclude the minority interest.
3. The rule is implemented as a new function used only by the universe study and tested with hand-made inputs. The existing functions in src/fundamentals.py are not changed.
4. The same rule is used for every stock in the Phase 4 universe, together with the split restatement of Amendment 8.

### Reproduction gate 1 of the Phase 4 entry, as amended
- Gate 1a: with the stored book_value table as input, the Phase 4 pipeline's Momentum, Value and Combined top-5 portfolios for the 17 stocks reproduce the published gross Sharpe ratios within 1e-4. This tests the code path. Momentum and the benchmark do not depend on book value and must reproduce in any case.
- Gate 1b (report only, no threshold): the book value per share from the fixed rule above against the stored table for the 17 stocks, by stock and month, and the number of months in which the Value top-5 holdings differ. This shows how much the published Value result depends on the arbitrary choice.
- A failure of Gate 1a stops the run. Gate 1b cannot fail.

## Amendment 10 (2026-10-31, before any Phase 4 result existed and before the book value, share count or split code was built)

A read-only check made while planning Stage 2 looked at the presence of book values under the Amendment 9 rule. It computed no signal, no return and no strategy result. This amendment records what it found and fixes the rules that follow.

### Finding
- Under the Amendment 9 rule, the number of name-months usable for Value and Combined differs from the Phase 3 coverage file: 65,383 in Phase 3, 204 lost and 614 gained under the rule, in 164 of 176 months, with a largest monthly change of -4 and +10 names. The lowest month stays at 300 (January 2012). Two causes: taking standard equity can change a record's filing date and so move it in or out of the 180-day window, and it can leave negative equity, which the existing code drops, where the previous mix kept a positive figure that included noncontrolling interest (139 records across 29 names). Momentum counts are not affected.
- Share counts have the same kind of tie. The existing get_shares_outstanding chooses between two tags that can carry the same date and filing date with different values: 87 names have such ties, 20 with a gap above 10%, and the largest gap is about 1,000 times, which looks like a units error in a filing. Without a rule, book value per share would still depend on row order.

### Decisions
1. Usable set for Value and Combined: defined by the Amendment 9 rule. The Phase 3 coverage results stand as measured, because they were computed with the rule registered at the time. The usable counts for Momentum must match results/universe_coverage_monthly.csv exactly. For Value and Combined, a reconciliation is printed by name and must close exactly in every month: the Phase 3 count, minus the names lost, plus the names gained, equals the count used. The thresholds of 200 and 100 are re-checked for the Value universe under the new rule and the result is reported.
2. Share count rule, used with the Amendment 9 rule for every stock in Phase 4: the balance sheet figure (CommonStockSharesOutstanding) is preferred, and the cover page figure is used only where the balance sheet figure is absent. When two records have the same filing date, the one with the newest period end is used. Cases where the two tags differ by more than a factor of 100 in the same filing are listed as suspected units errors. src/fundamentals.py is not changed. The rule is a new tested function.
3. Split cut-off: the cached closing prices were written on 2026-10-28 and carry split adjustments up to that date. Only splits dated on or before 2026-10-28 are applied to book value. Later splits are ignored and listed, because they would divide book value without a matching price adjustment.
4. Jump report: every restated book value per share series that moves by more than a factor of 2 in a month, and every suspected units error, is written to a new file, results/universe_study_bv_jumps.csv, and added to the output list of the Phase 4 entry. It is printed in Stage 2 and written in Stage 3.
5. Sensitivity: the Value and Combined signal and portfolio tests are also run excluding the names listed in the jump report. This is a labelled sensitivity. The headline results exclude nothing, and no threshold is tuned.
6. If Gate 1a fails because of the level differences between the cached and stored prices (JPM, PG and CAT differ by a constant factor from dividend adjustment between downloads), the run stops and reports. Any change to the gate needs its own amendment.
7. Staging: the Momentum path does not depend on book values or splits, and Stage 3 may be run in two parts. Each part writes its own new files, named as in the Phase 4 entry with the suffix _momentum or _value_combined before the extension. No file is overwritten. The Momentum part may be run before the Value path is complete. The same rules, periods and reading rules apply to both parts.

## Amendment 11 (2026-10-31, before any Value or Combined signal test, and before any return was computed on the wider universe)

The Stage 2 checks of the Value path passed all registered gates and wrote no result file. They also showed that units errors in the SEC share counts reach the Value signal, and that the gates cannot catch this, because they test reproducibility and not plausibility. This amendment records the finding and fixes the rules that follow, before any signal test is run.

### Finding (no signal test and no return on the wider universe was computed)
- Gates: the split download completed for 630 of 630 tickers with no errors (297 events in 208 tickers, none after the cut-off). Gate 2 and Gate 1a passed for Momentum, Value and Combined, and the reconciliation closes exactly every month: 65,383 less 204 plus 615 equals 65,794 usable name-months. The gained count is 615 and not the 614 of Amendment 10, because the share count rule of Amendment 10 also applies. The number of names usable for Value and Combined is between 300 and 426 in every month.
- Gate 1b (report only): the fixed rule changes book value per share for nine of the 17 stocks relative to the stored table (largest differences NEE 18.7%, WMT 9.4%, KO 8.9%, RTX 6.0%, DIS 5.8%), yet the Value top-5 holdings differ in only 1 of 48 in-sample months and 1 of 20 later months.
- Units errors: 143 monthly moves in restated book value per share above a factor of 100, across 59 tickers, and 177 filings in 73 tickers whose two share count tags differ by more than a factor of 100. P/B runs from about 0.00001 to 1.9 million. All 150 name-months with P/B below 0.1 fall in the top Value decile, in 85 of the 108 months of the new test. The existing functions of src/fundamentals.py are slightly worse (154 such moves in 63 tickers), so the problem is not caused by the rules of Amendments 9 and 10.
- Effect by test: rank IC and quintile or decile assignment are affected little by an extreme value, but Combined and Fama-MacBeth standardise raw P/B, and one extreme value inflates that month's standard deviation and flattens every other name's Value score.
- The jump list of Amendment 10 covers 215 tickers, about 34% of the usable universe. Many of these are real moves caused by thin equity, so excluding all of them would change the universe more than it would remove the errors.
- Yahoo's adjusted Close adjusts for spin-offs as well as splits: 117 of the 281 checked events are not simple ratios. The restatement of Amendment 8 stays consistent with this. A side effect is that the first filing after a spin-off can still show the pre-spin balance sheet, which explains many of the 28 large steps (for example ABT and HPQ).
- The portfolio_weights table of the stored database holds more rows than the published portfolios (245 for Value and 246 for Combined, against 240 for Momentum). The published returns and the holdings in results/portfolio_timeline.json are not affected: the holdings in that file equal the rebuild from the database in every month for Value and Combined. Phase 4 does not read this table.

### Decisions
1. Mechanical validity rule: a filing whose two share count tags (balance sheet and cover page) differ by more than a factor of 100 has no book value for that filing. The name has no Value or Combined score until its next valid filing. No number is guessed or corrected. This is applied before the share count rule of Amendment 10.
2. After the rule is applied, the jump report and the range of P/B are recomputed and printed before any signal test, and the remaining cases are listed. No further rule is added without a new amendment, and no return is looked at when such a decision is taken.
3. Headline: Value and Combined are run as registered, with raw P/B. Because a single extreme value affects the z-scores, two labelled sensitivities are also run and reported: Combined, and the Value Fama-MacBeth, with P/B winsorised at the 1st and 99th cross-sectional percentiles of each month before standardising. These change no headline.
4. The sensitivity of Amendment 10 (item 5) is narrowed to the names that still move by more than a factor of 100 after decision 1. The longer jump list stays in the jump report and is not used to exclude names.
5. Spin-offs: the listed ratios, including non-integer ones, are applied mechanically, as in Amendment 8. Stale pre-spin balance sheets after a spin-off are reported in the jump report and disclosed, and are not corrected.
6. The stale rows in portfolio_weights are recorded as a known issue of the stored database. They will be cleaned up in a separate dated entry and do not affect any published figure.

## Amendment 12 (2026-11-01, before any Value or Combined signal test, and before any Value or Combined return was computed)

Amendment 11, decision 2, requires the jump report and the range of P/B to be recomputed after the validity rule, and any further rule to have its own amendment. This amendment records what that check found and adds one labelled test. No Value or Combined return was computed or looked at when this decision was taken.

### Finding (no Value or Combined signal test and no Value or Combined return was computed)
- After decision 1 of Amendment 11, the moves above a factor of 100 fall from 143 in 59 tickers to 40 in 24 tickers, and the name-months with P/B below 0.1 fall from 150 to 13 (SPG 6, FTI 4, CMG 3). All registered gates pass and the reconciliation closes exactly every month: 65,383 less 451 plus 614 equals 65,546 usable name-months.
- The list of 24 names of Amendment 11, decision 4, does not cover every remaining extreme value. SPG has the lowest remaining P/B (about 0.0002), from a filing that reports 8,000 shares in one tag only. It has no neighbouring record, so it shows no move, and it is not on the list.
- A read-only check of every valid book value record, as filed and before split restatement, compared each record with the median of the same ticker's valid records. 45 records in 33 tickers differ from that median by more than a factor of 100. Likely causes, from comparing equity and shares with their own medians: a share count in a filing with one share tag (26 records), equity (11), a share count in a filing with both tags (4), and neither input (4, which may be real moves or thin equity). Tickers with a single record cannot be tested in this way (9 tickers) and are not on the list. Among them, FOX and FOXA each have one record of about 8.6 billion dollars per share, filed on 2019-05-10, and neither has a name-month with P/B below 0.1.
- The two lists overlap in 20 names, so together they hold 37 names.

### Decisions
1. Headline: Value and Combined are run as registered, after the validity rule of Amendment 11, decision 1, with raw P/B and nothing excluded. This amendment changes no headline.
2. One further labelled test is added. The Value and Combined signal and portfolio tests are also run excluding the 37 names below in every month of their history. The names leave both the Momentum and the Value legs before Combined is standardised, and Combined is standardised over the names that remain. The periods and reading rules are those of the headline, and the test is reported whatever the result. The sensitivities of Amendment 11, decisions 3 and 4, remain as registered and are also reported.
3. The list is fixed here and is not recomputed or changed:
   - Moves above a factor of 100 after decision 1 (24): AA, AAP, AEP, ALK, AMCR, ANF, ATO, CCL, CHTR, CLF, CLX, CMG, CNX, COR, CRM, CSX, CTVA, FTI, GEN, LUV, PKG, SPGI, SW, WYNN.
   - A record more than a factor of 100 from the ticker's own median (33): AA, AAP, AEP, ALK, AMCR, AMD, ANF, ATO, CB, CCL, CHTR, CIEN, CMG, CNX, CRM, CSX, CTVA, ENPH, EOG, FTI, FTNT, GEN, IDXX, LUV, MAR, NCLH, PKG, SLE, SPG, SPGI, URI, WST, WYNN.
   - Names on the second list only (13): AMD, CB, CIEN, ENPH, EOG, FTNT, IDXX, MAR, NCLH, SLE, SPG, URI, WST. Names on the first list only (4): CLF, CLX, COR, SW.
4. The list uses each ticker's full history, so it could not have been known during the sample, and some of its moves fall outside the evaluation months. It also includes names whose extreme value may be real. The test therefore measures how much the results depend on these names. It is not an investable rule and does not replace any headline.

### Corrections to Amendment 11
Earlier entries stand as written. These corrections apply to the items named here.
1. The 177 suspected units errors are 177 tag pairs in 155 filings, across 73 tickers. Amendment 11 counted them as 177 filings.
2. The lowest P/B before the validity rule was about 0.0000015, not about 0.00001.
3. After the validity rule, the number of names usable for Value and Combined is between 295 and 426 in every month. The range of 300 to 426 in Amendment 11 was measured before the rule. No month is below the thresholds of 200 and 100.
4. The wording of Amendment 11, "before any return was computed on the wider universe", was inaccurate, because the Momentum signal tests had already been committed. The same applies to its finding heading, "no signal test and no return on the wider universe was computed". Both statements hold only for Value and Combined.

## Amendment 13 (2026-11-07, before any Stage 4 code was written or run and before any portfolio result existed)

The Stage 4 plan (portfolio tests of Phase 4) was reviewed against the Phase 4 entry and Amendments 8 to 12. Seven points were left open by the registered text. This amendment fixes them. No portfolio return, turnover or Sharpe difference had been computed when these decisions were taken. No registered rule changes.

### Decisions
1. Paired tests. The Sharpe difference against the benchmark is tested with a 90% paired bootstrap interval (5,000 resamples, seed 42, the same months drawn for strategy, benchmark and Treasury bill rate) on three bases: gross, net on the drift-inclusive turnover basis, and net on the existing turnover basis. The gross difference with the Treasury bill rate is the headline, as in the published study. The two net differences are secondary. In every net test the benchmark is charged on the drift-inclusive basis (Amendment 2). The flat 2% difference is reported with its interval from bootstrap_sharpe_diff, for comparison only. A difference is called significant only if the 90% interval excludes zero (reading rule 3 of the Phase 4 entry), and only the headline basis is read for that purpose.
2. Number of tests. The headline holds 18 intervals (3 strategies, 2 sizes, 3 periods) at the 90% level, so about two would exclude zero by chance alone if there were no effect at all. The printout and the README state this, and no interval is read on its own.
3. New function. bootstrap_sharpe_diff_tbill is a new function in src/risk.py (Amendment 8, Additions). Its test must show that, with a constant monthly rate equal to the one implied by sharpe_ratio and the same seed, it reproduces bootstrap_sharpe_diff, or, if the two Sharpe definitions differ by construction, the test states the difference and checks it against a hand calculation.
4. Output files. The three registered files hold the headline only. The sensitivities are written to separate new files with the suffixes _excl_24 and _excl_37 (for example results/universe_study_portfolio_summary_excl_24.csv), as in Stage 3. Value and Combined only (Amendment 12, decision 2). Momentum is not run under exclusions, but the Momentum leg of Combined loses the excluded names.
5. Benchmark under exclusions. In the _excl_24 and _excl_37 runs the benchmark is the equal-weight portfolio of the usable names that remain, so that strategy and benchmark share one universe. The headline benchmark is unchanged.
6. Winsorised P/B. Amendment 11, decision 3 names the Combined signal tests and the Value Fama-MacBeth, and no portfolio. No winsorised portfolio is run. For the Value portfolios, a check is printed that winsorising does not change which names fall in the top decile or top quintile.
7. SPY. The 2012 to 2020 series is downloaded once to a separate reference folder in the cache and read from there. Over January 2021 to August 2026 its monthly returns must match results/spy_reference_monthly_returns.csv within 1e-6 in every month, or the run stops. SPY is reference only: Sharpe (Treasury bill and flat 2%), return, volatility and maximum drawdown, gross, with no turnover, no costs and no paired test.
8. Survivorship diagnostic. It is reported for both usable sets (names usable for Momentum, and names usable for Value and Combined), with a column that names the set. It is descriptive and uses the removed and stayed definition of Amendment 6, item 6.
9. First month. January 2012 is a purchase from cash and is charged as such, for strategies and benchmarks alike (reading 8 of Amendment 8). Average turnover for the 2012 to 2020 period includes that month. The first month is listed in the printout.
10. A held name with no return in month t is dropped (reading 5 of Amendment 8). In the drift-inclusive turnover, such a name is treated as sold at its last available weight. This is tested with a hand-made case.

## Amendment 14 (2026-11-07, after every registered result existed, before any code for these additions was written or run)

A review of the finished study listed four additions. The registered results already exist, so these are exploratory and post-results. They change no headline, no registered rule and no published figure. The new files are written once and never overwritten. If an addition changes how a result should be read, it is reported as it is, in the same place as the headline, and the README and the Method page are updated to say so.

### Decisions
1. Quintile mean returns. For each signal in the headline set (Momentum, Value, Combined) and each of the three periods, the mean monthly return of each of the five groups is reported, with the mean annualised as the mean times 12 (Amendment 8, reading 9). A monotonicity figure is added: the Spearman correlation between the group number (1 to 5) and the five group means, from -1 to 1. It is descriptive and has no interval. Q5 minus Q1 computed from the new table must equal the registered quintile spread mean, or the run stops.
2. Inference robustness. The registered intervals treat the months as independent draws. Monthly IC and slope series can be autocorrelated, in which case those intervals are too narrow. For the 33 headline tests (Momentum: rank IC, quintile spread, single and joint Fama-MacBeth; Value: the same four; Combined: rank IC, quintile spread, single Fama-MacBeth; each in the three periods) two further 90% intervals for the mean are reported next to the registered one:
   - Newey-West: normal interval, mean plus or minus 1.645 standard errors, with a Bartlett kernel and floor(4 * (n / 100)^(2/9)) lags, where n is the number of months used (the rule of Newey and West, 1994). The long-run variance divides each autocovariance by n.
   - Circular block bootstrap: 5,000 resamples, seed 42, blocks of ceil(n^(1/3)) months, percentile interval.
   The lag and block rules are fixed here and are not tuned. The registered interval stays the headline. A test is called robust only if all three intervals exclude zero. If a registered interval excludes zero and either new interval does not, the README states this. The lag-1 autocorrelation of each series is printed to explain any widening. The extras script recomputes the registered mean and interval for every row and stops if any differs from the saved summary files by more than 1e-9.
3. Book value rule check. No rule changes. Tests are added to show that (a) in the fixed rule of src/book_value_rule.py a figure restated in a later filing never replaces the first-disclosed figure of its period, and (b) no record is usable before its filing date. The old combination in src/fundamentals.py (lines 111 and 133, keep="last") is used by the 17-stock first study only, not by the wider universe. A test documents what it does: where the two equity tags share a period end, it keeps the later-filed figure. Its filing date is that later date, so the figure becomes usable only from then. The effect is a delay and the loss of the first-disclosed figure, not look-ahead. src/fundamentals.py is not changed, and no published figure is changed.
4. Data manifest. A list of every file in the raw-data cache (relative path, size, SHA-256, modification time in UTC), written once to results/data_manifest.csv. The modification time is when the file was last written on that machine, which is used as the download date but is not proof of it. A verify mode recomputes the checksums and lists files that are changed, missing or new. The cache itself stays outside Git.
5. Count of tests. These additions add 33 Newey-West and 33 block-bootstrap intervals to the 18 headline intervals and the other tests already run. They are read as one family with the registered results, so a single extra interval that excludes zero is not read on its own.
6. Not included. A delisting-return sensitivity, a factor-model alpha and an IC decay profile are not part of this amendment. The README lists them as limits and as future work.

## Amendment 15 (2026-11-11, after every registered result existed, before any code for these additions was written or run)

An audit of the finished study found two problems of description, not of computation. Neither changes a registered rule, a headline or a published figure. Everything added here is exploratory and post-results.

### Findings

1. **The Momentum signal is not 12-1.** calculate_momentum() returns, in the row dated t, the price at the end of t-1 divided by the price at the end of t-12, minus 1. That row is paired with the return of month t, which runs from the close of t-1 to the close of t. The signal therefore ends on the trade date and no month is skipped: it is an 11-month return that includes the most recent month, whose return tends to reverse. The registered formula (Phase 4 design, "price at t-1 divided by price at t-12, minus 1") was implemented as written. The description "12-1, excluding the most recent month" in the README, the Method page, the home page, the signal profile text, docs/STUDY_17_STOCKS.md and the robustness grid labels (6-1, 9-1, 12-1) is wrong. The test test_calculate_momentum_skips_most_recent_month shows that the row dated t does not use the price at t. That is the one-month lag required to avoid look-ahead, not a skipped month.
2. **The survivorship wording overreaches.** The README and the dashboard say that survivorship inflates levels and that differences are the informative part. Missing names are mostly acquired or bankrupt, and they are missing from the portfolio and from its benchmark alike, so a difference is also biased, in a direction that depends on the signal. Coverage for Value and Combined is 61% of the index in 2012, 78% in 2021, and 85% even for names that stayed.

### Disclosure of a prior look

Before this amendment was written, a read-only audit check (not saved, not committed) computed the rank IC of a true 12-1 signal on the same cache. It gave a full-period mean IC of about +0.005, against about +0.011 for the registered signal on the same names, with a correlation of 0.97 between the two monthly series, and an IC of about -0.024 for the last month's return alone in 2012 to 2020. The outcome of the sensitivity below is therefore partly known. The amendment does not claim to have registered that outcome. It registers the definition, the tests and the reading rule before the committed script runs.

### Decisions

1. **No headline changes.** The registered Momentum and Combined signals, their results and their reading stay as published. From now on they are described as "11-month momentum: the return from the close 12 months before the trade date to the close of the previous month, with no month skipped".
2. **True 12-1 sensitivity (new function, existing code untouched).** A new function in src/factors.py, calculate_momentum_skip_month(prices, lookback_months=12, skip_months=1), returns in the row dated t the price at the end of t-2 divided by the price at the end of t-13, minus 1. It is a new function. calculate_momentum() is not changed. A hand-worked test must fail if the signal uses the price at t-1 or the price at t.
3. **Scope of the sensitivity.** Momentum and Combined (with the true 12-1 leg and the registered Value leg), over the same three periods, with the same tests as the headline: rank IC, quintile spread, single Fama-MacBeth, and for Momentum the joint Fama-MacBeth with Value; and the top-decile and top-quintile portfolios against the same benchmarks, gross and net on both turnover bases. The usable set is the registered Momentum set intersected with names that have a price at t-13. The first evaluation month, 2012-01, has no t-13 price in the calendar and is not used. The number of months and names used is printed for each period.
4. **Reversal diagnostic.** The rank IC and quintile spread of the last month's return alone (price at t-1 over price at t-2, minus 1) are reported for the same periods, descriptive, with the registered 90% interval.
5. **Intervals and seed.** The same 5,000 resamples, seed 42, 90% bootstrap intervals, and the Newey-West and block-bootstrap intervals of Amendment 14.
6. **Reading rule.** These results are read as one family with the registered results and the Amendment 14 additions. A single interval that excludes zero is not read on its own. If any sensitivity interval excludes zero while the registered one does not, the README and the Method page say so next to the headline. Nothing replaces the registered Momentum or Combined result.
7. **Survivorship, descriptive table.** From the existing monthly files and the existing coverage file, with no new data, a table by calendar year: the share of the index usable for each signal, the mean monthly rank IC, and the top-decile Sharpe difference against the benchmark with its interval. It is descriptive and adds no test. Written to a new file.
8. **Wording corrections.** The text listed in claude/wording_fixes_2026-11-11.md replaces the wrong descriptions. docs/STUDY_17_STOCKS.md is kept as published and gets a dated note at the top that its Momentum is the 11-month signal; its figures do not change. A line is added to the README data integrity log.
9. **Outputs.** New files only, written with mode x, named results/universe_study_*_momentum_skip_month.csv and results/universe_study_survivorship_by_year.csv. The script stops if any exists.

### What this does not do

It does not change the pre-registered design, does not tune a lookback, and does not decide which Momentum definition is better. A delisting-return scenario, a block bootstrap for the portfolio Sharpe differences, an arithmetic Sharpe column and a factor-model alpha are separate additions, to be registered in their own amendment.

## Amendment 16 (2026-11-12, after every registered result existed, before any code for these additions was written or run)

A review of the finished study raised concentration, benchmark-risk and validation questions. Everything added here is exploratory and post hoc. No registered rule, headline or published figure changes.

### Disclosure of a prior look

Before this amendment was written, a read-only check of the saved holdings file (not committed) showed that the top Value decile held about 53% Financials against about 12% of the universe, and that top-decile Value volatility was about 25% against about 15% for the benchmark. These observations motivate items 1 and 2.

### Decisions

1. **Sector-neutral Value and Combined.** Each month the Value z-score is computed within sector, then Combined is rebuilt from the registered Momentum leg and the sector-neutral Value leg. Same periods, same tests, same 5,000 resamples, seed 42, 90% intervals, Newey-West and block intervals as Amendments 14 and 15.
2. **Benchmark regression.** For each headline portfolio, monthly excess return is regressed on the benchmark's excess return. Alpha and beta are reported with Newey-West 90% intervals (lags by the rule in Amendment 14). The same is run for the sector-neutral portfolios.
3. **Earnings yield.** Used only if net income or EPS with a disclosure date is already in the stored fundamentals. If not, this is reported as not feasible and no data is added.
4. **Reference factor check.** The Kenneth French monthly Mom (UMD) and HML factors are used, taken from the data library (CRSP database of 202609) and stored unchanged for 2011-01 to 2026-09 in data/external/french/ (ff3_monthly_201101_202609.csv: Mkt-RF, SMB, HML, RF; mom_monthly_201101_202609.csv: Mom; percent, months before 2011 not stored). The correlation of each with the long-short spread of Momentum and Value over the overlapping study months (2012-01 to 2026-08) is reported, descriptive only. French's factors use all US stocks and value-weighting, so a high correlation is not expected, and the sign and rough size are the check.
5. **Book value timing.** A descriptive count of how many stored book values were first disclosed after the date they are used, expected to be zero under the existing rule.
6. **Reading rule.** Results join the existing family of tests and are counted in the ledger. A single interval that excludes zero is not read on its own. No variant is dropped.
7. **Wording.** "Pre-registered" is replaced by "pre-specified and version-controlled" in README, dashboard and LinkedIn draft. The rule is unchanged, only the description.
8. **Outputs.** New files only, mode x, named results/universe_study_*_sector_neutral.csv and results/universe_study_alpha_regression.csv. Scripts stop if any exists.

### What this does not do

It does not tune a parameter, choose a better Value definition, or add power to the registered sample.
