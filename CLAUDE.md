# CLAUDE.md: standing rules for this repository

Project: Quantitative Equity Strategy Research & Backtesting Framework (17-stock study and 500-stock study complete).

## Environment
- Windows, VS Code, PowerShell. The venv must be active: `.\.venv\Scripts\Activate.ps1` (prompt shows `(.venv)`). If you see "No module named pytest", the venv is not active.
- Run tests with `python -m pytest tests/ -v`. All tests must pass before you say a task is done.

## Hard rules (research integrity)
1. NEVER overwrite or regenerate existing result files (`results/*.csv`, `results/*.json`, `results/*.png`) unless the task explicitly says so. New analyses write to NEW files.
2. NEVER let out-of-sample data (2025-01 onward) leak into in-sample outputs. In-sample scripts filter `common_dates <= IN_SAMPLE_END` from `config.py`.
3. `docs/OUT_OF_SAMPLE_PLAN.md` and `docs/LIMITATIONS_PLAN.md` are pre-registrations. Never edit an existing entry. Changes are appended as dated amendments, and only when I ask.
4. Do not tune parameters to improve results. Every variant that is run must be reported, not only the best one.
5. No dummy or invented data anywhere, except hand-made inputs inside unit tests.
6. Check for look-ahead bias on every new signal: a value dated t may only use information available at the close of t-1.
7. The CSVs are the source of truth. Never hard-code a result into HTML or README. The dashboard generator writes the data blocks.

## Code and writing
- Add or update unit tests for every new function in `src/`.
- No em dashes in README, HTML or comments. Do not edit README prose or HTML commentary unless the task gives the exact text.
- `.gitattributes` sets `* text=auto eol=lf`, so files are stored with LF. If Git shows a file as modified and `git diff --ignore-cr-at-eol` is empty, the change is line endings only. Do not stage files you did not change.

## Repo map
- `config.py`: UNIVERSE, START_DATE, END_DATE (exclusive in yfinance), IN_SAMPLE_START/END, OUT_OF_SAMPLE_START/END.
- `src/`: `factors.py`, `portfolio.py`, `backtest.py`, `risk.py`, `database.py`, `fundamentals.py`.
- Layout: scripts live in `scripts/universe/` (500-stock study) and `scripts/first_study/` (17-stock study) and run from the repository root as modules, for example `python -m scripts.universe.run_universe_signals`. Dashboard pages are in the root, their script, style and data files in `assets/`.
- First-study order: `run_data_pipeline`, `run_fundamentals_pipeline`, `run_strategy_comparison`, `test_significance`, `test_transaction_costs`, then `run_out_of_sample` (out-of-sample only). The first-study dashboard generators were removed when its pages were retired.
- Dashboard is static HTML plus Chart.js. Do not move it to Streamlit.
