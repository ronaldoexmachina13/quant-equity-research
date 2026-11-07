# Momentum and Value in S&P 500 Stocks

[![tests](https://github.com/ronaldoexmachina13/quant-equity-research/actions/workflows/tests.yml/badge.svg)](https://github.com/ronaldoexmachina13/quant-equity-research/actions/workflows/tests.yml)

A pre-registered cross-sectional test of 12-1 momentum, price-to-book value and their average on about 500 S&P 500 members, January 2012 to August 2026. [Live dashboard](https://ronaldoexmachina13.github.io/quant-equity-research/). The study is complete and no further development is planned.

## Abstract

None of the three signals shows a statistically detectable relationship with next-month returns in the primary tests: all six mean rank IC intervals include zero. Two of 18 portfolio Sharpe-difference intervals exclude zero, both Value in 2012 to 2020 and both the same overlapping bet, against about 1.8 expected under the null at the 90% level. The first test period has 108 months and a monthly IC standard deviation of up to about 0.23, so the minimum detectable mean IC is about 0.055. The evidence is consistent with no effect and with a small one. The data are free and survivor-biased, so relative comparisons are informative and return levels are not.

## Evidence

All intervals are 90% bootstrap intervals (5,000 resamples, seed 42). IC is the monthly Spearman rank correlation between a signal and the next month's return. Sharpe differences are paired, against an equal-weight benchmark of the names with usable data for that signal, using the three-month Treasury bill as the risk-free rate.

| Test | 2012 to 2020 | 2021 to 2026 | Reading |
|---|---:|---:|---|
| Momentum: mean rank IC | +0.007 (-0.029 to +0.042) | +0.009 (-0.032 to +0.047) | Includes zero in both periods |
| Value: mean rank IC | -0.017 (-0.043 to +0.010) | +0.020 (-0.018 to +0.057) | Includes zero in both periods |
| Combined: mean rank IC | -0.002 (-0.036 to +0.032) | +0.015 (-0.023 to +0.051) | Includes zero in both periods |
| Momentum: Sharpe difference, top decile | +0.28 (-0.12 to +0.63) | +0.06 (-0.50 to +0.54) | Includes zero in both periods |
| Value: Sharpe difference, top decile | **-0.44 (-0.73 to -0.15)** | +0.17 (-0.24 to +0.61) | **Excludes zero in 2012 to 2020 only** |
| Combined: Sharpe difference, top decile | +0.14 (-0.23 to +0.48) | +0.22 (-0.27 to +0.68) | Includes zero in both periods |

The 2021 to 2026 months were already known from an earlier 17-stock study, so they are a re-test and not out-of-sample evidence. Quintile spreads, Fama-MacBeth regressions and top-quintile portfolios are in `results/` and on the dashboard.

![Mean monthly rank IC by signal and period, with 90% bootstrap intervals. All six intervals include zero.](results/universe_study_ic_intervals.png)

### Value, 2012 to 2020

Two of the 18 headline portfolio comparisons exclude zero, both for Value in 2012 to 2020 (top decile and top quintile). The two portfolios overlap, so this is one finding measured twice. It is absent from the re-test and from the full period. The rank IC, quintile spread and Fama-MacBeth intervals for the same signal and period all include zero, although the Fama-MacBeth slope falls just below zero under three secondary sensitivities (winsorised P/B, and with the 24 or 37 suspect names excluded). Those tests share the same months and stocks and are not independent evidence. No explanation has been tested.

![Sharpe ratio difference against the equal-weight benchmark, by strategy, portfolio size and period, with 90% paired bootstrap intervals. Two intervals exclude zero, both Value in 2012 to 2020.](results/universe_study_sharpe_diff_intervals.png)

Portfolios hold the top decile or quintile of names by signal at equal weight, rebalanced monthly, with 10 bps one-way costs charged on drift-inclusive turnover. Costs do not change which intervals include zero. Excluding the 24 or 37 suspect names moves the Value and Combined point estimates slightly and leaves the same two intervals excluding zero.

## Hypotheses

Momentum is the trailing 12-month return excluding the most recent month, which avoids the one-month reversal effect. Candidate explanations in the literature are slow incorporation of news and investor under-reaction. Value is the negative price-to-book ratio, which may compensate for distress risk or reflect over-pessimism. Neither premium is expected to be large among liquid, heavily analysed large caps, so a null result is a plausible outcome. Combined is the average of the two cross-sectional z-scores, with the 50/50 weighting fixed before testing.

## Data

| Item | Source and treatment |
|---|---|
| Universe | S&P 500 membership rebuilt month by month from Wikipedia. Between 353 and 499 names are usable for Momentum each month and between 295 and 426 for Value and Combined. |
| Prices | Yahoo Finance via `yfinance`, adjusted close. |
| Book value | SEC EDGAR filings, aligned to the filing date. Book value per share is restated for later splits. |
| Risk-free rate | Three-month Treasury bill, FRED. |

**Survivorship.** Acquired and bankrupt companies mostly have no free price history, so each month's universe is the set of names that have data. In 2012, for Value and Combined, 26% of names later removed from the index had usable data against 85% of names that stayed. Names later removed that did have data earned an annualised mean monthly return of about 3% to 4% over 2012 to 2026, against about 16% for names that stayed. This is descriptive and not a correction.

## Method

1. **Timing.** A signal dated t uses data up to the end of month t-1 and is paired with the return in month t.
2. **Primary evidence.** Rank IC, quintile spread and Fama-MacBeth slopes (single and joint), each with a bootstrap interval.
3. **Secondary evidence.** Top-decile and top-quintile portfolios, with a paired bootstrap interval for each Sharpe difference. A difference counts only if the 90% interval excludes zero, and portfolio results are read alongside the signal tests.
4. **No tuning.** Signal definitions were frozen from the earlier study. No lookback, weight or threshold was varied.

**Pre-registration.** The design, the reading rules and every later change are recorded as dated, append-only amendments in [`docs/LIMITATIONS_PLAN.md`](docs/LIMITATIONS_PLAN.md), committed before the code that depends on them. The earlier study's out-of-sample test follows [`docs/OUT_OF_SAMPLE_PLAN.md`](docs/OUT_OF_SAMPLE_PLAN.md).

**Power.** The monthly rank IC has a standard deviation of up to about 0.23. With 108 months the minimum detectable mean IC is about 0.055, above the 0.02 to 0.03 often cited for large-cap momentum. The test could not have found a small real effect, so an interval that includes zero does not show the effect is zero.

## Data integrity log

| When | Defect | Effect |
|---|---|---|
| Sep 2026 | Value used the month-end price instead of the previous month-end, a one-month look-ahead. | Raised the 17-stock Value Sharpe from 0.75 to 0.85, before the split fix below. The bug had penalised Value. |
| Sep 2026 | The first download missed 31 December 2024, because the `yfinance` end date is exclusive. | About 0.01 of Sharpe. |
| Oct 2026 | Price-to-book was too low for stocks that split their shares (Walmart 2024, NextEra 2020): Yahoo rewrites old prices after a split and SEC book value per share does not change. | 17-stock in-sample Value Sharpe fell from 0.86 to about 0.61, below the benchmark's 0.81. Alpha moved from +2.9% (t = 0.62) to about -0.9% (t = -0.17). Out-of-sample results are essentially unchanged. See `results/value_split_*.csv` and Amendment 8. |
| Oct 2026 | Some SEC filings report share counts under two tags that differ by more than 100 times (177 tag pairs in 155 filings), giving absurd price-to-book ratios. | Such filings carry no book value. Results were also run with winsorised P/B and with 24 and 37 names excluded. |

## Limitations

- **Survivorship.** A delisting-aware source such as CRSP is the real fix.
- **Free data.** Wikipedia membership is approximate early on (up to about 12 names overstated in 2012). Some book values rest on share counts that may carry unit errors the rule cannot detect. Ticker reuse is not fully detectable.
- **Universe.** Large, liquid S&P 500 names are the hardest place to find a factor premium.
- **Signals.** P/B is not sector-adjusted, Momentum is not volatility-scaled, and there is no quality factor.
- **Costs.** A flat 10 bps one way, with no market impact or capacity analysis.
- **Multiplicity.** 18 headline portfolio intervals at the 90% level, so about two would exclude zero by chance.
- **Inference.** No Fama-French controls and no Newey-West errors on the Fama-MacBeth slopes.

## Dashboard

Four static pages, built from the files in `results/`. Chart.js is loaded from a CDN; there is no server.

| Page | Question it answers |
|---|---|
| Overview | Do the signals rank stocks by next-month return? Rank IC with intervals, IC statistics and rolling stability, portfolio growth and drawdown against the benchmark, deepest drawdown episodes, monthly active-return heatmap, Sharpe differences, coverage and survivorship. |
| Strategy Analysis | Per signal: construction, rolling three-year excess return, all signal tests, sensitivity to the book-value treatment, and cost drag. |
| Stock Analysis | Which of the 861 tickers ever in the index have data, and which names contributed or detracted in the top-decile portfolios. |
| Portfolio Timeline | Month by month: holdings, returns, contributions and trades of each top-decile portfolio. |

## Reproducing

Python 3.13 and the pinned packages (`pip install -r requirements.txt`). Raw downloads are cached outside Git in the folder named by the environment variable `UNIVERSE_CACHE_DIR`. The SQLite file `database/universe_feasibility.db` is not committed. Result files are never overwritten: each script stops if its output exists, and the committed `results/` files already exist in a fresh clone. Run everything from the repository root, as modules.

```bash
python -m scripts.universe.run_universe_membership      # S&P 500 membership from Wikipedia (database only)
python -m scripts.universe.run_universe_prices          # price availability, Yahoo Finance
python -m scripts.universe.run_universe_fundamentals    # book value availability, SEC EDGAR
python -m scripts.universe.rebuild_feasibility_db       # finishes the database, checks it against committed files
python -m scripts.universe.run_universe_splits          # split history for book value restatement
python -m scripts.universe.run_universe_gates           # reproduction gates (prints checks, writes no result file)
python -m scripts.universe.run_universe_signals --momentum-only
python -m scripts.universe.run_universe_signals --value-combined
python -m scripts.universe.run_universe_spy             # SPY reference prices
python -m scripts.universe.run_universe_portfolios      # portfolio tests and sensitivities
python -m scripts.universe.make_universe_charts         # the charts and table on this page
python -m scripts.universe.run_universe_holdings        # holdings and per-stock summary, checked against committed returns
python -m scripts.universe.generate_universe_dashboard_data   # assets/universe_*_data.js (never overwrites)
python -m pytest tests/ -q                              # about 300 tests, no network needed
```

Rerunning a result-writing script in a fresh clone stops at the first existing file. To regenerate a result, write it to a new folder or move the old file first.

## Repository layout

```
index.html, universe-*.html   dashboard pages (GitHub Pages serves the repository root)
assets/                       dashboard.js, styles.css and the generated universe_*_data.js files
config.py                     17-stock universe and evaluation windows (earlier study)
src/                          library code: data loading, SQLite storage, factors, backtest, risk, universe
                              construction, book value rules, split adjustment, signal evaluation, portfolios
scripts/universe/             the large-universe pipeline, one script per stage (see Reproducing)
scripts/first_study/          the 17-stock study and its sensitivities
tests/                        unit tests checked against hand-worked cases, run on every push
sql/                          schema and analytical queries (see sql/README.md)
results/                      every generated CSV, JSON and chart (universe_* is the 500-stock study)
docs/                         pre-registration, out-of-sample plan, and the 17-stock write-up
database/                     SQLite files, generated and not committed
CLAUDE.md                     standing rules for the AI coding assistant used on this project
```

## Earlier study: 17 stocks

A fixed set of 17 large caps, tested in sample (2021 to 2024) and on 20 pre-registered months it had not seen (January 2025 to August 2026). The benchmark had the highest out-of-sample Sharpe ratio (1.89, against 1.72 for Combined, 1.53 for Value and 1.05 for Momentum) and no strategy could be statistically distinguished from it. Value's in-sample edge does not survive the split correction. The write-up is in [`docs/STUDY_17_STOCKS.md`](docs/STUDY_17_STOCKS.md).

## Extensions not undertaken

Sector-neutral Value, a quality factor, a Fama-French factor regression, Newey-West errors, and a delisting-aware data source.
