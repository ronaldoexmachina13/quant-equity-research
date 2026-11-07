# Equity Factor Research: do momentum and value predict stock returns?

[![tests](https://github.com/ronaldoexmachina13/quant-equity-research/actions/workflows/tests.yml/badge.svg)](https://github.com/ronaldoexmachina13/quant-equity-research/actions/workflows/tests.yml)

### [**View the live dashboard (17-stock study)**](https://ronaldoexmachina13.github.io/quant-equity-research/)

*Do simple momentum and value signals predict next-month returns among large US stocks, and do portfolios built from them beat an equal-weight benchmark?*

> **Correction (7 November 2026): Value results in the first study are overstated.** After publication I found that the price-to-book ratio used by the Value signal was too low for stocks that split their shares (Walmart in 2024 and NextEra in 2020). Yahoo Finance rewrites old prices after a split, while SEC book value per share does not change. With splits handled, Value's in-sample (2021 to 2024) Sharpe ratio in the 17-stock study is about 0.61, not 0.86, below the benchmark's 0.81, and its alpha is about -0.9% a year (t = -0.17), not +2.9% (t = 0.62). The claims in the [full 17-stock write-up](docs/STUDY_17_STOCKS.md) and on the dashboard that Value had a slightly higher Sharpe ratio than the benchmark, or edged it in 2021 to 2022, are therefore not supported. Out-of-sample results are essentially unchanged, and nothing is statistically significant in either version. The corrected figures are in `results/value_split_*.csv` and the method is in `LIMITATIONS_PLAN.md` (Amendment 8).

**Status: complete. No further development is planned.**

## Bottom line

On about 500 S&P 500 stocks from 2012 to 2026, none of the three signals (Momentum, Value, Combined) showed a statistically detectable relationship with next-month returns. Every 90% interval on the mean rank correlation includes zero. With 108 months in the first test period, the test could only have detected a mean rank correlation of about 0.055 or larger, so the result means "not enough evidence", not "no effect". The data is free and survivor-biased, so only differences between portfolios, not return levels, should be read.

## Results at a glance

Mean monthly rank correlation (rank IC) between each signal and next-month returns, with 90% bootstrap intervals:

| Signal | 2012 to 2020 (108 months) | 2021 to 2026 (68 months, a re-test) |
|---|---:|---:|
| Momentum (12-1) | +0.007 (-0.029 to +0.043) | +0.009 (-0.032 to +0.047) |
| Value (negative P/B) | -0.017 (-0.043 to +0.010) | +0.020 (-0.018 to +0.057) |
| Combined | -0.002 (-0.036 to +0.032) | +0.015 (-0.023 to +0.051) |

The quintile spreads and Fama-MacBeth regressions agree: no interval excludes zero. The 2021 to 2026 months were already known from the first study, so they are a re-test and not out-of-sample evidence.

**Portfolios (secondary evidence).** Top-decile and top-quintile portfolios, equal weight, rebalanced monthly, 10 bps one-way costs. Of 18 headline Sharpe differences against the equal-weight benchmark (gross, Treasury bill rate), 16 have 90% intervals that include zero. The two exceptions are Value in 2012 to 2020 (decile and quintile, which overlap and are one finding measured twice): Sharpe ratios of 0.50 and 0.54 against 0.94 for the benchmark. About two such results were expected by chance, the signal-level tests do not corroborate them, and the re-test and full period do not show them. I report them as found and do not build a story on them. Excluding the 24 or 37 names with suspect book values, or charging costs, changes none of these readings.

## Why these signals

Momentum (the return from 12 months ago to one month ago) is a long-documented effect that may reflect slow reaction to news. Value (a low price-to-book ratio) may compensate for risk or reflect over-pessimism. Neither is expected to be large among liquid, heavily analysed large caps, which is why a null is a plausible outcome and not a surprise.

## Data

- **Universe:** S&P 500 membership rebuilt month by month from Wikipedia (the current list walked backwards through the changes table). Between 353 and 499 names are usable for Momentum each month, and between 295 and 426 for Value and Combined.
- **Prices:** Yahoo Finance via `yfinance`. **Book value:** SEC EDGAR XBRL filings, aligned to filing dates so each signal uses only information that was public at the time. **Treasury bill rate:** FRED TB3MS. All free.
- **Survivorship:** companies that were acquired or went bankrupt mostly have no price history on Yahoo Finance, so the universe in each month is the names that have data. In 2012, 26% of names later removed from the index had usable data, against 85% of names that stayed. Names later removed earned about 11 to 13 percentage points a year less than names that stayed (a descriptive comparison, not a correction). Return levels and Sharpe levels are therefore flattered and are not read as evidence of performance.

## Method

1. **Signals (frozen from the first study):** Momentum 12-1, Value as negative price-to-book, Combined as the average of the two cross-sectional z-scores. No tuning.
2. **Primary evidence (signal level):** the monthly rank IC (Spearman correlation of signal and next-month return), the quintile spread (top fifth minus bottom fifth), and Fama-MacBeth regressions, each with 5,000-resample bootstrap intervals.
3. **Secondary evidence (portfolios):** equal-weight top decile and top quintile, monthly rebalancing, gross and net returns on two turnover bases, Sharpe ratios with the actual Treasury bill rate and the flat 2% side by side, and a paired bootstrap interval for each Sharpe difference against the benchmark. A difference counts as significant only if the 90% interval excludes zero, and portfolio results are read only alongside the signal tests.
4. **Timing:** a signal dated *t* uses data only up to the end of month *t-1* and is paired with the return in month *t*.

## Pre-registration

The design, the reading rules and every later change were written into [`LIMITATIONS_PLAN.md`](LIMITATIONS_PLAN.md) as dated, append-only amendments and committed before the code that depends on them. The first study's out-of-sample test follows [`OUT_OF_SAMPLE_PLAN.md`](OUT_OF_SAMPLE_PLAN.md). Amendments that came from findings (stock splits, share-count ties, units errors) are listed below. Later amendments added labelled sensitivities and change no headline.

## Corrections found by the project itself

| When | What was wrong | Effect |
|---|---|---|
| Sep 2026 | The Value signal used the month-end price instead of the previous month-end, a one-month look-ahead. | Fixing it raised Value's Sharpe from 0.75 to 0.85 (before the split fix below). The bug had penalised Value. |
| Sep 2026 | The first download missed 31 December 2024, because the `yfinance` end date is exclusive. | About 0.01 of Sharpe. |
| Oct 2026 | P/B was too low for stocks that split their shares, because Yahoo rewrites old prices after a split and SEC book value per share does not change. | In-sample Value Sharpe fell from 0.86 to about 0.61, and its alpha changed sign (see the correction at the top). |
| Oct 2026 | Some SEC filings report share counts in two tags that differ by more than 100 times (177 tag pairs in 155 filings), which can give absurd P/B ratios. | Such filings have no book value. Results were also tested with winsorised P/B and with 24 and 37 names excluded. No reading changed. |

## What a null result means

A confidence interval that includes zero does not show that the effect is zero. The monthly rank IC has a standard deviation of about 0.23, so 108 months can only detect a mean of about 0.055 or more, which is larger than typical large-cap momentum effects (around 0.02 to 0.03). This study could not have found a small real effect, and it should be read as "not enough evidence".

## Limitations

- **Survivorship bias** (above). A delisting-aware data source would be the real upgrade.
- **Free data.** Wikipedia membership is approximate early on (up to about 12 names overstated in 2012). Some book values come from share counts that may carry units errors the rule cannot detect. Ticker reuse is not fully detectable.
- **S&P 500 only.** Large, liquid stocks are the hardest place to find a factor premium.
- **Simple signals.** P/B is not sector-adjusted, Momentum is not volatility-scaled, and there is no quality factor.
- **Flat costs.** 10 bps one-way, with no market impact or capacity analysis.
- **Many intervals.** The portfolio tests report 18 headline intervals at the 90% level, so about two would exclude zero by chance alone.
- **No factor-model controls.** No Fama-French regression was run.

## The first study: 17 stocks (2021 to 2026)

A fixed set of 17 large caps, tested in sample (2021 to 2024) and on 20 pre-registered months the strategies had never seen (January 2025 to August 2026). The benchmark had the highest Sharpe ratio out of sample (1.89, against 1.72 for Combined, 1.53 for Value and 1.05 for Momentum), and no strategy could be statistically distinguished from it. Value's in-sample edge is not supported after the split correction above. The full write-up, kept as published, is in [`docs/STUDY_17_STOCKS.md`](docs/STUDY_17_STOCKS.md).

## Dashboard

The live dashboard presents the 17-stock study. The results for the 500-stock study are in the CSV files under `results/`, named `universe_study_*`, and are summarised on this page.

## Reproducing the large-universe study

Python 3.13 and the pinned packages in `requirements.txt` (`pip install -r requirements.txt`). Raw downloads are cached outside Git. The cache folder is set with an environment variable (`UNIVERSE_CACHE_DIR`), and the SQLite file `database/universe_feasibility.db` is rebuilt by the first scripts (it is not committed). Result files are never overwritten: each script stops if its output already exists.

```bash
python run_universe_membership.py            # S&P 500 membership from Wikipedia
python run_universe_prices.py                # price availability from Yahoo Finance
python run_universe_fundamentals.py          # book value availability from SEC EDGAR
python rebuild_feasibility_db.py             # finishes the database; checks it against the committed Phase 3 files
python run_universe_splits.py                # split data for book value restatement
python run_universe_signals.py --momentum-only
python run_universe_signals.py --value-combined
python run_universe_spy.py                   # SPY reference prices, downloaded once
python run_universe_portfolios.py            # portfolio tests, three headline files plus two sensitivities
python -m pytest tests/ -q                   # about 300 tests, no network needed
```

## Repository map

- `src/` factor construction, backtest, risk metrics, signal tests, universe and portfolio code
- `run_universe_*.py` the large-universe pipeline, `run_*.py` the 17-stock study and its sensitivities
- `results/` every result file (`universe_study_*` for the 500-stock study)
- `LIMITATIONS_PLAN.md`, `OUT_OF_SAMPLE_PLAN.md` pre-registration and amendments
- `docs/STUDY_17_STOCKS.md` the full first study
- `index.html`, `strategies.html`, `portfolio.html`, `stocks.html` the dashboard
- `tests/` unit tests

## Future work

Sector-neutral Value, a quality factor, a Fama-French factor regression, Newey-West errors on the Fama-MacBeth slopes, and a delisting-aware data source. None is planned here.
