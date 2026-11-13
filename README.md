# Do Momentum and Value Still Work in the S&P 500?

[![tests](https://github.com/ronaldoexmachina13/quant-equity-research/actions/workflows/tests.yml/badge.svg)](https://github.com/ronaldoexmachina13/quant-equity-research/actions/workflows/tests.yml)

**Short answer: not detectably.** This is a pre-specified test of two of the best-known stock factors, momentum (the return over the 11 months to the end of the previous month) and price-to-book value, and their average, on about 500 large US companies from January 2012 to August 2026. None of them can be shown to rank next-month returns better than chance. The sections below show how the test was built to avoid look-ahead and tuning, and where it still falls short.

[**Open the dashboard**](https://ronaldoexmachina13.github.io/quant-equity-research/) &nbsp;|&nbsp; [Method and pre-specification](docs/LIMITATIONS_PLAN.md)

The hypothesis is that momentum and value earn a premium among US large caps. Neither premium is expected to be large among liquid, heavily analysed companies, so a null result is a plausible outcome.

The work uses Python (pandas, NumPy, SciPy, statsmodels, matplotlib), SQLite and SQL for the index-membership and coverage queries and the 17-stock cross-checks, and a static HTML and Chart.js dashboard.

As of 13 November 2026. Prices run to August 2026, and the pre-specification includes amendments up to Amendment 18.

![Exhibit 1: rank IC by signal](results/exhibit_1_rank_ic.png)

## Findings

| Question | Answer |
|---|---|
| **Do the rankings predict returns?** | Not detectably. In the six main tests (rank IC for each of three signals over two test periods) every interval includes zero. Another 27 tests ask the same question in other ways, so they are not independent evidence, and none of them excludes zero either. |
| **Do the top-ranked portfolios beat the benchmark?** | On the registered Sharpe test, no: only 2 of 18 comparisons exclude zero, about what chance gives (1.8 if independent). Both are Value in 2012 to 2020 (the top decile and the top quintile, so the holdings overlap), and in both Value did worse than the benchmark on a risk-adjusted basis. A regression of each portfolio's return on its benchmark's, added after the results (Amendment 16), finds 11 of 18 alphas that exclude zero, against about 2 expected by chance if independent. Nine are positive (all Momentum or Combined, which are close to the same signal; the four full-period ones are +3.6% to +4.7% a year) and 2 are negative (Value, 2012 to 2020). A four-factor regression (Amendment 18) finds none of the 18 excluding zero. These later checks are exploratory. |
| **Could the test have found an effect?** | Only a large one. With 108 months it detects a mean rank IC of about 0.055 (80% power). Smaller effects would be missed, so this is "no evidence of an effect", not "proof of no effect". |
| **Is the data good enough?** | For return levels, no. The data are free and survivor-biased: among names that have a price history, those later dropped from the index earned about 3% to 4% a year in this sample, against about 16% for names that stayed. The groups are formed with hindsight, so this is not an estimate of the bias. Differences between a portfolio and its benchmark are affected too, because the missing names are missing from both, in a direction that depends on the signal. |

### Reading guide

- **Rank IC (information coefficient).** Each month, rank the stocks by the signal and by the return they earned next month, then take the correlation of the two rankings. +1 means the signal ordered returns perfectly, 0 means it told you nothing, and -1 means it was backwards. With 108 months, a mean Momentum rank IC of about 0.055 or more is detected 80% of the time, and smaller values are often missed (see Power in Hypotheses and method).
- **90% interval.** The range of values the data are consistent with. If it contains zero, the result cannot be told apart from no effect.
- **Sharpe ratio.** Return above the risk-free rate per unit of volatility. A Sharpe difference compares a portfolio with its benchmark, and a negative value means the portfolio did worse.
- **Benchmark.** The equal-weight average of the same usable names in the same month, not the S&P 500 index. Each portfolio is compared with the benchmark built from the names its own signal could use (Momentum, or Value and Combined), so a name missing from the data is missing from both sides. SPY is shown separately as a reference.
- **Group (quintile).** One fifth of the stocks, ranked on the signal. Group 5 has the highest signal.

## Why a null result is worth reporting

Published factors often weaken when tested carefully. Hou, Xue and Zhang re-tested 452 published anomalies with methods that limit the weight of tiny stocks and found that 65% of them could not clear the usual significance hurdle, a t-statistic of 1.96 ([Review of Financial Studies, 2020](https://doi.org/10.1093/rfs/hhy131)). Large, liquid stocks such as the S&P 500 are expected to be a harder place to find a premium, because they are closely analysed and cheap to trade. That is a hypothesis, not something this study tests. A null here is a plausible and informative outcome. What matters is whether the test is reliable enough to trust that answer.

![Exhibit 2: return by group](results/exhibit_2_return_by_group.png)

If a signal worked, the five groups would earn more in steps from left to right. Momentum's top group is the best in every period, but the groups below it are not ordered. For Value in 2012 to 2020 the most expensive fifth earned the most (18.2% a year, against 14.2% for the cheapest fifth), and no interval is reported for that gap.

![Exhibit 3: portfolio Sharpe differences](results/exhibit_3_sharpe_difference.png)

The one interval that stands out is Value in 2012 to 2020, measured twice (top decile and top quintile). It is absent from the re-test and from the full period, and it points the wrong way for a value premium. The registered tests of the signal itself for the same period all include zero. In the three secondary sensitivities (winsorised price-to-book and two exclusion lists), 5 of 66 signal intervals exclude zero, against about 7 expected by chance if they were independent. All five are Value Fama-MacBeth slopes for 2012 to 2020, all with a negative slope whose interval stops just short of zero, and they share the same months and stocks.

Costs of 10 bps one way change none of these readings. No explanation has been tested.

The 2021 to 2026 months were already known from an earlier 17-stock study, so they are a re-test and not out-of-sample evidence.

## Safeguards in the design

- **Pre-specified.** The design, the reading rules and every later change are dated, append-only amendments in [`docs/LIMITATIONS_PLAN.md`](docs/LIMITATIONS_PLAN.md), committed before the code that depends on them. They are dated Git commits made by the author, not entries in an independent registry. Post-hoc additions are labelled as such.
- **No look-ahead.** A signal dated t uses only information available at the end of month t-1 and is held through month t. Book values enter on the date the filing became public.
- **No tuning.** Signal definitions were frozen from the earlier study. No lookback, weight or threshold was varied to improve a result.
- **Interval choice.** 90% bootstrap intervals, cross-checked with Newey-West and block-bootstrap intervals. Every test is counted, and the number of false positives expected by chance is stated beside the result.
- **Errors found and corrected.** These are logged below: a one-month look-ahead in the Value signal, a split-adjustment bug that had flattered Value (its 17-stock Sharpe fell from 0.86 to about 0.61 once fixed), unit errors in SEC share counts that produced absurd price-to-book ratios, and a Momentum label that described an 11-month return as 12-1.
- **Tested and reproducible.** More than 400 tests, many of them hand-worked cases, run on every push. Seeds are fixed, and the raw-data cache is checksummed in `results/data_manifest.csv`.

## Limits

- **Survivorship.** Acquired and bankrupt companies mostly lack free price history. A delisting-aware source such as CRSP is the real fix. Which way the bias runs for each strategy is not tested here and need not be the same for all of them: acquired companies often earned a premium and bankrupt ones lost most of their value, and both are missing. Coverage is lowest from 2012 to 2015 (61% to 66% of index member-months usable for Value), so the early years of the 2012 to 2020 test rest on the weakest data.
- **Data quality.** Wikipedia membership is approximate early on, and some book values rest on share counts that may carry unit errors the rule cannot detect. Filings that show negative book equity are dropped, so those companies keep an older positive book value for up to six months or leave the Value and Combined tests.
- **Scope.** Large caps only. P/B is not sector-adjusted, Momentum is not volatility-scaled, there is no quality factor, costs are a flat 10 bps one way, with no market impact or capacity analysis. A four-factor Fama-French regression and sector-neutral variants were added after the results (Amendments 16 to 18), so they are exploratory and not registered. In the four-factor regression, none of the 18 regressions of the registered portfolios (six portfolios, three periods) has an alpha interval that excludes zero, before costs. Of the 24 same-names and sector-neutral variant regressions, 8 have an interval that excludes zero, all with a positive alpha (Value or Combined), against about 2.4 expected by chance if they were independent.
- Value in 2012 to 2020 had higher volatility than its benchmark: 25.4% a year against 15.0% for the top decile, a beta of 1.55 to the benchmark and a maximum drawdown of 49.0% against 27.0% (before costs). Its return was 13.4% a year against 14.7%. In those years 53.2% of its name-months are in Financials and 25.9% have no sector label. Sectors are one current label per stock, not a historical one.
- Combined is mostly Momentum. Over 2012 to 2026 the monthly rank IC of Combined has a correlation of +0.98 with Momentum's. Of Combined's top-decile name-months, 85.8% are also in Momentum's top decile in the same month (73.5% the other way round; the two universes differ in size, with 353 to 499 usable names for Momentum and 295 to 426 for Combined). The overlap with Value is small: 6.9% of Combined's top-decile name-months are also in Value's, and 4.0% of Momentum's. The Combined results should therefore not be read as a separate test from Momentum's. The monthly rank ICs of Momentum and Value are correlated at -0.53.
- **Sharpe convention.** The Sharpe ratio is the annualised return minus the compounded risk-free return, divided by annualised volatility. The arithmetic version, mean monthly excess return over volatility, gives differences that are mostly 5% to 25% smaller across the 18 gross portfolio comparisons and changes no sign. It was recomputed from the saved monthly returns after the results and is not saved in a result file or part of the registered tests. Of the 18 differences, 17 are smaller (15 of them by 5% to 25%) and one is about 19% larger (Momentum top decile, 2021 to 2026).
- **Power.** With 108 months the test detects a mean rank IC of about 0.055 (80% power), so a smaller premium cannot be ruled out.

## Explore

| Page | Question it answers |
|---|---|
| Summary | What is the answer, and why believe it? |
| Signals | Do the rankings predict next-month returns? |
| Portfolios | Do top-ranked stocks beat the benchmark? |
| Universe | Can the data be trusted, and which names drove the results? |
| Method | What was done, in what order? |

<details>
<summary><b>Hypotheses and method</b></summary>

Momentum is the return from the close 12 months before the trade date to the close of the previous month. No month is skipped, so the most recent month, whose return tends to reverse, is part of the signal. A true 12-1 version, which does skip it, was run as a labelled sensitivity (Amendment 15, shown below) and changes no reading. Momentum was documented by Jegadeesh and Titman (Journal of Finance, 1993). Common explanations, which this study does not test, are slow incorporation of news and investor under-reaction. Value is the negative price-to-book ratio, which may compensate for distress risk or reflect over-pessimism. Neither premium is expected to be large among liquid, heavily analysed large caps, so a null result is a plausible outcome. Combined is the average of the two cross-sectional z-scores, with the 50/50 weighting fixed before testing.

1. **Timing.** A signal dated t uses only information available at the end of month t-1 and is held through month t.
2. **Primary evidence.** Rank IC, quintile spread and Fama-MacBeth slopes (single and joint), each with a bootstrap interval.
3. **Secondary evidence.** Top-decile and top-quintile portfolios, with a paired bootstrap interval for each Sharpe difference. A difference counts only if the 90% interval excludes zero, and portfolio results are read alongside the signal tests.
4. **No tuning.** Signal definitions were frozen from the earlier study. No lookback, weight or threshold was varied to improve a result.

**Pre-specification.** The design, the reading rules and every later change are recorded as dated, append-only amendments in [`docs/LIMITATIONS_PLAN.md`](docs/LIMITATIONS_PLAN.md), committed before the code that depends on them. The earlier study's out-of-sample test follows [`docs/OUT_OF_SAMPLE_PLAN.md`](docs/OUT_OF_SAMPLE_PLAN.md).

**Power.** The monthly rank IC has a standard deviation of up to about 0.23. With 108 months the minimum detectable mean IC is about 0.055 for Momentum (0.052 for Combined and 0.041 for Value), at the 10% two-sided level with 80% power, using each sample's own standard deviation. A true mean IC of 0.02 would be detected in about 24% of such samples for Momentum, 25% for Combined and 34% for Value. The test could not have found a small real effect, so an interval that includes zero does not show the effect is zero.

</details>

<details>
<summary><b>Data</b></summary>

| Item | Source and treatment |
|---|---|
| Universe | S&P 500 membership rebuilt month by month from Wikipedia. Between 353 and 499 names are usable for Momentum each month and between 295 and 426 for Value and Combined (from `results/universe_study_monthly_counts_momentum.csv` and `_value_combined.csv`). |
| Prices | Yahoo Finance via `yfinance`, adjusted close. |
| Book value | SEC EDGAR filings, aligned to the filing date. Book value per share is restated for later splits. |
| Risk-free rate | Three-month Treasury bill, FRED. |

**Survivorship.** Acquired and bankrupt companies mostly have no free price history, so each month's universe is the set of names that have data. In 2012, for Value and Combined, 26% of names later removed from the index had usable data against 85% of names that stayed. Of the 294 names removed from the index in or after January 2012, 158 (54%) have no price history. Counting all 370 removed names in the membership file, including 76 removed before 2012 that never enter a test month, 226 (61%) have none. Names later removed that did have data earned an annualised mean return of about 3% to 4% over 2012 to 2026 (4.0% for the names usable for Momentum, 3.1% for Value and Combined), against about 16% for names that stayed. The means are monthly averages times 12 and the groups are formed with hindsight, so this is descriptive. It is not a correction.

</details>

<details>
<summary><b>Sensitivities: true 12-1 momentum and survivorship by year</b></summary>

**True 12-1 momentum.** The registered Momentum signal ends at the close of the previous month and skips no month (see the data integrity log). A true 12-1 version, which ends one month earlier, was run as a labelled sensitivity (Amendment 15). It does not replace the registered result.

- **Signal tests.** The mean rank IC over the 175 usable months is +0.005 (90% interval -0.021 to +0.031), against +0.008 for the registered signal, and the two monthly series have a correlation of 0.97. The previous month's return on its own has a mean rank IC of -0.024 in 2012 to 2020 (interval -0.051 to +0.002). That is the direction the short-term reversal effect would predict, but it cannot be told apart from zero.
- **Portfolios.** Sharpe differences against the benchmark, gross of costs, Treasury bill rate, with 90% intervals:

| Portfolio | Period | Registered | True 12-1 |
|---|---|---|---|
| Momentum, top decile | 2012 to 2020 | +0.28 (-0.12 to +0.63) | +0.09 (-0.29 to +0.42) |
| Momentum, top decile | 2021 to 2026 | +0.06 (-0.50 to +0.54) | +0.04 (-0.52 to +0.54) |
| Momentum, top decile | Full period | +0.12 (-0.22 to +0.42) | +0.03 (-0.31 to +0.32) |
| Momentum, top quintile | 2012 to 2020 | +0.24 (-0.09 to +0.55) | +0.21 (-0.09 to +0.50) |
| Momentum, top quintile | 2021 to 2026 | +0.11 (-0.30 to +0.47) | +0.06 (-0.34 to +0.41) |
| Momentum, top quintile | Full period | +0.15 (-0.11 to +0.38) | +0.12 (-0.13 to +0.34) |
| Combined, top decile | 2012 to 2020 | +0.14 (-0.23 to +0.48) | +0.02 (-0.37 to +0.36) |
| Combined, top decile | 2021 to 2026 | +0.22 (-0.27 to +0.68) | +0.17 (-0.32 to +0.62) |
| Combined, top decile | Full period | +0.13 (-0.17 to +0.41) | +0.05 (-0.26 to +0.32) |
| Combined, top quintile | 2012 to 2020 | +0.17 (-0.17 to +0.48) | +0.09 (-0.22 to +0.37) |
| Combined, top quintile | 2021 to 2026 | +0.19 (-0.18 to +0.54) | +0.19 (-0.17 to +0.52) |
| Combined, top quintile | Full period | +0.15 (-0.10 to +0.38) | +0.11 (-0.12 to +0.33) |

The 2021 to 2026 months were already known from the 17-stock study, so they are a re-test and not out-of-sample evidence. The true 12-1 point estimates are lower than the registered ones in 11 of the 12 rows and the same in the twelfth, by up to about 0.19, so the unskipped month may have helped the registered signal slightly in this sample. The intervals overlap almost entirely, and none of the 36 portfolio comparisons (two strategies, two group sizes, three periods and three cost bases) has an interval that excludes zero, with the Treasury bill rate or with the flat 2%. With 12 headline intervals, about 1.2 would be expected to exclude zero by chance alone. No reading changes.

**Survivorship by year.** A descriptive table for the registered signals, one row per year and signal. It adds no test.

- The share of index member-months usable for Value rises from 61% in 2012 to 84% in 2026, and for Momentum from 71% to 99%. Among names later removed from the index, the usable share for Value rises from 26% to 63%.
- The yearly Sharpe differences have mixed signs, and no pattern with coverage is visible. Two of the 45 yearly intervals exclude zero (Value in 2017 and Momentum in 2020), against about 4.5 expected by chance. Each interval rests on 8 to 12 months and is very wide, so the table is context and not evidence.

The files are `results/universe_study_*_momentum_skip_month.csv` and `results/universe_study_survivorship_by_year.csv`.

</details>

<details>
<summary><b>Data integrity log</b></summary>

| When | Defect | Effect |
|---|---|---|
| Sep 2026 | Value used the month-end price instead of the previous month-end, a one-month look-ahead. | Raised the 17-stock Value Sharpe from 0.75 to 0.85, before the split fix below. The bug had penalised Value. |
| Sep 2026 | The first download missed 31 December 2024, because the `yfinance` end date is exclusive. | About 0.01 of Sharpe. |
| Oct 2026 | Price-to-book was too low for stocks that split their shares (Walmart 2024, NextEra 2020): Yahoo rewrites old prices after a split and SEC book value per share does not change. | 17-stock in-sample Value Sharpe fell from 0.86 to about 0.61, below the benchmark's 0.81. Alpha moved from +2.9% (t = 0.62) to about -0.9% (t = -0.17). Out-of-sample results are essentially unchanged. See `results/value_split_*.csv` and Amendment 8. |
| Oct 2026 | Some SEC filings report share counts under two tags that differ by more than 100 times (177 tag pairs in 155 filings, counted in `results/universe_study_bv_jumps.csv`), giving absurd price-to-book ratios. | Such filings carry no book value. Results were also run with winsorised P/B and with 24 and 37 names excluded. |
| Nov 2026 | Momentum was described as 12-1, skipping the most recent month. The code uses the return from 12 months before the trade date to the end of the previous month, with no month skipped. | No reading changes. A true 12-1 version gives a similar rank IC (mean +0.005 against +0.008, monthly series correlation 0.97, no interval excluding zero). The description was corrected; see Amendment 15 and the `_momentum_skip_month` files. |

</details>

<details>
<summary><b>Reproducing the results</b></summary>

Python 3.13 and the pinned packages (`pip install -r requirements.txt`). Raw downloads are cached outside Git in the folder named by the environment variable `UNIVERSE_CACHE_DIR`. SEC EDGAR and Wikipedia ask automated clients to identify themselves, so set `SEC_CONTACT_EMAIL` to your own address before running the download scripts. The SQLite file `database/universe_feasibility.db` is not committed. `results/data_manifest.csv` lists the size and SHA-256 checksum of every cached download (`make_data_manifest --verify` compares). Result files are never overwritten: each script stops if its output exists, and the committed `results/` files already exist in a fresh clone. Run everything from the repository root, as modules.

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
python -m scripts.universe.run_universe_extras          # quintile returns and Newey-West and block-bootstrap intervals (Amendment 14)
python -m scripts.universe.run_universe_skip_month --write   # true 12-1 sensitivity and survivorship by year (Amendment 15); --dry-run writes nothing
python -m scripts.universe.make_data_manifest           # checksums of the raw-data cache; add --verify to compare later
python -m scripts.universe.make_universe_charts         # the charts and table on this page
python -m scripts.universe.run_universe_holdings        # holdings and per-stock summary, checked against committed returns
python -m scripts.universe.generate_universe_dashboard_data   # assets/universe_*_data.js (never overwrites)
python -m pytest tests/ -q                              # more than 400 tests, no network needed
```

Rerunning a result-writing script in a fresh clone stops at the first existing file. To regenerate a result, write it to a new folder or move the old file first.

</details>

<details>
<summary><b>Design choices</b></summary>

- **Static dashboard, not Streamlit.** The pages are plain HTML and JavaScript served by GitHub Pages, so anyone can open them without installing anything or running a server. The data behind them are committed files, generated by a script that never overwrites.
- **Scripts, not notebooks.** Each stage is a module-run script that stops if its output already exists, so results cannot be silently replaced, and the logic is covered by tests. Notebooks would hide state between cells.
- **SQLite, with SQL as an independent check.** A local SQLite file needs no database server. The queries in `sql/` recompute key results of the 17-stock study directly from the stored prices and book values, as a cross-check on the Python code (see `sql/README.md`).
- **AI-assisted build.** An AI coding assistant was used, and `CLAUDE.md` records the standing rules it works under. The design, the reading rules and every correction are logged in the dated amendments.

</details>

<details>
<summary><b>Repository layout</b></summary>

```
index.html, signals.html, portfolios.html, universe.html, method.html
                              dashboard pages (GitHub Pages serves the repository root)
assets/                       dashboard.js, styles.css and the generated universe_*_data.js files
config.py                     17-stock universe and evaluation windows (earlier study)
src/                          library code: data loading, SQLite storage, factors, backtest, risk, universe
                              construction, book value rules, split adjustment, signal evaluation, portfolios, data manifest
scripts/universe/             the large-universe pipeline, one script per stage (see Reproducing)
scripts/first_study/          the 17-stock study and its sensitivities
tests/                        unit tests checked against hand-worked cases, run on every push
sql/                          schema and analytical queries (see sql/README.md)
results/                      every generated CSV, JSON and chart (universe_* is the 500-stock study)
docs/                         the dated plan and its amendments, the out-of-sample plan, and the 17-stock write-up
database/                     SQLite files, generated and not committed
CLAUDE.md                     standing rules for the AI coding assistant used on this project
```

</details>

<details>
<summary><b>Earlier study: 17 stocks</b></summary>

A fixed set of 17 large caps, tested in sample (2021 to 2024) and on 20 pre-specified months it had not seen (January 2025 to August 2026). The benchmark had the highest out-of-sample Sharpe ratio (1.89, against 1.72 for Combined, 1.53 for Value and 1.05 for Momentum) and no strategy could be statistically distinguished from it. Value's in-sample edge does not survive the split correction. Some first-study scripts and result files, such as the robustness grid, keep the momentum labels 12-1, 9-1 and 6-1 as published; each is the return from 12, 9 or 6 months before the trade date to the end of the previous month, with no month skipped (Amendment 15). The write-up is in [`docs/STUDY_17_STOCKS.md`](docs/STUDY_17_STOCKS.md).

</details>

## Next steps

A delisting-aware data source, a delisting-return sensitivity, point-in-time sector labels for the sector-neutral work and a quality factor.

## Licence

MIT. See [`LICENSE`](LICENSE). This is research code, not investment advice.

**Data sources.** The index membership in `results/universe_membership.csv` is derived from the tables on the Wikipedia pages [List of S&P 500 companies](https://en.wikipedia.org/wiki/List_of_S%26P_500_companies) and [Historical components of the S&P 500](https://en.wikipedia.org/wiki/Historical_components_of_the_S%26P_500), whose text is available under the [Creative Commons Attribution-ShareAlike 4.0 licence](https://creativecommons.org/licenses/by-sa/4.0/). The code rebuilt those tables into monthly membership intervals, so the file is a modified version, and it is shared under the same CC BY-SA 4.0 terms. Prices come from Yahoo Finance and book values from SEC EDGAR filings. The raw downloads are not redistributed in this repository.
