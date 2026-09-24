import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.interpolate import RectBivariateSpline
from matplotlib.colors import LinearSegmentedColormap

# ---------- DATA: Sharpe ratio by strategy and regime ----------
# Update these four numbers per row if the underlying backtest ever changes.
# Row order must match `strategies`, column order must match `periods`.
strategies = ["Momentum", "Value", "Combined", "Benchmark"]
periods = ["2021-2022", "2023-2024"]
sharpe = np.array([
    [0.25, 0.92],   # Momentum
    [0.64, 1.12],   # Value
    [0.16, 1.27],   # Combined
    [0.59, 1.12],   # Benchmark
])

# ---------- Build a smooth interpolated surface for visual effect ----------
x_ctrl = np.arange(len(strategies))
y_ctrl = np.arange(len(periods))
spline = RectBivariateSpline(x_ctrl, y_ctrl, sharpe, kx=3, ky=1, s=0)
xi = np.linspace(0, len(strategies) - 1, 140)
yi = np.linspace(0, len(periods) - 1, 90)
Xi, Yi = np.meshgrid(xi, yi)
Zi = spline(xi, yi).T

cmap = LinearSegmentedColormap.from_list(
    "qrd", ["#0b1f3a", "#123a5c", "#1c7a6e", "#3fae6a", "#e8c547", "#d94f3d"], N=256
)

# ---------- Render ----------
fig = plt.figure(figsize=(9, 6.5), facecolor="#05070d")
ax = fig.add_axes([0.03, 0.05, 0.94, 0.9], projection="3d")
ax.set_facecolor("#05070d")

ax.plot_surface(Xi, Yi, Zi, cmap=cmap, linewidth=0, antialiased=True,
                 rstride=1, cstride=1, alpha=0.97, shade=True, vmin=0.0, vmax=1.4)
ax.plot_wireframe(Xi[::7, ::5], Yi[::7, ::5], Zi[::7, ::5],
                   color="white", linewidth=0.25, alpha=0.18)

# Mark the real measured points so the reader can see what's actual data
# vs. the smoothed interpolation between them
for xi_i in range(len(strategies)):
    for yi_i in range(len(periods)):
        ax.scatter([xi_i], [yi_i], [sharpe[xi_i, yi_i] + 0.03],
                   color="white", s=45, edgecolor="#05070d",
                   linewidth=1.2, depthshade=False, zorder=10)

ax.set_xticks(x_ctrl)
ax.set_xticklabels(strategies, color="#cfd8e3", fontsize=10.5, fontweight="bold")
ax.set_yticks(y_ctrl)
ax.set_yticklabels(periods, color="#cfd8e3", fontsize=10.5, fontweight="bold")
ax.set_zticks([0, 0.5, 1.0, 1.5])
ax.set_zticklabels(["0.0", "0.5", "1.0", "1.5"], color="#8b95a5", fontsize=8.5)
ax.set_zlabel("Sharpe Ratio", color="#8b95a5", fontsize=9.5, labelpad=8)

# Push tick labels further from the axes so "Benchmark" and "2021-2022"
# don't collide with each other in the corner where the axes meet
ax.tick_params(axis='x', pad=12)
ax.tick_params(axis='y', pad=18)

ax.xaxis.pane.fill = ax.yaxis.pane.fill = ax.zaxis.pane.fill = False
ax.xaxis.pane.set_edgecolor("#1a2438")
ax.yaxis.pane.set_edgecolor("#1a2438")
ax.zaxis.pane.set_edgecolor("#1a2438")
ax.grid(False)
# Slightly wider azimuth opens up the corner further, on top of the padding above
ax.view_init(elev=24, azim=-50)
ax.set_box_aspect((1.9, 1, 0.75))

plt.savefig("results/momentum_vs_value_regime_split.png", dpi=180, facecolor=fig.get_facecolor())
plt.close()
print("Saved results/momentum_vs_value_regime_split.png")