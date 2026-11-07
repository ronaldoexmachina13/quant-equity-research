/* Shared helpers for the large-universe dashboard pages. Needs Chart.js and universe_data.js loaded first. */
Chart.defaults.font.family = '"DejaVu Sans Mono", "JetBrains Mono", Menlo, Consolas, ui-monospace, monospace';
Chart.defaults.font.size = 11;
Chart.defaults.color = "#8A8A8A";
Chart.defaults.borderColor = "#2A2A2A";
Chart.defaults.scale.grid.color = "#2A2A2A";
Object.assign(Chart.defaults.plugins.tooltip, { titleColor: "#FFB000", bodyColor: "#E8E8E8", titleFont: { weight: "700" } });

const COLORS = { Momentum: "#3ED88A", Value: "#29B6F6", Combined: "#FFB000", Benchmark: "#FFFFFF", SPY: "#8A8A8A" };
const PERIODS = [
  { key: "New test (2012-2020)", label: "2012–2020" },
  { key: "Re-test (2021-2026)", label: "2021–2026" },
  { key: "Full period (2012-2026)", label: "2012–2026" }
];
const PERIOD_LABEL = Object.fromEntries(PERIODS.map(p => [p.key, p.label]));
const SIGNALS = ["Momentum", "Value", "Combined"];
const U = UNIVERSE;
const MINUS = "−";

function sgn(x, d) { return (x < 0 ? MINUS : "+") + Math.abs(x).toFixed(d); }
function pct(x, d) { return (x * 100).toFixed(d) + "%"; }
function spct(x, d) { return (x < 0 ? MINUS : "+") + Math.abs(x * 100).toFixed(d) + "%"; }
function buttons(containerId, options, current, onPick) {
  const box = document.getElementById(containerId);
  box.innerHTML = "";
  options.forEach(o => {
    const b = document.createElement("button");
    b.className = "metric-btn" + (o.key === current ? " active" : "");
    b.textContent = o.label;
    b.onclick = () => { onPick(o.key); buttons(containerId, options, o.key, onPick); };
    box.appendChild(b);
  });
}

/* ---------- forest plot (SVG) ---------- */
function niceStep(range) {
  const raw = range / 5, mag = Math.pow(10, Math.floor(Math.log10(raw))), n = raw / mag;
  return (n < 1.5 ? 1 : n < 3.5 ? 2 : n < 7.5 ? 5 : 10) * mag;
}
function forest(svgId, rows, fmt, domain) {
  const W = 860, right = 190, left = Math.max(175, Math.max(...rows.map(r => r.label.length)) * 7.4 + 12), rowH = 30, top = 14, bottom = 36;
  const H = top + rows.length * rowH + bottom;
  let lo = domain ? domain[0] : Math.min(0, ...rows.map(r => r.lo));
  let hi = domain ? domain[1] : Math.max(0, ...rows.map(r => r.hi));
  const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
  const x = v => left + (v - lo) / (hi - lo) * (W - left - right);
  const step = niceStep(hi - lo);
  let s = "";
  for (let t = Math.ceil(lo / step) * step; t <= hi + 1e-9; t += step) {
    const tv = Math.abs(t) < step / 1000 ? 0 : t;
    s += `<line x1="${x(tv)}" x2="${x(tv)}" y1="${top}" y2="${H - bottom}" stroke="#2A2A2A"/>` +
         `<text class="muted" x="${x(tv)}" y="${H - bottom + 16}" text-anchor="middle">${fmt.axis(tv)}</text>`;
  }
  s += `<line x1="${x(0)}" x2="${x(0)}" y1="${top}" y2="${H - bottom}" stroke="#E8E8E8" stroke-width="1.2"/>`;
  rows.forEach((r, i) => {
    const y = top + i * rowH + rowH / 2;
    if (i > 0 && rows[i - 1].group !== r.group) s += `<line x1="0" x2="${W}" y1="${top + i * rowH}" y2="${top + i * rowH}" stroke="#2A2A2A" stroke-dasharray="2 3"/>`;
    const c = COLORS[r.color] || "#E8E8E8";
    s += `<text x="0" y="${y + 4}">${r.label}</text>`;
    s += `<line x1="${x(r.lo)}" x2="${x(r.hi)}" y1="${y}" y2="${y}" stroke="${c}" stroke-width="2.5"/>`;
    s += `<line x1="${x(r.lo)}" x2="${x(r.lo)}" y1="${y - 5}" y2="${y + 5}" stroke="${c}" stroke-width="2"/>`;
    s += `<line x1="${x(r.hi)}" x2="${x(r.hi)}" y1="${y - 5}" y2="${y + 5}" stroke="${c}" stroke-width="2"/>`;
    s += `<circle cx="${x(r.mean)}" cy="${y}" r="4.5" fill="${c}" ${r.excl ? 'stroke="#FF5A5A" stroke-width="2.5"' : 'stroke="#000" stroke-width="1.5"'}/>`;
    s += `<text class="${r.excl ? "flag" : "muted"}" x="${W - right + 14}" y="${y + 4}">${fmt.val(r.mean)} [${fmt.val(r.lo)}, ${fmt.val(r.hi)}]</text>`;
  });
  const svg = document.getElementById(svgId);
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.innerHTML = s;
}

/* ---------- 1. signal tests ---------- */
const TESTS = [
  { key: "rank_ic", label: "Rank IC", fmt: { axis: v => v.toFixed(2), val: v => sgn(v, 3) },
    text: "Rank IC is the monthly Spearman correlation between a signal and the next month's return. Zero means no ranking power; a positive mean means higher-ranked stocks tended to earn more. Bars are 90% bootstrap intervals (5,000 resamples). Red marks an interval that excludes zero; none do." },
  { key: "quintile_spread", label: "Quintile spread", fmt: { axis: v => (v * 100).toFixed(1) + "%", val: v => spct(v, 2) },
    text: "Average next-month return of the top-ranked fifth of stocks minus the bottom-ranked fifth. A positive spread means the signal sorted winners from losers in the expected direction." },
  { key: "fama_macbeth_single", label: "Fama-MacBeth", fmt: { axis: v => v.toFixed(3), val: v => sgn(v, 4) },
    text: "Slope from a monthly cross-sectional regression of next-month return on one signal at a time, averaged across months, with a bootstrap interval. The slope is in the signal's own units, so compare each row with zero, not with other rows." },
  { key: "fama_macbeth_joint", label: "Fama-MacBeth, joint", fmt: { axis: v => v.toFixed(3), val: v => sgn(v, 4) },
    text: "The same regression with Momentum and Value entered together, so each slope is net of the other." }
];
/* ---------- shared chart helpers ---------- */
function makeSplitLine(atBottom) { return {
  id: "splitLine",
  afterDraw(chart) {
    const x = chart.scales.x.getPixelForValue(U.split);
    const { ctx, chartArea } = chart;
    ctx.save();
    ctx.strokeStyle = "#8A8A8A"; ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.moveTo(x, chartArea.top); ctx.lineTo(x, chartArea.bottom); ctx.stroke();
    ctx.setLineDash([]); ctx.fillStyle = "#8A8A8A"; ctx.font = "700 10px " + Chart.defaults.font.family;
    const y = atBottom ? chartArea.bottom - 6 : chartArea.top + 12;
    ctx.textAlign = "right"; ctx.fillText("2012–2020", x - 6, y);
    ctx.textAlign = "left"; ctx.fillText("2021–2026 (RE-TEST)", x + 6, y);
    ctx.restore();
  }
}; }
function lineChart(canvasId, datasets, yTick, tipFmt, withSplit, splitAtBottom) {
  return new Chart(document.getElementById(canvasId), {
    type: "line",
    data: { labels: U.dates, datasets: datasets.map(d => Object.assign({ pointRadius: 0, fill: false, tension: 0.1, borderWidth: 2 }, d)) },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: i => i.dataset.label + ": " + tipFmt(i.parsed.y) } } },
      scales: { y: { ticks: { callback: yTick, maxTicksLimit: 7 } }, x: { ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 }, grid: { display: false } } }
    },
    plugins: withSplit ? [makeSplitLine(!!splitAtBottom)] : []
  });
}
function growth(returns) { let g = 1; return returns.map(r => (g *= 1 + r)); }
function drawdown(g) { let peak = 1; return g.map(v => { peak = Math.max(peak, v); return v / peak - 1; }); }

function summaryRow(period, strategy, sz, b) {
  return U.summary.find(r => r.period === period && r.strategy === strategy && (r.size || null) === (sz || null) && r.basis === b) ||
         U.summary.find(r => r.period === period && r.strategy === strategy && (r.size || null) === (sz || null) && r.basis === "gross");
}
