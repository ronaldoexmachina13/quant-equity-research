# Quantitative Equity Strategy Research & Backtesting Framework

*Does buying recent winners actually beat just holding everything? I built this to find out, properly.*

> **Status:** This is a living document. It reflects what I know as of Version 0.4 — momentum and value factors both fully tested, along with a combined version of the two, plus two robustness checks (portfolio concentration, and a two-period split). The period-split check in particular changed how I'd state the overall conclusion — see below. A closing synthesis tying everything together is the next stage.

---

## What this project is

I wanted to move from "I understand markets and financial statements" toward actually being able to build and test an investment idea in code. This project is that attempt: a small but real research pipeline that pulls historical stock data and company filings, builds factor signals from them, constructs portfolios, and backtests whether those strategies would have actually worked.

I'm not trying to prove any strategy is a winner. I'm trying to test ideas honestly and report whatever the data actually shows — including if the answer is "no, it didn't work here." That standard applies throughout this README: every result below is reported as I found it, not as I hoped it would look.

## The question I'm asking

If you rank a group of stocks by how well they've recently performed, and buy the top performers, does that actually beat just holding all of them? And separately: does ranking stocks by how cheap they are relative to their accounting fundamentals do any better? And does combining the two ideas beat either one alone?

## Why I expected momentum might work

Momentum is one of the better-documented patterns in finance research — stocks that have been going up tend to keep going up for a while longer, at least over 3-12 month horizons. I built my signal using the standard "12-1" version of this: I measure the return over the past 12 months, but I deliberately drop the most recent month. That's because there's a separate, well-known effect (short-term reversal) where stocks that just popped tend to give some of it back over the next few weeks. Including that last month would mix two opposing effects together, so I left it out.

## How I built the momentum strategy

- **The stocks I used:** 17 large, liquid companies spread across different sectors (tech, financials, healthcare, energy, industrials, etc.). I picked them for size and liquidity, not because I already knew they'd do well — that would have defeated the whole point.
- **The data:** Daily adjusted closing prices from Yahoo Finance, 2020 through 2024, pulled with a Python library called `yfinance` and stored in a local SQLite database (a lightweight, file-based database — no separate server needed, which is ideal for a solo research project like this).
- **The signal:** 12-month return, skipping the most recent month, calculated at the end of each month.
- **Rebalancing:** Every month, I re-rank all 17 stocks and rebuild the portfolio from scratch.
- **On the look-ahead bias question:** because I already skip the most recent month when computing momentum, the signal for any given month is fully known before that month's return happens — so I'm not accidentally using future information to make past decisions. Avoiding this kind of leakage is one of the most important disciplines in backtesting; a strategy that secretly "knows the future" will look great on paper and fail immediately in real trading.

## How the momentum portfolio works

Each month, I take the 5 stocks with the highest momentum score and hold them in equal amounts (20% each). I kept it simple on purpose — no volatility weighting, no optimization — because I wanted to isolate one question: does the *ranking itself* add value? Fancier weighting can come later, but only after I know the basic signal is worth building on.

My benchmark is just holding all 17 stocks equally, all the time, with no picking involved. That's the "do nothing clever" comparison every active strategy here has to beat.

## What actually happened with momentum

| Metric | Momentum Strategy | Just Holding All 17 |
|---|---|---|
| Period | 2021–2024 | 2021–2024 |
| Total return | 47.7% | 67.7% |
| Annualized return | 10.2% | 13.8% |
| Annualized volatility | 14.8% | 14.6% |
| Sharpe ratio | 0.56 | 0.81 |
| Max drawdown | -14.8% | -13.4% |

![Cumulative return comparison](results/backtest_equity_curve.png)

## What I make of the momentum result

Honestly — the strategy lost on every single measure. Not just lower return, but a worse Sharpe ratio and a worse drawdown too. And the thing that stands out to me: the volatility of both portfolios was almost identical (14.8% vs 14.6%). That rules out the easy excuse of "well, at least it took less risk" — it didn't. It took basically the same risk and delivered less.

My best guess for why: by only holding 5 stocks instead of 17, I gave up some diversification benefit, and it doesn't look like the momentum signal made up for that loss here. I want to be careful not to overstate this, though — this is one universe, one 4-year window, and one specific way of building the portfolio. It's a real result, but not a sweeping one.

---

## Adding a Value factor

Momentum losing on every metric made me want to test something that behaves differently. Value and momentum are known in finance research to have a negative correlation — value tends to do well precisely when momentum struggles. So the next real question was whether a value-based approach would have done better over the same period, and whether combining the two helps.

**Why value needs different data than momentum.** Momentum only needs prices, which `yfinance` handles well. Value needs actual company fundamentals — book value, specifically (a company's accounting net worth: assets minus liabilities), for a Price-to-Book ratio (market price per share divided by book value per share — a classic "is this stock cheap relative to what the company is worth on paper" measure). I wanted this to come from primary, official data rather than a paid API, so I built a small module that pulls directly from the SEC's EDGAR system — the same regulatory filings (10-Ks and 10-Qs, the annual and quarterly reports every US public company is legally required to submit) every public company must file, exposed as free, structured data with no signup or API key required.

**What this actually involves, technically.** EDGAR doesn't hand you a pre-calculated P/B ratio — it gives you the raw ingredients, tagged in a structured format called XBRL, with each figure tied to the exact date it was filed. I compute book value per share myself: `stockholders' equity ÷ shares outstanding`. Keeping track of the *filing date*, not just the number itself, matters a lot here: it tells me exactly when each figure was actually known publicly, which is what let me avoid the same look-ahead bias problem I was careful about with momentum.

### The mess of real filing data

Fetching this cleanly across all 17 tickers was genuinely harder than fetching prices, for reasons worth documenting rather than hiding — this is the part of the project where I did the most real debugging, and I think it's actually the most educational part to read.

- **Different companies tag the same concept differently.** Apple and Microsoft report shares outstanding under one standard tag; other companies use a different tag on a different reporting page (the filing's "cover page" versus the balance sheet itself), or a variant meant for companies with partially-owned subsidiaries. I found this by directly inspecting each company's raw filing data rather than guessing, and built a small system that checks multiple known tag variants and combines whatever it finds.
- **Filing dates don't line up perfectly.** A company's equity figure and its share count are sometimes filed a few weeks apart within the same reporting period. An exact-date match would silently miss these pairs, so I match dates within a 45-day window instead.
- **Restated periods can corrupt point-in-time accuracy.** Companies often re-disclose prior-period figures as comparison numbers in a later filing (e.g. a 2013 annual report re-showing 2009's numbers alongside the new ones). My first version of the code kept whichever filing was *most recent* whenever the same period appeared twice, which quietly attached a years-later filing date to a years-old number — making the data look like it was "known" to the market far later than it actually was. I fixed this to keep the *earliest* filed version of each period instead, since that's the date the figure was genuinely first made public.
- **A real, live corporate action broke my company lookup.** Exxon's data came back with only 6 usable data points, all clustered in 2024–2026 — suspiciously little for a company that size. Digging in, I found that ExxonMobil completed a legal restructuring from New Jersey to Texas in mid-2026, executed by creating a brand-new holding company that took over the "XOM" ticker going forward. SEC's own company-lookup file had already updated to point "XOM" at this new entity — which is correct and current, but that new entity only has filings from mid-2026 onward, useless for a 2020-2024 backtest. All of Exxon's actual historical filings live under the *original* corporate entity's identifier (called a CIK — Central Index Key, SEC's internal company ID), which I now hard-code as a manual override in the code, documented with the full reasoning so it doesn't look like an unexplained hack later.
- **An outlier filter I added for one problem broke a different, valid case.** After fixing Exxon, I added a rule to drop any book-value-per-share reading under $1, assuming it meant a bad data pairing. That was right for Exxon's one genuine outlier, but it also silently deleted several real, legitimate data points for Home Depot — which has run with unusually thin book equity for years because of aggressive share buybacks (buying back your own stock reduces book equity, sometimes toward zero, even for a very healthy company). A small positive book value is a real feature of Home Depot's balance sheet, not an error. I loosened the filter to only drop non-positive values, which fixed Home Depot without reopening the Exxon problem. This was a good reminder that a fix for one data problem can quietly create a new one elsewhere, and it's worth checking both sides after any change like that.
- **At least one outright bad filing exists in the wild.** Coca-Cola's data included a single row reporting exactly 0 shares outstanding in 2009 — clearly a filing error, since real values before and after are in the billions. I filter out any non-positive share count as invalid.

### Current data coverage, and why it varies

After fixing the issues above, here's what I actually have (usable Price-to-Book data points per ticker, out of 60 possible monthly observations across the 2020–2024 window):

| Ticker | Data Points | Notes |
|---|---|---|
| Most of the universe | 59–60 | Full or near-full coverage |
| HD | 47 | A real gap (roughly late 2018–mid 2020) in the raw filing data itself, not caused by the outlier filter — accepted as a documented limitation given time constraints, rather than fully traced to its root cause |
| DIS | Partial, via forward-fill from limited raw filings | Constrained — likely a date-alignment gap between otherwise-healthy equity and shares data, not fully root-caused |
| XOM | 68 raw filings (fixed) | Was 6 before the CIK correction described above; now in line with the best-covered tickers |
| V | 0 | I directly confirmed, by querying SEC's own company-lookup service, that the ticker-to-company mapping is correct — this isn't a bug in my code. Visa's multi-class share structure (it has separate Class A/B/C common stock) most likely doesn't map cleanly onto the standard tags my code checks, and the little data that does exist is too old and sparse to survive forward-filling into the 2020-2024 window. Excluded from the Value factor at this stage. |

Where coverage was sparse but partially usable, I forward-fill book value between known filing dates — carrying the last reported figure forward until a new one arrives, capped at 6 months of staleness before treating it as missing rather than stale. This is standard, defensible practice for fundamental data, which only updates quarterly at most, unlike daily prices. Critically, the fill is based on each figure's actual **filing date**, not the fiscal period it describes — a number only becomes usable once it's actually public. Filling based on the period-end date instead would effectively leak information backward in time and reintroduce the exact look-ahead bias problem I was careful to avoid with momentum.

## Comparing three strategies

With Value built, I now have three genuinely different approaches to compare, all against the same passive benchmark from before.

**Momentum** bets that recent winners keep winning. Each month, it ranks all 17 stocks by their trailing 12-month return (skipping the most recent month, for the reasons described above) and holds the top 5, equally weighted.

**Value** bets the opposite kind of thing — that cheap stocks are mispriced and will correct upward. Each month, it ranks all 17 stocks by Price-to-Book ratio and holds the 5 *cheapest* (lowest P/B), equally weighted. Low P/B is the "attractive" direction here — the opposite convention from momentum, where a high score wins.

**Combined** tries to blend both bets into a single ranking, rather than picking one philosophy over the other. This needed one extra piece of care: momentum scores (small returns, like 0.15) and Value scores (P/B-based, ranging into the tens or even hundreds) live on completely different numeric scales. Just averaging them directly would let Value's much larger numbers dominate the blend almost entirely, silently producing something that's really a Value strategy wearing a "combined" label. So each factor is first converted to a **z-score** — a statistics term for "how many standard deviations above or below this month's average is this stock, on this factor alone" — which puts both factors on the same footing before averaging them together. The top 5 by that blended score get held, equally weighted.

The same passive benchmark applies to all three: just holding all 17 stocks equally, every month, no picking involved.

### What actually happened

| Metric | Momentum | Value | Combined | Just Holding All 17 |
|---|---|---|---|---|
| Period | 2021–2024 | 2021–2024 | 2021–2024 | 2021–2024 |
| Total return | 47.7% | 80.7% | 55.0% | 67.7% |
| Annualized return | 10.2% | 15.9% | 11.6% | 13.8% |
| Annualized volatility | 14.8% | 18.5% | 14.9% | 14.6% |
| Sharpe ratio | 0.56 | 0.75 | 0.64 | **0.81** |
| Max drawdown | -14.8% | -14.5% | -14.3% | -13.4% |

*(Sharpe ratio here is return in excess of a flat 2% risk-free rate, divided by volatility — it's the number that answers "was the return worth the risk taken to get it," rather than looking at return alone.)*

### What I make of this

Value actually beat the benchmark on raw return — 15.9% annualized versus 13.8%, a real result, not noise. But it also took on noticeably more volatility to get there (18.5% versus 14.6%), and once you divide return by the risk taken to earn it, its Sharpe ratio (0.75) still falls short of just holding everything (0.81). It's a different kind of underperformance than momentum's: momentum lost on *every* dimension, while Value's picks were directionally right — the strategy just wasn't compensated enough for the extra risk it took on to make those picks.

Combining momentum and value didn't produce the best of both worlds — it landed closer to momentum's weaker profile than to Value's stronger one. I think I know why: when I checked which stocks each strategy actually picked for December 2024, momentum and value overlapped on 3 of their 5 holdings. With that much agreement between the two factors in this particular 17-stock universe, "combining" them didn't diversify the bets the way factor theory would predict in a genuinely low-correlation setting — it mostly diluted Value's stronger signal with momentum's weaker one, rather than cancelling out each strategy's individual weak spots.

The overall honest conclusion: **none of the three active strategies I built beat simply owning the whole 17-stock universe, once risk is accounted for**, in this specific universe and time period. That's consistent with a real, well-documented pattern in the wider academic literature — concentrated factor strategies often struggle to beat diversified passive exposure once volatility is priced in properly, especially over short windows and in small, correlated universes like this one. I don't take this as the project "failing" — I take it as the actual answer to the question I set out to test, reported the way I found it, which is the whole point of doing this properly instead of just looking for a result that sounds good.

## A quick robustness check: does concentration matter?

Before treating the result above as final, I wanted to stress-test one specific assumption: my momentum hypothesis for *why* the active strategies underperformed was that holding only 5 of 17 stocks gives up diversification benefit without being compensated for it. If that's really the mechanism, then holding *more* stocks should help. So I reran all three strategies exactly the same way, just holding the top 8 instead of the top 5, and compared.

| Metric | Momentum (5 → 8) | Value (5 → 8) | Combined (5 → 8) |
|---|---|---|---|
| Sharpe ratio | 0.56 → 0.65 | 0.75 → 0.55 | 0.64 → 0.68 |
| Annualized volatility | 14.8% → 14.2% | 18.5% → 15.5% | 14.9% → 13.3% |
| Max drawdown | -14.8% → -14.9% | -14.5% → -14.2% | -14.3% → -11.6% |

This didn't turn out to be a clean "yes, diversification was the whole story" result, and I think that's actually more useful than if it had been.

**Momentum got better**, in the direction my original hypothesis predicted — lower volatility, higher Sharpe. That's consistent with concentration having genuinely hurt it.

**Value got worse**, which surprised me — its Sharpe actually *dropped* (0.75 to 0.55), even though its volatility also fell. That means the return it was earning fell by more than the risk did once I diluted it from 5 names to 8. My read on this: Value's edge in this specific universe seems to be concentrated in its very best few picks — spreading into a few more, less-cheap stocks watered down the signal itself, not just its risk profile. That's a different effect than simple diversification, and it means my original "5 of 17 forgoes diversification" explanation from the momentum section doesn't fully apply to Value the same way.

**Combined improved the most**, and interestingly — its Sharpe (0.68) became the best of the three active strategies at either concentration level, and its max drawdown (-11.6%) actually beat the benchmark's (-13.4%) — the first time any active strategy in this project has beaten the benchmark on any risk metric at all.

The bottom line I'm taking from this: **the benchmark still wins on a risk-adjusted basis at both 5 and 8 holdings (Sharpe 0.81 either way)**, so that core conclusion holds up under this particular stress test rather than falling apart. But the *reason* each strategy underperforms isn't one single story — concentration genuinely explains part of momentum's problem, but it doesn't explain Value's the same way. I'd rather report that nuance honestly than force everything into one tidy explanation that only actually fits one of the three strategies.

## A second robustness check: does the benchmark win in every period, or just on average?

The concentration check above still evaluated everything over the same single 4-year window (2021-2024). That leaves an open question: is "the benchmark wins on a risk-adjusted basis" a genuinely stable conclusion, or could it be an average of some periods where an active strategy actually did better, offset by others where it did worse? To check, I split the same 4-year window into two halves — 2021-2022 and 2023-2024 — and reran all three strategies plus the benchmark independently in each half, back at the original top-5 concentration.

I want to be precise about what this test is and isn't. It's not an out-of-sample test in the machine-learning sense — none of these strategies have parameters that get "fit" to data, so there's nothing to overfit. What it actually checks is simpler and still meaningful: does the full-period conclusion hold up consistently within each sub-period on its own, or does it depend on which stretch of time you happen to be looking at?

**2021-2022:**

| Metric | Momentum | Value | Combined | Benchmark |
|---|---|---|---|---|
| Sharpe ratio | 0.25 | **0.64** | 0.10 | 0.59 |
| Max drawdown | -14.8% | -14.5% | -14.3% | -13.4% |

**2023-2024:**

| Metric | Momentum | Value | Combined | Benchmark |
|---|---|---|---|---|
| Sharpe ratio | 0.92 | 0.88 | **1.35** | 1.12 |
| Max drawdown | -7.5% | -11.2% | **-6.2%** | -6.3% |

This is the most interesting result in the whole project, and it changes how I'd state the overall conclusion. **The "benchmark always wins" finding doesn't actually hold up once you look within each period separately.** In 2021-2022, Value beat the benchmark on Sharpe (0.64 vs 0.59) — the first time any active strategy anywhere in this project beat the benchmark on a risk-adjusted basis. In 2023-2024, Combined beat the benchmark by an even larger margin (1.35 vs 1.12), and also posted a better max drawdown than the benchmark (-6.2% vs -6.3%).

What happened is that two *different* strategies each won in their own period, and averaging both periods together into one 4-year number washed both wins out, because no single strategy won consistently across the whole window. I think there's a real, economically sensible explanation for this rather than it just being noise: 2021-2022 included the 2022 rate-hike environment, a period where value-style investing has historically tended to do relatively well and momentum/growth-style investing has tended to struggle — which is exactly the pattern I saw. 2023-2024 included the AI-driven mega-cap rally, where momentum recovered and Combined — benefiting from both factors performing reasonably in that stretch — produced the best risk-adjusted result of anything tested in this entire project.

So the more accurate conclusion isn't "passive beats active, full stop" — it's that **factor performance here looks genuinely regime-dependent**, and a single average over one 4-year window that happened to contain two quite different regimes back-to-back can hide real, meaningful wins that occurred within each regime on its own. That's a more honest and more useful finding than the simpler one I had before this check, and it's a good example of why I think it's worth actually running robustness checks rather than stopping at the first clean-looking number.

## Where this falls short (and I want to be upfront about it)

- **Only 17 stocks.** That's a small, hand-picked group, not the actual S&P 500. A bigger universe might behave differently.
- **One time period.** 2021-2024 includes 2022, which was a genuinely rough year for momentum strategies generally. I haven't tested other periods yet.
- **No trading costs.** Rebalancing every month in real life isn't free. I haven't modeled that yet on any of the three strategies, so this comparison is a bit optimistic across the board.
- **Risk-free rate is a flat guess.** I used a constant 2% for the Sharpe ratio instead of pulling actual historical rates for each period.
- **A couple of fundamentals gaps remain unresolved.** V is excluded entirely; HD and DIS have real, partially-understood coverage gaps. None of this changes the overall conclusion, but it's worth being upfront that the Value and Combined results aren't built on perfectly complete data.
- **Only two robustness checks done so far, and both are fairly coarse.** I've tested one alternative concentration (top-8) and one two-way period split (2021-2022 vs 2023-2024), but haven't tried other portfolio sizes, other rebalancing frequencies, or a proper rolling/expanding-window test across more than two periods. Two periods is enough to show the full-period result isn't the whole story, but not enough to characterize exactly how regime-dependent these strategies really are. I'm also being deliberately careful not to just keep trying different settings until something looks better — that would defeat the point of testing honestly, so any further changes need their own clear justification, not just curiosity about whether they'd help the numbers.

## What I used

Python (pandas, NumPy, matplotlib, yfinance, requests), SQLite, the SEC's public EDGAR API, Git/GitHub, VS Code.

## How the project is laid out

```
quant-equity-research/
├── database/            # SQLite database (generated, not committed)
├── src/
│   ├── data_loader.py   # pulls price data from Yahoo Finance
│   ├── database.py      # saves/reads prices and book value from SQLite
│   ├── factors.py       # builds the momentum, value, and combined signals
│   ├── fundamentals.py  # pulls and cleans SEC EDGAR fundamentals for the value factor
│   ├── portfolio.py     # ranks stocks, builds the portfolio
│   ├── backtest.py      # simulates returns, compares vs benchmark
│   └── risk.py          # Sharpe ratio, volatility, drawdown
├── results/             # saved charts
├── run_data_pipeline.py # fetches + stores price data end to end
├── check_data.py        # sanity-checks the stored data
└── requirements.txt
```

## What's next

- **A full end-of-project writeup** tying the momentum, value, combined, concentration, and period-split findings together into one coherent piece, alongside the code itself — this is the immediate next step.
- **Further robustness testing, if I come back to this:** trading costs, a bigger universe, different rebalancing frequencies, and a finer-grained rolling-window test across more than two periods, to get a clearer picture of exactly how regime-dependent these strategies are, not just that they are. As always, being careful not to just keep tweaking parameters until something looks better.
- **Eventually:** a real interactive dashboard, once there's a result worth showing off.

---

*Everything above reflects what I know as of this update. The momentum, value, and combined findings are complete and specific to the stocks, time period, and method I used — not a claim about markets in general.*
