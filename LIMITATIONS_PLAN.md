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
