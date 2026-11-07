"""
Charts and headline table for the large-universe study (Phase 4).

Reads only saved result files and writes three NEW files (never overwritten):
  results/universe_study_ic_intervals.png         rank IC with 90% intervals, by signal and period
  results/universe_study_sharpe_diff_intervals.png  portfolio Sharpe differences with 90% intervals
  results/universe_study_headline_table.md        the table used in the README

Inputs:
  results/universe_study_signal_summary_momentum.csv
  results/universe_study_signal_summary_value_combined.csv
  results/universe_study_portfolio_summary.csv

Nothing is recomputed here. Every number is read from those files.
Run:  python make_universe_charts.py
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

RESULTS = Path("results")
IC_PNG = RESULTS / "universe_study_ic_intervals.png"
SHARPE_PNG = RESULTS / "universe_study_sharpe_diff_intervals.png"
TABLE_MD = RESULTS / "universe_study_headline_table.md"

SIGNALS = ["Momentum", "Value", "Combined"]
NEW_TEST, RE_TEST = "New test (2012-2020)", "Re-test (2021-2026)"
PERIODS = [NEW_TEST, RE_TEST, "Full period (2012-2026)"]
PERIOD_LABEL = {NEW_TEST: "2012 to 2020", RE_TEST: "2021 to 2026", "Full period (2012-2026)": "2012 to 2026"}
SIZE_LABEL = {"top_decile": "top decile", "top_quintile": "top quintile"}

INK, MUTED, GRID = "#1f2933", "#6b7785", "#e4e7eb"
BLUE, GRAY, ACCENT = "#2a6fb0", "#7b8794", "#d95f02"


def load():
    ic = pd.concat([pd.read_csv(RESULTS / "universe_study_signal_summary_momentum.csv"),
                    pd.read_csv(RESULTS / "universe_study_signal_summary_value_combined.csv")])
    ic = ic[ic["test"] == "rank_ic"].set_index(["signal", "period"])
    summary = pd.read_csv(RESULTS / "universe_study_portfolio_summary.csv")
    headline = summary[summary["headline_test"] == True].set_index(["strategy", "size", "period"])
    return ic, headline


def style(ax):
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, length=0, labelsize=9)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def ic_chart(ic):
    fig, ax = plt.subplots(figsize=(8, 3.6), dpi=200)
    style(ax)
    spec = [(NEW_TEST, BLUE, "o", +0.16, "2012 to 2020 (108 months)"),
            (RE_TEST, GRAY, "D", -0.16, "2021 to 2026 (68 months, a re-test)")]
    for row, signal in enumerate(SIGNALS[::-1]):
        for period, color, marker, offset, _ in spec:
            r = ic.loc[(signal, period)]
            y = row + offset
            ax.plot([r["ci_90_lower"], r["ci_90_upper"]], [y, y], color=color, linewidth=2, solid_capstyle="round")
            ax.plot(r["mean"], y, marker=marker, color=color, markersize=7, markeredgecolor="white", markeredgewidth=1.2)
    ax.axvline(0, color=INK, linewidth=1)
    ax.set_yticks(range(len(SIGNALS)))
    ax.set_yticklabels(SIGNALS[::-1], color=INK, fontsize=10)
    ax.set_ylim(-0.6, len(SIGNALS) - 0.4)
    ax.set_xlabel("Mean monthly rank IC with 90% bootstrap interval", color=MUTED, fontsize=9)
    ax.set_title("No signal's rank correlation with next-month returns is distinguishable from zero",
                 loc="left", color=INK, fontsize=11, fontweight="bold", pad=22)
    handles = [plt.Line2D([], [], color=c, marker=m, linewidth=2, markersize=7, label=l) for _, c, m, _, l in spec]
    ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, frameon=False,
              fontsize=8.5, labelcolor=MUTED, handlelength=1.6, columnspacing=1.6)
    fig.tight_layout()
    fig.savefig(IC_PNG, facecolor="white")
    plt.close(fig)


def sharpe_chart(headline):
    rows = [(s, z) for s in SIGNALS for z in ("top_decile", "top_quintile")]
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.5), dpi=200, sharey=True, sharex=True)
    for ax, period in zip(axes, PERIODS):
        style(ax)
        for i, (strategy, size) in enumerate(rows[::-1]):
            r = headline.loc[(strategy, size, period)]
            sig = bool(r["significant_tbill"])
            color = ACCENT if sig else GRAY
            ax.plot([r["ci_90_lower_tbill"], r["ci_90_upper_tbill"]], [i, i], color=color, linewidth=2, solid_capstyle="round")
            ax.plot(r["sharpe_diff_tbill"], i, marker="o", color=color, markersize=6.5, markeredgecolor="white", markeredgewidth=1.1)
            if sig:
                ax.annotate(f"{r['sharpe_diff_tbill']:+.2f}", (r["sharpe_diff_tbill"], i), xytext=(0, 8),
                            textcoords="offset points", ha="center", va="bottom", fontsize=8, color=ACCENT, fontweight="bold")
        ax.axvline(0, color=INK, linewidth=1)
        ax.set_title(PERIOD_LABEL[period], loc="left", color=INK, fontsize=10, fontweight="bold")
        ax.set_xlim(-1.0, 0.9)
    axes[0].set_yticks(range(len(rows)))
    axes[0].set_yticklabels([f"{s}, {SIZE_LABEL[z]}" for s, z in rows[::-1]], color=INK, fontsize=9)
    fig.supxlabel("Sharpe ratio difference against the equal-weight benchmark (gross, Treasury bill rate), 90% paired bootstrap interval",
                  color=MUTED, fontsize=8.5)
    handles = [plt.Line2D([], [], color=GRAY, marker="o", linewidth=2, label="interval includes zero"),
               plt.Line2D([], [], color=ACCENT, marker="o", linewidth=2, label="interval excludes zero")]
    fig.legend(handles=handles, loc="upper right", ncol=2, frameon=False, fontsize=8.5, labelcolor=MUTED)
    fig.tight_layout(rect=(0, 0.0, 1, 0.97))
    fig.savefig(SHARPE_PNG, facecolor="white")
    plt.close(fig)


def fmt(mean, lower, upper, digits=3):
    return f"{mean:+.{digits}f} ({lower:+.{digits}f} to {upper:+.{digits}f})"


def table(ic, headline):
    lines = ["| Test | 2012 to 2020 | 2021 to 2026 | Reading |", "|---|---:|---:|---|"]
    for signal in SIGNALS:
        cells, flags = [], []
        for period in (NEW_TEST, RE_TEST):
            r = ic.loc[(signal, period)]
            cells.append(fmt(r["mean"], r["ci_90_lower"], r["ci_90_upper"]))
            flags.append(bool(r["excludes_zero"]))
        reading = "Interval includes zero in both periods" if not any(flags) else "Interval excludes zero in at least one period"
        lines.append(f"| {signal}: mean rank IC | {cells[0]} | {cells[1]} | {reading} |")
    for strategy in SIGNALS:
        cells, flags = [], []
        for period in (NEW_TEST, RE_TEST):
            r = headline.loc[(strategy, "top_decile", period)]
            sig = bool(r["significant_tbill"])
            text = fmt(r["sharpe_diff_tbill"], r["ci_90_lower_tbill"], r["ci_90_upper_tbill"], 2)
            cells.append(f"**{text}**" if sig else text)
            flags.append(sig)
        if not any(flags):
            reading = "Interval includes zero in both periods"
        else:
            where = [PERIOD_LABEL[p] for p, f in zip((NEW_TEST, RE_TEST), flags) if f]
            reading = f"**Interval excludes zero in {' and '.join(where)} only**; the headline signal tests include zero, some sensitivities lean the same way"
        lines.append(f"| {strategy}: Sharpe difference against benchmark, top decile | {cells[0]} | {cells[1]} | {reading} |")
    return "\n".join(lines) + "\n"


def main():
    existing = [str(p) for p in (IC_PNG, SHARPE_PNG, TABLE_MD) if p.exists()]
    if existing:
        sys.exit(f"Output files already exist and are never overwritten: {existing}. Stopping.")
    ic, headline = load()
    ic_chart(ic)
    sharpe_chart(headline)
    text = table(ic, headline)
    with open(TABLE_MD, "x", encoding="utf-8") as f:
        f.write(text)
    n = len(headline)
    print(f"Wrote {IC_PNG}, {SHARPE_PNG}, {TABLE_MD}")
    print(f"Headline intervals: {n}, excluding zero: {int(headline['significant_tbill'].sum())}")
    print(text)


if __name__ == "__main__":
    main()
