"""
The three exhibits of the README, in the same style as the dashboard.

Reads only saved result files and writes three NEW files (never overwritten):
  results/exhibit_1_rank_ic.png            rank IC with 90% intervals, by signal and period
  results/exhibit_2_return_by_group.png    annualised return of each fifth of stocks, ranked on the signal
  results/exhibit_3_sharpe_difference.png  portfolio Sharpe differences against the benchmark, 90% intervals

Inputs:
  results/universe_study_signal_summary_momentum.csv
  results/universe_study_signal_summary_value_combined.csv
  results/universe_study_quintile_returns.csv
  results/universe_study_portfolio_summary.csv

Nothing is recomputed here. Every number is read from those files.
Run from the repository root:  python -m scripts.universe.make_universe_charts
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

RESULTS = Path("results")
OUTPUTS = {"ic": "exhibit_1_rank_ic.png", "groups": "exhibit_2_return_by_group.png", "sharpe": "exhibit_3_sharpe_difference.png"}

SIGNALS = ["Momentum", "Value", "Combined"]
NEW_TEST, RE_TEST, FULL = "New test (2012-2020)", "Re-test (2021-2026)", "Full period (2012-2026)"
PERIOD_LABEL = {NEW_TEST: "2012 to 2020", RE_TEST: "2021 to 2026", FULL: "2012 to 2026"}

# The dashboard palette (assets/styles.css).
BG, TEXT, MUTED, GRID, AMBER, NEG = "#000000", "#E8E8E8", "#8A8A8A", "#2A2A2A", "#FFB000", "#FF5A5A"
COLOR = {"Momentum": "#3ED88A", "Value": "#29B6F6", "Combined": "#FFB000"}
plt.rcParams.update({"font.family": "DejaVu Sans Mono", "font.size": 9, "axes.facecolor": BG, "figure.facecolor": BG,
                     "text.color": TEXT, "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED})


def load():
    tests = pd.concat([pd.read_csv(RESULTS / "universe_study_signal_summary_momentum.csv"),
                       pd.read_csv(RESULTS / "universe_study_signal_summary_value_combined.csv")])
    ic = tests[tests["test"] == "rank_ic"].set_index(["signal", "period"])
    groups = pd.read_csv(RESULTS / "universe_study_quintile_returns.csv")
    summary = pd.read_csv(RESULTS / "universe_study_portfolio_summary.csv")
    headline = summary[summary["headline_test"] == True].set_index(["strategy", "size", "period"])
    return ic, groups, headline


def header(fig, label, title, subtitle):
    fig.text(0.015, 0.965, label, color=AMBER, fontsize=8.5, fontweight="bold", va="top")
    fig.text(0.015, 0.915, title, color=TEXT, fontsize=12.5, fontweight="bold", va="top")
    fig.text(0.015, 0.845, subtitle, color=MUTED, fontsize=8.5, va="top")


def frame(ax, grid_axis="x"):
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(length=0, labelsize=8.5)
    getattr(ax, f"{grid_axis}axis").grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def interval(ax, y, lower, mean, upper, color, marker, flagged=False, size=7.5):
    line = NEG if flagged else color
    ax.plot([lower, upper], [y, y], color=line, linewidth=2.2, solid_capstyle="butt")
    face = line if marker == "o" else BG
    ax.plot(mean, y, marker=marker, color=face, markersize=size, markeredgecolor=line, markeredgewidth=1.8, zorder=3)


def exhibit_1(ic, path):
    fig, ax = plt.subplots(figsize=(9, 4.4), dpi=200)
    fig.subplots_adjust(left=0.13, right=0.975, top=0.73, bottom=0.17)
    header(fig, "EXHIBIT 1  |  RANK IC", "No signal's rank IC is distinguishable from zero",
           "Mean monthly rank correlation between the signal and next month's return, 90% bootstrap interval")
    frame(ax)
    for row, signal in enumerate(SIGNALS[::-1]):
        for period, marker, offset in ((NEW_TEST, "o", 0.16), (RE_TEST, "D", -0.16)):
            r = ic.loc[(signal, period)]
            interval(ax, row + offset, r["ci_90_lower"], r["mean"], r["ci_90_upper"], COLOR[signal], marker, bool(r["excludes_zero"]))
    ax.axvline(0, color=TEXT, linewidth=1)
    ax.set_yticks(range(len(SIGNALS)))
    ax.set_yticklabels(SIGNALS[::-1], color=TEXT, fontsize=10, fontweight="bold")
    ax.set_ylim(-0.6, len(SIGNALS) - 0.4)
    ax.set_xlabel("Zero means no ranking power. Intervals that cross zero cannot be told apart from it.", fontsize=8.5, labelpad=10)
    handles = [plt.Line2D([], [], color=MUTED, marker="o", linewidth=2, markersize=7, label="2012 to 2020, 108 months"),
               plt.Line2D([], [], color=MUTED, marker="D", markerfacecolor=BG, linewidth=2, markersize=7, label="2021 to 2026, 68 months (a re-test)")]
    ax.legend(handles=handles, loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=2, frameon=False, fontsize=8.5, labelcolor=MUTED)
    fig.savefig(path, facecolor=BG)
    plt.close(fig)


def exhibit_2(groups, path):
    fig, axes = plt.subplots(1, 3, figsize=(9, 3.9), dpi=200, sharey=True)
    fig.subplots_adjust(left=0.07, right=0.985, top=0.70, bottom=0.17, wspace=0.12)
    header(fig, "EXHIBIT 2  |  RETURN BY GROUP", "Returns do not climb in steps as the signal improves",
           "Annualised return of each fifth of stocks, ranked on the signal at the start of the month, 2012 to 2026")
    full = groups[groups["period"] == FULL]
    for ax, signal in zip(axes, SIGNALS):
        frame(ax, "y")
        part = full[full["signal"] == signal].sort_values("quintile")
        ax.bar(part["quintile"], part["mean_annualised"] * 100, color=COLOR[signal], width=0.68)
        for q, v in zip(part["quintile"], part["mean_annualised"] * 100):
            ax.text(q, v + 0.35, f"{v:.1f}", ha="center", va="bottom", fontsize=8, color=TEXT)
        ax.set_title(signal, loc="left", color=TEXT, fontsize=10, fontweight="bold", pad=8)
        ax.set_xticks(range(1, 6))
        ax.set_xticklabels(["1\nlow", "2", "3", "4", "5\nhigh"], fontsize=8)
        ax.set_title(f"rank corr. {part['monotonicity'].iloc[0]:+.1f}", loc="right", color=MUTED, fontsize=8, pad=8)
        ax.set_ylim(0, 21)
    axes[0].set_ylabel("% a year", labelpad=6)
    fig.savefig(path, facecolor=BG)
    plt.close(fig)


def exhibit_3(headline, path):
    fig, axes = plt.subplots(1, 3, figsize=(9, 4.0), dpi=200, sharey=True, sharex=True)
    fig.subplots_adjust(left=0.115, right=0.985, top=0.70, bottom=0.17, wspace=0.10)
    header(fig, "EXHIBIT 3  |  PORTFOLIOS", "Only one bet stands out, and it lagged the benchmark",
           "Sharpe ratio difference against the equal-weight benchmark, top decile (dot) and top quintile (diamond), 90% intervals")
    for ax, period in zip(axes, (NEW_TEST, RE_TEST, FULL)):
        frame(ax)
        for row, signal in enumerate(SIGNALS[::-1]):
            for size, marker, offset in (("top_decile", "o", 0.16), ("top_quintile", "D", -0.16)):
                r = headline.loc[(signal, size, period)]
                interval(ax, row + offset, r["ci_90_lower_tbill"], r["sharpe_diff_tbill"], r["ci_90_upper_tbill"], COLOR[signal],
                         marker, bool(r["significant_tbill"]), size=6.5)
        ax.axvline(0, color=TEXT, linewidth=1)
        ax.set_title(PERIOD_LABEL[period], loc="left", color=TEXT, fontsize=10, fontweight="bold", pad=8)
        ax.set_xlim(-1.0, 0.9)
        ax.set_ylim(-0.6, len(SIGNALS) - 0.4)
    axes[0].set_yticks(range(len(SIGNALS)))
    axes[0].set_yticklabels(SIGNALS[::-1], color=TEXT, fontsize=10, fontweight="bold")
    fig.text(0.5, 0.045, "Red marks an interval that excludes zero. About two of 18 would do so by chance alone.", ha="center", color=MUTED, fontsize=8.5)
    fig.savefig(path, facecolor=BG)
    plt.close(fig)


def main(folder: Path = RESULTS):
    paths = {key: folder / name for key, name in OUTPUTS.items()}
    existing = [str(p) for p in paths.values() if p.exists()]
    if existing:
        sys.exit(f"Output files already exist and are never overwritten: {existing}. Stopping.")
    ic, groups, headline = load()
    exhibit_1(ic, paths["ic"])
    exhibit_2(groups, paths["groups"])
    exhibit_3(headline, paths["sharpe"])
    print("Wrote " + ", ".join(str(p) for p in paths.values()))
    print(f"Headline portfolio intervals: {len(headline)}, excluding zero: {int(headline['significant_tbill'].sum())}")


if __name__ == "__main__":
    main()
