# Quantitative Equity Strategy Research & Backtesting Framework

*Does buying recent winners actually beat just holding everything? I built this to find out, properly.*

> **Status:** This is a living document. It reflects what I know as of Version 0.3. I'm currently working on Version 0.4 (adding more factors beyond momentum), so treat the conclusions below as specific to the momentum-only strategy I've tested so far — not a final verdict.

---

## What this project is

I wanted to move from "I understand markets and financial statements" toward actually being able to build and test an investment idea in code. This project is that attempt: a small but real research pipeline that pulls historical stock data, builds a momentum signal, constructs a portfolio from it, and backtests whether it would have actually worked.

I'm not trying to prove momentum is a winning strategy. I'm trying to test it honestly and report whatever the data actually shows — including if the answer is "no, it didn't work here."

## The question I'm asking

If you rank a group of stocks by how well they've recently performed, and buy the top performers, does that actually beat just holding all of them?

## Why I expected it might work

Momentum is one of the better-documented patterns in finance research — stocks that have been going up tend to keep going up for a while longer, at least over 3-12 month horizons. I built my signal using the standard "12-1" version of this: I measure the return over the past 12 months, but I deliberately drop the most recent month. That's because there's a separate, well-known effect (short-term reversal) where stocks that just popped tend to give some of it back over the next few weeks. Including that last month would mix two opposing effects together, so I left it out.

## How I built it

- **The stocks I used:** 17 large, liquid companies spread across different sectors (tech, financials, healthcare, energy, industrials, etc.). I picked them for size and liquidity, not because I already knew they'd do well — that would have defeated the whole point.
- **The data:** Daily adjusted closing prices from Yahoo Finance, 2020 through 2024, pulled with `yfinance` and stored in a local SQLite database.
- **The signal:** 12-month return, skipping the most recent month, calculated at the end of each month.
- **Rebalancing:** Every month, I re-rank all 17 stocks and rebuild the portfolio from scratch.
- **On the look-ahead bias question:** because I already skip the most recent month when computing momentum, the signal for any given month is fully known before that month's return happens — so I'm not accidentally using future information to make past decisions.

## How the portfolio works

Each month, I take the 5 stocks with the highest momentum score and hold them in equal amounts (20% each). I kept it simple on purpose — no volatility weighting, no optimization — because I wanted to isolate one question: does the *ranking itself* add value? Fancier weighting can come later, but only after I know the basic signal is worth building on.

My benchmark is just holding all 17 stocks equally, all the time, with no picking involved. That's the "do nothing clever" comparison.

## What actually happened

| Metric | Momentum Strategy | Just Holding All 17 |
|---|---|---|
| Period | 2021–2024 | 2021–2024 |
| Total return | 47.7% | 67.7% |
| Annualized return | 10.2% | 13.8% |
| Annualized volatility | 14.8% | 14.6% |
| Sharpe ratio | 0.56 | 0.81 |
| Max drawdown | -14.8% | -13.4% |

![Cumulative return comparison](results/backtest_equity_curve.png)

## What I make of this

Honestly — the strategy lost on every single measure. Not just lower return, but a worse Sharpe ratio and a worse drawdown too. And the thing that stands out to me: the volatility of both portfolios was almost identical (14.8% vs 14.6%). That rules out the easy excuse of "well, at least it took less risk" — it didn't. It took basically the same risk and delivered less.

My best guess for why: by only holding 5 stocks instead of 17, I gave up some diversification benefit, and it doesn't look like the momentum signal made up for that loss here. I want to be careful not to overstate this, though — this is one universe, one 4-year window, and one specific way of building the portfolio. It's a real result, but not a sweeping one.

## Where this falls short (and I want to be upfront about it)

- **Only 17 stocks.** That's a small, hand-picked group, not the actual S&P 500. A bigger universe might behave differently.
- **One time period.** 2021-2024 includes 2022, which was a genuinely rough year for momentum strategies generally. I haven't tested other periods yet.
- **No trading costs.** Rebalancing every month in real life isn't free. I haven't modeled that yet on either side, so this comparison is a bit optimistic for both.
- **Risk-free rate is a flat guess.** I used a constant 2% for the Sharpe ratio instead of pulling actual historical rates.
- **Just momentum, on its own.** I haven't combined it with anything else yet — that's literally what I'm building next.

## The dashboard

Not built yet. I want the results to actually be worth putting on a dashboard before I build one — right now that would just be a nice-looking wrapper around an early, single-factor result.

## What I used

Python (pandas, NumPy, matplotlib, yfinance), SQLite, Git/GitHub, VS Code.

## How the project is laid out

```
quant-equity-research/
├── database/            # SQLite database (generated, not committed)
├── src/
│   ├── data_loader.py   # pulls price data from Yahoo Finance
│   ├── database.py      # saves/reads from SQLite
│   ├── factors.py       # builds the momentum signal
│   ├── portfolio.py     # ranks stocks, builds the portfolio
│   ├── backtest.py      # simulates returns, compares vs benchmark
│   └── risk.py          # Sharpe ratio, volatility, drawdown
├── results/             # saved charts
├── run_data_pipeline.py # fetches + stores data end to end
├── check_data.py        # sanity-checks the stored data
└── requirements.txt
```

## What's next

- **Right now:** adding quality and value factors alongside momentum, to see if combining signals does better than momentum alone.
- **After that:** stress-testing this properly — trading costs, a bigger universe, different rebalancing frequencies, testing on a period I haven't looked at yet.
- **Eventually:** a real interactive dashboard, once there's a result worth showing off.

---

*Everything above reflects what I know as of Version 0.3. It's specific to the stocks, time period, and method I used — not a general claim about whether momentum investing works.*
