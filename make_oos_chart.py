"""Draw the out-of-sample growth chart used at the top of the README.

Reads results/oos_monthly_returns.csv (written by run_out_of_sample.py) and
saves results/oos_growth.png in the same palette as the dashboard.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter

ORDER = ["Momentum", "Value", "Combined", "Benchmark"]
COLORS = {"Momentum": "#3ED88A", "Value": "#29B6F6", "Combined": "#FFB000", "Benchmark": "#FFFFFF"}
BG, TEXT, MUTED, GRID = "#000000", "#E8E8E8", "#8A8A8A", "#2A2A2A"

plt.rcParams["font.family"] = "monospace"
plt.rcParams["font.monospace"] = ["DejaVu Sans Mono", "Consolas", "Menlo"]

returns = pd.read_csv("results/oos_monthly_returns.csv", index_col="date", parse_dates=True)[ORDER]

# Growth of 1 invested at the end of the month before the first return
growth = (1 + returns).cumprod()
start_date = returns.index[0] - pd.offsets.MonthEnd(1)
growth = pd.concat([pd.DataFrame([[1.0] * len(ORDER)], columns=ORDER, index=[start_date]), growth])

fig, ax = plt.subplots(figsize=(10, 5), facecolor=BG)
ax.set_facecolor(BG)

for name in ORDER:
    ax.plot(growth.index, growth[name], color=COLORS[name],
            linewidth=2.4 if name == "Benchmark" else 2.0, label=name)

# End-of-line labels with the total return, nudged apart so they do not overlap
ends = sorted(((growth[n].iloc[-1], n) for n in ORDER), reverse=True)
min_gap = 0.026
label_y, prev = {}, None
for value, name in ends:
    y = value if prev is None else min(value, prev - min_gap)
    label_y[name] = y
    prev = y
for name in ORDER:
    pct = (growth[name].iloc[-1] - 1) * 100
    ax.text(growth.index[-1] + pd.Timedelta(days=12), label_y[name], f"{pct:+.1f}%",
            color=COLORS[name], fontsize=10, fontweight="bold", va="center")

ax.set_xlim(growth.index[0], growth.index[-1] + pd.Timedelta(days=75))
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:.2f}"))
ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
ax.grid(axis="y", color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
for side in ("top", "right"):
    ax.spines[side].set_visible(False)
for side in ("left", "bottom"):
    ax.spines[side].set_color(GRID)
ax.tick_params(colors=MUTED, labelsize=9)

fig.text(0.07, 0.95, "OUT OF SAMPLE: GROWTH OF $1 SINCE THE END OF DECEMBER 2024",
         color=TEXT, fontsize=11, fontweight="bold", va="top")
fig.text(0.07, 0.905, "Jan 2025 - Aug 2026, 20 months the strategies had never seen. Before trading costs.",
         color=MUTED, fontsize=9, va="top")
leg = ax.legend(loc="upper left", frameon=False, ncol=4, fontsize=9, bbox_to_anchor=(0.0, 1.0))
for text in leg.get_texts():
    text.set_color(TEXT)

fig.subplots_adjust(left=0.07, right=0.97, top=0.84, bottom=0.1)

os.makedirs("results", exist_ok=True)
fig.savefig("results/oos_growth.png", dpi=180, facecolor=BG)
plt.close(fig)
print("Saved results/oos_growth.png")
