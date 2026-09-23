# Out-of-sample test plan (pre-registered)

**Written:** 23 September 2026, before any price or filing data after 31 December 2024 was downloaded into this project. The Git commit that adds this file is the timestamp.

## Purpose

Every result in this repository so far comes from 2021–2024, the period in which the strategies were built and examined. This test asks whether the findings hold on data the strategies have never seen. The rules below are fixed now and will not be changed after the new results are seen.

## Test period

- **Out-of-sample period:** January 2025 to August 2026 (the last complete month at the time of writing), about 20 monthly returns.
- **In-sample period:** January 2021 to December 2024. The existing in-sample results will be kept exactly as they are and reported separately; they will not be merged with or replaced by the new period.

## Strategy rules (frozen)

Identical to the code at the commit that adds this file:

- **Universe:** the same 17 tickers in `config.py`. No additions or removals, even where coverage is thin (V remains excluded from Value and Combined for lack of usable book value data).
- **Momentum:** 12-month return skipping the most recent month (12-1), measured at each month-end.
- **Value:** Price-to-Book using book value per share from SEC EDGAR, aligned to filing dates, forward-filled for at most 6 months; lowest P/B ranks highest.
- **Combined:** cross-sectional z-scores of momentum and value, averaged with equal weight.
- **Portfolio:** top 5 stocks by score, equal weight (20% each), rebalanced monthly.
- **Benchmark:** all 17 stocks in equal weight, rebalanced monthly.
- **Risk-free rate:** flat 2% a year, as in the in-sample results.
- **Transaction costs:** 10 bps one-way on actual turnover.

The only code changes allowed are those needed to extend the date range, fetch the new data and report the new period separately. Any data-quality fix required for 2025–2026 filings will be documented in the README with its reason.

## What will be reported

For each strategy and the benchmark over the out-of-sample period: total and annualized return, volatility, Sharpe, Sortino, maximum drawdown, beta and alpha, the alpha t-statistic and p-value, and the paired-bootstrap Sharpe difference against the benchmark (90% confidence interval).

## How the results will be read

- **The main in-sample conclusion holds** if the benchmark's Sharpe ratio is again at least as high as each active strategy's.
- **The Combined regime finding** (strong 2023–2024 result, alpha +5.1%) is supported only if Combined's out-of-sample alpha is positive; it is contradicted if the alpha is zero or negative.
- **The Value finding** (full-period alpha +1.4%, concentrated in a few names) is supported only if Value's out-of-sample alpha is positive.
- With about 20 months of data, no result is expected to be statistically significant. The test checks direction and consistency, not significance, and will be reported that way.

## Commitments

1. The strategy rules above will not be changed in response to the out-of-sample results.
2. The out-of-sample results will be published whether they support, contradict or fail to resolve the in-sample findings.
3. The out-of-sample period will be shown separately in the README and on the dashboard, labelled as out of sample.