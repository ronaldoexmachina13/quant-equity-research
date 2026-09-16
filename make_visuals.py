import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
from scipy.interpolate import RectBivariateSpline
from matplotlib.colors import LinearSegmentedColormap

strategies = ["Momentum", "Value", "Combined", "Benchmark"]
periods = ["2021-2022", "2023-2024"]
sharpe = np.array([
    [0.25, 0.92],
    [0.64, 0.88],
    [0.10, 1.35],
    [0.59, 1.12],
])

x_ctrl = np.arange(4)
y_ctrl = np.arange(2)
spline = RectBivariateSpline(x_ctrl, y_ctrl, sharpe, kx=3, ky=1, s=0)
xi = np.linspace(0, 3, 120)
yi = np.linspace(0, 1, 70)
Xi, Yi = np.meshgrid(xi, yi)
Zi = spline(xi, yi).T

cmap = LinearSegmentedColormap.from_list(
    "qrd", ["#0b1f3a", "#123a5c", "#1c7a6e", "#3fae6a", "#e8c547", "#d94f3d"], N=256
)

fig = plt.figure(figsize=(5.5, 5.5), facecolor="#05070d")
ax = fig.add_axes([0.05, 0.08, 0.9, 0.8], projection="3d")
ax.set_facecolor("#05070d")

ax.plot_surface(Xi, Yi, Zi, cmap=cmap, linewidth=0, antialiased=True,
                 rstride=1, cstride=1, alpha=0.98, shade=True, vmin=0.0, vmax=1.4)
ax.plot_wireframe(Xi[::6, ::5], Yi[::6, ::5], Zi[::6, ::5],
                   color="white", linewidth=0.25, alpha=0.15)

for xi_i in range(4):
    for yi_i in range(2):
        ax.scatter([xi_i], [yi_i], [sharpe[xi_i, yi_i] + 0.03],
                   color="white", s=40, edgecolor="#05070d",
                   linewidth=1.1, depthshade=False, zorder=10)

ax.set_xticks(x_ctrl)
ax.set_xticklabels(strategies, color="#cfd8e3", fontsize=9, fontweight="bold")
ax.set_yticks([0, 1])
ax.set_yticklabels(periods, color="#cfd8e3", fontsize=9, fontweight="bold")
ax.set_zlabel("Sharpe Ratio", color="#8b95a5", fontsize=8, labelpad=6)
ax.xaxis.pane.fill = ax.yaxis.pane.fill = ax.zaxis.pane.fill = False
ax.grid(False)
ax.set_box_aspect((1.7, 1, 0.75))

fig.text(0.06, 0.94, "MOMENTUM vs VALUE: THE REGIME SPLIT",
         color="white", fontsize=15, fontweight="bold", family="sans-serif")
fig.text(0.06, 0.905, "Sharpe ratio by strategy and market regime",
         color="#9aa5b8", fontsize=10, family="sans-serif")

def rotate(frame):
    ax.view_init(elev=25, azim=frame)
    return fig,

n_frames = 60
anim = FuncAnimation(fig, rotate, frames=np.linspace(0, 360, n_frames), interval=70, blit=False)
anim.save("results/momentum_vs_value_regime_split_rotating.gif", writer=PillowWriter(fps=14), dpi=80)
print("saved gif")