# CLAUDE.md: standing rules for this repository

Project: Quantitative Equity Strategy Research & Backtesting Framework (version 0.5 complete, 0.6 in planning).
Owner: Ronaldo. Strong in finance, beginner to early-intermediate in Python and SQL. Explain what you are doing and why, in financial terms, before the code.

## Environment
- Windows, VS Code, PowerShell. The venv must be active: `.\.venv\Scripts\Activate.ps1` (prompt shows `(.venv)`). If you see "No module named pytest", the venv is not active.
- Run tests with `python -m pytest tests/ -v`. All tests must pass before you say a task is done.

## Hard rules (research integrity)
1. NEVER overwrite or regenerate existing result files (`results/*.csv`, `results/*.json`, `results/*.png`) unless the task explicitly says so. New analyses write to NEW files.
2. NEVER let out-of-sample data (2025-01 onward) leak into in-sample outputs. In-sample scripts filter `common_dates <= IN_SAMPLE_END` from `config.py`.
3. `OUT_OF_SAMPLE_PLAN.md` and `LIMITATIONS_PLAN.md` are pre-registrations. Never edit an existing entry. Changes are appended as dated amendments, and only when I ask.
4. Do not tune parameters to improve results. Every variant that is run must be reported, not only the best one.
5. No dummy or invented data anywhere, except hand-made inputs inside unit tests.
6. Check for look-ahead bias on every new signal: a value dated t may only use information available at the close of t-1.
7. The CSVs are the source of truth. Never hard-code a result into HTML or README. The dashboard generator writes the data blocks.

## Writing rules
- No em dashes (the long dash) and no AI-sounding phrasing in README, HTML or comments. Use plain professional research language: "the results suggest", "the evidence is consistent with".
- Do not edit README prose or HTML commentary. Report the numbers and I will write the text with Ronaldo.

## Working style
- Plan first. Show the plan and wait for approval before editing.
- One logical change at a time. Keep functions small, with one responsibility and clear names.
- Add or update unit tests for every new function in `src/`.
- Do NOT run `git commit` or `git push`. Show `git status` and a summary of the diff. Ronaldo commits himself, with git commands on ONE line joined with `;`.
- Known quirk: `.gitattributes` is missing, so some files show as modified because of CRLF line endings only. Do not stage files you did not change.

## Repo map
- `config.py`: UNIVERSE, START_DATE, END_DATE (exclusive in yfinance), IN_SAMPLE_START/END, OUT_OF_SAMPLE_START/END.
- `src/`: `factors.py`, `portfolio.py`, `backtest.py`, `risk.py`, `database.py`, `fundamentals.py`.
- Pipeline order: `run_data_pipeline.py`, `run_fundamentals_pipeline.py`, `run_strategy_comparison.py`, `test_significance.py`, `test_transaction_costs.py`, `generate_portfolio_timeline.py`, `generate_stocks_data.py`, `generate_dashboard_data.py`. Then `run_out_of_sample.py` (out-of-sample only).
- Dashboard is static HTML plus Chart.js. Do not move it to Streamlit.
