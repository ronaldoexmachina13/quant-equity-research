import json
import re
from decimal import Decimal, ROUND_HALF_UP
import pandas as pd

ORDER = ["Momentum", "Value", "Combined", "Benchmark"]
KEYS = ["momentum", "value", "combined", "benchmark"]  # lowercase, matches DATA's object keys


def round_half_up(x: float, decimals: int) -> float:
    """
    Python's built-in round() (and f-string .Nf formatting) can round the
    "wrong" way on numbers like 1.115, because 1.115 can't be represented
    exactly in binary floating point -- it's actually stored as something
    fractionally below 1.115, so round() rounds it DOWN to 1.11 instead of
    the conventionally-expected 1.12. Decimal(str(x)), built from the
    number's text representation rather than its binary float value,
    avoids that trap and rounds the way a person reading "1.115" would.
    """
    q = Decimal(10) ** -decimals
    return float(Decimal(str(x)).quantize(q, rounding=ROUND_HALF_UP))


def pct(x: float, decimals: int = 1) -> str:
    """0.477 -> '47.7%'"""
    return f"{round_half_up(x * 100, decimals):.{decimals}f}%"


def num(x: float, decimals: int = 2) -> str:
    """0.555 -> '0.56'"""
    return f"{round_half_up(x, decimals):.{decimals}f}"


def load_period(path: str) -> pd.DataFrame:
    return pd.read_csv(path, index_col="label")


def build_metrics_block(full: pd.DataFrame, p1: pd.DataFrame, p2: pd.DataFrame) -> str:
    """
    Build the JS `const METRICS = {...};` block. Chart axis bounds (max,
    step) are presentation choices, not derived from data -- they stay
    fixed here. If a future backtest produces a value outside these
    ranges, the chart will clip; check `full`/`p1`/`p2`'s max values
    against these bounds if that ever looks wrong.
    """
    sharpe_p1 = [round_half_up(float(p1.loc[s, "sharpe_ratio"]), 2) for s in ORDER]
    sharpe_p2 = [round_half_up(float(p2.loc[s, "sharpe_ratio"]), 2) for s in ORDER]
    total_p1 = [round_half_up(float(p1.loc[s, "total_return"]) * 100, 1) for s in ORDER]
    total_p2 = [round_half_up(float(p2.loc[s, "total_return"]) * 100, 1) for s in ORDER]
    ann_p1 = [round_half_up(float(p1.loc[s, "annualized_return"]) * 100, 1) for s in ORDER]
    ann_p2 = [round_half_up(float(p2.loc[s, "annualized_return"]) * 100, 1) for s in ORDER]
    vol_p1 = [round_half_up(float(p1.loc[s, "annualized_volatility"]) * 100, 1) for s in ORDER]
    vol_p2 = [round_half_up(float(p2.loc[s, "annualized_volatility"]) * 100, 1) for s in ORDER]

    return f"""const METRICS = {{
  sharpe: {{ label: "Sharpe Ratio", suffix: "", max: 1.6, step: 0.2,
    p1: {sharpe_p1}, p2: {sharpe_p2} }},
  total: {{ label: "Total Return", suffix: "%", max: 50, step: 10,
    p1: {total_p1}, p2: {total_p2} }},
  ann: {{ label: "Annualized Return", suffix: "%", max: 25, step: 5,
    p1: {ann_p1}, p2: {ann_p2} }},
  vol: {{ label: "Annualized Volatility", suffix: "%", max: 25, step: 5,
    p1: {vol_p1}, p2: {vol_p2} }}
}};"""


def build_stats_line(row: pd.Series) -> str:
    """One strategy's `stats: { ... }` line, from its full-period CSV row."""
    total = pct(row["total_return"])
    ann = pct(row["annualized_return"])
    vol = pct(row["annualized_volatility"])
    sharpe = num(row["sharpe_ratio"])
    dd = pct(row["max_drawdown"])
    return f'stats: {{ total: "{total}", ann: "{ann}", vol: "{vol}", sharpe: "{sharpe}", dd: "{dd}" }}'


def update_strategies_html(path: str, full: pd.DataFrame, p1: pd.DataFrame, p2: pd.DataFrame):
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()

    # --- Replace the whole METRICS block (no hand-written content in it) ---
    new_metrics = build_metrics_block(full, p1, p2)
    pattern = re.compile(r"const METRICS = \{.*?\n\};", re.DOTALL)
    matches = pattern.findall(html)
    if len(matches) != 1:
        raise ValueError(f"Expected exactly 1 'const METRICS' block, found {len(matches)}. Aborting -- check the file manually before rerunning.")
    html = pattern.sub(new_metrics.replace("\\", "\\\\"), html, count=1)

    # --- Replace each strategy's stats: {...} line, in DATA-object order ---
    # DATA lists strategies in the order momentum, value, combined, benchmark,
    # and "stats:" appears nowhere else in the file (FINDINGS/ANALYSIS don't
    # use that key), so replacing the 4 occurrences in order is safe.
    stats_pattern = re.compile(r"stats:\s*\{[^}]*\}")
    existing_stats = stats_pattern.findall(html)
    if len(existing_stats) != 4:
        raise ValueError(f"Expected exactly 4 'stats: {{...}}' blocks, found {len(existing_stats)}. Aborting -- check the file manually before rerunning.")

    new_lines = [build_stats_line(full.loc[s]) for s in ORDER]
    it = iter(new_lines)
    html = stats_pattern.sub(lambda m: next(it), html)

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Updated {path}:")
    print(f"  - METRICS block regenerated from {len(p1)} + {len(p2)} rows (2021-2022, 2023-2024)")
    for s, line in zip(ORDER, new_lines):
        print(f"  - {s}: {line}")


def update_index_html(path: str, full: pd.DataFrame, metadata: dict):
    """
    Update index.html's 4 mini-stat numbers in place. Order in the HTML
    is fixed (stocks, strategies, months, benchmark Sharpe) and matches
    the order these values are generated in below -- if that order in
    index.html's <div class="mini-stats"> block ever changes, this must
    change to match.
    """
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()

    n_stocks = str(metadata["n_stocks"])
        n_strategies = str(len([s for s in ORDER if s != "Benchmark"]))  # active strategies only; the benchmark is the control
    n_months = str(metadata["n_months"])
    benchmark_sharpe = num(full.loc["Benchmark", "sharpe_ratio"])

    new_values = [n_stocks, n_strategies, n_months, benchmark_sharpe]

    pattern = re.compile(r'<div class="ms-value">([^<]*)</div>')
    existing = pattern.findall(html)
    if len(existing) != 4:
        raise ValueError(f"Expected exactly 4 'ms-value' divs in {path}, found {len(existing)}. Aborting -- check the file manually before rerunning.")

    it = iter(new_values)
    html = pattern.sub(lambda m: f'<div class="ms-value">{next(it)}</div>', html)

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Updated {path}:")
    print(f"  - stocks: {n_stocks}, strategies: {n_strategies}, months: {n_months}, benchmark Sharpe: {benchmark_sharpe}")


def update_portfolio_html(path: str, timeline: dict):
    """
    Inject HOLDINGS, CONTRIBUTIONS, and METRICS_DATA into portfolio.html
    as compact JSON, matching the file's existing single-line style for
    these three consts. COMPANY_NAMES is left untouched -- it's static
    reference data (ticker -> full name), not a backtest output.
    """
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()

    holdings_json = json.dumps(timeline["holdings"], separators=(",", ":"))
    contributions_json = json.dumps(timeline["contributions"], separators=(",", ":"))
    metrics_json = json.dumps(timeline["metrics"], separators=(",", ":"))

    replacements = [
        (r"const HOLDINGS = \{.*?\};", f"const HOLDINGS = {holdings_json};"),
        (r"const METRICS_DATA = \{.*?\};", f"const METRICS_DATA = {metrics_json};"),
        (r"const CONTRIBUTIONS = \{.*?\};", f"const CONTRIBUTIONS = {contributions_json};"),
    ]

    for pattern, replacement in replacements:
        compiled = re.compile(pattern, re.DOTALL)
        matches = compiled.findall(html)
        if len(matches) != 1:
            raise ValueError(f"Expected exactly 1 match for {pattern[:30]}..., found {len(matches)}. Aborting.")
        html = compiled.sub(lambda m: replacement, html, count=1)

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Updated {path}: HOLDINGS, CONTRIBUTIONS, METRICS_DATA all regenerated from results/portfolio_timeline.json")


def update_stocks_html(path: str, computed: dict):
    """
    Update stocks.html's STOCKS array with fresh backtest-derived fields,
    while preserving each ticker's existing "name" and "sector" -- those
    are static reference facts already sitting in the file, not
    something the backtest computes, so they're read back out of the
    file itself rather than regenerated.
    """
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()

    match = re.search(r"const STOCKS = (\[.*?\]);", html, re.DOTALL)
    if not match:
        raise ValueError(f"Could not find 'const STOCKS = [...]' in {path}. Aborting.")
    existing_stocks = json.loads(match.group(1))

    seen = set()
    updated = []
    for s in existing_stocks:
        ticker = s["ticker"]
        seen.add(ticker)
        if ticker not in computed:
            raise ValueError(f"'{ticker}' is in {path} but has no computed data. Aborting.")
        c = computed[ticker]
        updated.append({
            "ticker": ticker,
            "name": s["name"],
            "sector": s["sector"],
            "latest_price": c["latest_price"],
            "latest_momentum_12_1": c["latest_momentum_12_1"],
            "latest_pb": c["latest_pb"],
            "momentum_months_selected": c["momentum_months_selected"],
            "value_months_selected": c["value_months_selected"],
            "combined_months_selected": c["combined_months_selected"],
            "total_months_evaluated": c["total_months_evaluated"],
        })

    missing = set(computed.keys()) - seen
    if missing:
        raise ValueError(f"Computed data includes tickers not present in {path}: {missing}. Aborting.")

    body = ",\n  ".join(json.dumps(s) for s in updated)
    new_block = f"const STOCKS = [\n  {body}\n];"

    html = re.sub(r"const STOCKS = \[.*?\];", lambda m: new_block, html, count=1, flags=re.DOTALL)

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Updated {path}: {len(updated)} tickers refreshed (name/sector preserved from the file)")


def build_significance_rows(path: str = "results/significance_test.csv") -> list:
    """
    Read the significance test CSV into a list of plain dicts, formatted
    for display (percentages/ratios rounded, booleans kept as real
    Python bools so they serialize as JS true/false, not the string
    "True"/"False" that a naive CSV-to-string conversion would produce).
    """
    df = pd.read_csv(path)
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "period": r["period"],
            "strategy": r["strategy"],
            "strategy_sharpe": round(float(r["strategy_sharpe"]), 2),
            "benchmark_sharpe": round(float(r["benchmark_sharpe"]), 2),
            "sharpe_diff": round(float(r["sharpe_diff"]), 2),
            "ci_lower": round(float(r["ci_90_lower"]), 2),
            "ci_upper": round(float(r["ci_90_upper"]), 2),
            "significant": bool(r["significant_at_90pct"]),
        })
    return rows


def build_cost_rows(path: str = "results/transaction_cost_impact.csv") -> list:
    """Read the transaction cost CSV into a list of plain dicts, formatted for display."""
    df = pd.read_csv(path)
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "strategy": r["strategy"],
            "avg_turnover": pct(float(r["avg_monthly_turnover"])),
            "gross_sharpe": round(float(r["gross_sharpe"]), 2),
            "net_sharpe": round(float(r["net_sharpe"]), 2),
            "gross_total_return": pct(float(r["gross_total_return"])),
            "net_total_return": pct(float(r["net_total_return"])),
        })
    return rows


def update_robustness_data(path: str, significance_rows: list, cost_rows: list):
    """
    Inject the significance-test and transaction-cost results into
    strategies.html as two JS consts, SIGNIFICANCE_DATA and COST_DATA,
    for the Robustness tab to render as tables.
    """
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()

    sig_json = json.dumps(significance_rows, separators=(",", ":"))
    cost_json = json.dumps(cost_rows, separators=(",", ":"))

    new_sig_line = f"const SIGNIFICANCE_DATA = {sig_json};"
    new_cost_line = f"const COST_DATA = {cost_json};"

    sig_pattern = re.compile(r"const SIGNIFICANCE_DATA = \[.*?\];", re.DOTALL)
    cost_pattern = re.compile(r"const COST_DATA = \[.*?\];", re.DOTALL)

    if not sig_pattern.search(html) or not cost_pattern.search(html):
        raise ValueError(
            "Could not find 'const SIGNIFICANCE_DATA' or 'const COST_DATA' placeholders in "
            f"{path}. Add the Robustness tab markup (Step B) before running this."
        )

    html = sig_pattern.sub(lambda m: new_sig_line, html, count=1)
    html = cost_pattern.sub(lambda m: new_cost_line, html, count=1)

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Updated {path}: SIGNIFICANCE_DATA ({len(significance_rows)} rows), COST_DATA ({len(cost_rows)} rows)")


if __name__ == "__main__":
    full = load_period("results/strategy_comparison_full_period.csv")
    p1 = load_period("results/strategy_comparison_2021_2022.csv")
    p2 = load_period("results/strategy_comparison_2023_2024.csv")

    update_strategies_html("strategies.html", full, p1, p2)

    significance_rows = build_significance_rows()
    cost_rows = build_cost_rows()
    update_robustness_data("strategies.html", significance_rows, cost_rows)

    with open("results/backtest_metadata.json") as f:
        metadata = json.load(f)
    update_index_html("index.html", full, metadata)

    with open("results/portfolio_timeline.json") as f:
        timeline = json.load(f)
    update_portfolio_html("portfolio.html", timeline)

    with open("results/stocks_data.json") as f:
        stocks_computed = json.load(f)
    update_stocks_html("stocks.html", stocks_computed)