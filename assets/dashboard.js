/* Shared helpers for the large-universe dashboard pages. Needs Chart.js and universe_data.js loaded first. */
const cssVar = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
Chart.defaults.font.family = '"IBM Plex Mono", "DejaVu Sans Mono", Menlo, Consolas, ui-monospace, monospace';
Chart.defaults.font.size = 11;
Chart.defaults.color = cssVar("--muted");
Chart.defaults.borderColor = cssVar("--grid");
Chart.defaults.scale.grid.color = c => (c.scale && c.scale.axis === "y" && c.tick && c.tick.value === 0) ? cssVar("--zero") : cssVar("--grid");
Chart.defaults.scale.grid.lineWidth = c => (c.scale && c.scale.axis === "y" && c.tick && c.tick.value === 0) ? 1.5 : 1;
Chart.defaults.scales.linear.ticks.maxTicksLimit = 6;
Chart.defaults.scales.logarithmic.ticks.maxTicksLimit = 6;
Chart.defaults.scale.grid.drawTicks = false;
Chart.defaults.scale.ticks.padding = 6;
Chart.defaults.scale.border.display = false;
Chart.defaults.animation = false;
Chart.defaults.elements.line.borderWidth = 1.3;
Chart.defaults.elements.bar.borderRadius = 0;
Object.assign(Chart.defaults.plugins.tooltip, {
  backgroundColor: cssVar("--tip-bg"), borderColor: cssVar("--tip-border"), borderWidth: 1, cornerRadius: 0, padding: 8,
  titleColor: cssVar("--text-strong"), bodyColor: cssVar("--text"), titleFont: { weight: "500", size: 11 }, bodyFont: { size: 11 }, boxPadding: 3
});

const COLORS = { Momentum: cssVar("--momentum"), Value: cssVar("--value"), Combined: cssVar("--combined"), Benchmark: cssVar("--benchmark"), SPY: cssVar("--p1") };
const TEXTC = { Momentum: cssVar("--momentum-text"), Value: cssVar("--value-text"), Combined: cssVar("--combined-text") };
const textFor = c => { const k = Object.keys(COLORS).find(n => COLORS[n] === c); return (k && TEXTC[k]) || c; };
// colours are read once at load, so the theme toggle (renderChrome) saves the choice and reloads the page
const PERIODS = [
  { key: "New test (2012-2020)", label: "2012 to 2020" },
  { key: "Re-test (2021-2026)", label: "2021 to 2026" },
  { key: "Full period (2012-2026)", label: "2012 to 2026" }
];
const PERIOD_LABEL = Object.fromEntries(PERIODS.map(p => [p.key, p.label]));
const SIGNALS = ["Momentum", "Value", "Combined"];
const U = UNIVERSE;
const MINUS = "−";

function sgn(x, d) { return (x < 0 ? MINUS : "+") + Math.abs(x).toFixed(d); }
function pct(x, d) { return (x * 100).toFixed(d).replace(/^-/, MINUS) + "%"; }
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
function forest(svgId, rows, fmt, domain, band) {
  /* On a phone the plot is redrawn narrow, with the label and value above each interval, so the text stays readable */
  const compact = window.innerWidth < 640;
  const W = compact ? 400 : 860, right = compact ? 10 : 190, left = compact ? 10 : Math.max(175, Math.max(...rows.map(r => r.label.length)) * 7.4 + 12);
  const rowH = compact ? 50 : 30, top = 26, bottom = 34;
  const H = top + rows.length * rowH + bottom;
  let lo = domain ? domain[0] : Math.min(0, ...rows.map(r => r.lo), band ? -band.half : 0);
  let hi = domain ? domain[1] : Math.max(0, ...rows.map(r => r.hi), band ? band.half : 0);
  const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
  const x = v => left + (v - lo) / (hi - lo) * (W - left - right);
  const step = niceStep(hi - lo);
  let s = "";
  if (band) {
    s += `<rect x="${x(-band.half)}" y="${top}" width="${x(band.half) - x(-band.half)}" height="${H - bottom - top}" fill="${cssVar("--zero")}" fill-opacity="0.10"/>` +
         `<line x1="${x(-band.half)}" x2="${x(-band.half)}" y1="${top}" y2="${H - bottom}" stroke="${cssVar("--zero")}" stroke-opacity="0.5" stroke-dasharray="3 3"/>` +
         `<line x1="${x(band.half)}" x2="${x(band.half)}" y1="${top}" y2="${H - bottom}" stroke="${cssVar("--zero")}" stroke-opacity="0.5" stroke-dasharray="3 3"/>` +
         `<text class="dim" x="${x(-band.half)}" y="${top - 9}">${compact && band.short ? band.short : band.label}</text>`;
  }
  for (let t = Math.ceil(lo / step) * step; t <= hi + 1e-9; t += step) {
    const tv = Math.abs(t) < step / 1000 ? 0 : t;
    s += `<line x1="${x(tv)}" x2="${x(tv)}" y1="${top}" y2="${H - bottom}" stroke="${cssVar("--grid")}"/>` +
         `<text class="muted" x="${x(tv)}" y="${H - bottom + 17}" text-anchor="middle">${fmt.axis(tv)}</text>`;
  }
  s += `<line x1="${left}" x2="${W - right}" y1="${H - bottom}" y2="${H - bottom}" stroke="${cssVar("--line-strong")}"/>`;
  s += `<line x1="${x(0)}" x2="${x(0)}" y1="${top}" y2="${H - bottom}" stroke="${cssVar("--text")}" stroke-width="1"/>`;
  rows.forEach((r, i) => {
    const y0 = top + i * rowH, y = compact ? y0 + 34 : y0 + rowH / 2;
    if (i > 0 && rows[i - 1].group !== r.group) s += `<line x1="0" x2="${W}" y1="${y0}" y2="${y0}" stroke="${cssVar("--line")}" stroke-dasharray="2 3"/>`;
    const c = COLORS[r.color] || cssVar("--text");
    const textY = compact ? y0 + 16 : y + 4;
    s += `<text x="${compact ? left : 0}" y="${textY}">${r.label}${r.excl ? " *" : ""}</text>`;
    s += `<line x1="${x(r.lo)}" x2="${x(r.hi)}" y1="${y}" y2="${y}" stroke="${c}" stroke-width="2"/>`;
    s += `<line x1="${x(r.lo)}" x2="${x(r.lo)}" y1="${y - 4}" y2="${y + 4}" stroke="${c}" stroke-width="1.5"/>`;
    s += `<line x1="${x(r.hi)}" x2="${x(r.hi)}" y1="${y - 4}" y2="${y + 4}" stroke="${c}" stroke-width="1.5"/>`;
    const m = x(r.mean), d = 5.5;
    /* Filled marker: the 90% interval excludes zero. Hollow marker: it includes zero. */
    s += `<polygon points="${m},${y - d} ${m + d},${y} ${m},${y + d} ${m - d},${y}" fill="${r.excl ? c : "none"}" stroke="${c}" stroke-width="2"/>`;
    const cls = r.excl ? "flag " + (r.mean < 0 ? "neg" : "pos") : "muted";
    const vx = compact ? W - right : W - right + 14;
    s += `<text class="${cls}" x="${vx}" y="${textY}"${compact ? ' text-anchor="end"' : ""}>${fmt.val(r.mean)} [${fmt.val(r.lo)}, ${fmt.val(r.hi)}]</text>`;
  });
  const svg = document.getElementById(svgId);
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.innerHTML = s;
}

/* ---------- family forest: many tests in one SVG ----------
   One block per unit (rank IC, quintile spread, Sharpe difference and so on). Each block has a symmetric scale of its own, so zero
   sits at the same horizontal position in every block and in every family; a filled marker means the 90% interval excludes zero.
   Rows: { label, sig, rest, mean, lo, hi, excl } or { header } for a sub-heading. Block: { title, fmt, rows, band }. */
function familyForest(svgId, blocks, opt) {
  opt = opt || {};
  const small = !!opt.small, compact = small || window.innerWidth < 640;
  const W = small ? 360 : compact ? 390 : 860, Lw = small ? 84 : compact ? 150 : 215, Rw = small ? 22 : compact ? 6 : 192;
  const rowH = opt.rowH || 16, x0 = Lw, x1 = W - Rw, mid = (x0 + x1) / 2, half = (x1 - x0) / 2 - 4;
  const niceHalf = h => { const mag = Math.pow(10, Math.floor(Math.log10(h))), n = h / mag; return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * mag; };
  let y = 2, s = "";
  blocks.forEach(b => {
    const data = b.rows.filter(r => !r.header);
    const h = b.h ? niceHalf(b.h) : niceHalf(Math.max(...data.map(r => Math.max(Math.abs(r.lo), Math.abs(r.hi))), b.band || 0));
    const x = v => mid + v / h * half;
    if (b.title) { s += `<text class="blk" x="0" y="${y + 12}">${b.title}</text>`; y += 22; }
    const top = y;
    let body = "";
    b.rows.forEach(r => {
      if (r.header) { body += `<text class="sub" x="0" y="${y + rowH - 4}">${r.header}</text>`; y += rowH; return; }
      const yc = y + rowH / 2, c = COLORS[r.sig] || cssVar("--text"), label = r.sig && !r.plain ? `<tspan fill="${TEXTC[r.sig]}">${r.sig}</tspan>${esc(r.rest)}` : esc(r.label);
      const txt = `${b.fmt.val(r.mean)} [${b.fmt.val(r.lo)}, ${b.fmt.val(r.hi)}]${r.excl ? " *" : ""}`;
      body += `<g><title>${esc((r.sig || "") + (r.rest || r.label || ""))}: ${txt}</title><rect x="0" y="${y}" width="${W}" height="${rowH}" fill="transparent"/>` +
        `<text x="0" y="${yc + 4}">${label}</text>` +
        `<line x1="${x(r.lo)}" x2="${x(r.hi)}" y1="${yc}" y2="${yc}" stroke="${c}" stroke-width="1.3"/>` +
        `<line x1="${x(r.lo)}" x2="${x(r.lo)}" y1="${yc - 3}" y2="${yc + 3}" stroke="${c}"/><line x1="${x(r.hi)}" x2="${x(r.hi)}" y1="${yc - 3}" y2="${yc + 3}" stroke="${c}"/>` +
        `<circle cx="${x(r.mean)}" cy="${yc}" r="3.3" fill="${r.excl ? c : cssVar("--bg")}" stroke="${c}" stroke-width="1.3"/>` +
        (compact ? "" : `<text class="val${r.excl ? " flag" : ""}" x="${x1 + 12}" y="${yc + 4}">${txt}</text>`) + `</g>`;
      y += rowH;
    });
    const bottom = y;
    if (b.band) s += `<rect x="${x(-b.band)}" y="${top}" width="${x(b.band) - x(-b.band)}" height="${bottom - top}" fill="${cssVar("--zero")}" fill-opacity="0.12"/>`;
    [-h, -h / 2, h / 2, h].forEach(v => { s += `<line x1="${x(v)}" x2="${x(v)}" y1="${top}" y2="${bottom}" stroke="${cssVar("--grid")}"/>`; });
    s += body;
    s += `<line x1="${x(0)}" x2="${x(0)}" y1="${top}" y2="${bottom}" stroke="${cssVar("--text")}"/>` +
         `<line x1="${x0 - 4}" x2="${x1 + 4}" y1="${bottom}" y2="${bottom}" stroke="${cssVar("--line-strong")}"/>`;
    [-h, 0, h].forEach(v => { s += `<text class="muted ax" x="${x(v)}" y="${bottom + 15}" text-anchor="middle">${b.fmt.axis(v)}</text>`; });
    y = bottom + 30;
  });
  const svg = document.getElementById(svgId);
  svg.setAttribute("viewBox", `0 0 ${W} ${y}`);
  svg.innerHTML = s;
}

/* ---------- 1. signal tests ---------- */
const TESTS = [
  { key: "rank_ic", label: "Rank IC", fmt: { axis: v => v.toFixed(2), val: v => sgn(v, 3) },
    text: "Rank IC is the monthly Spearman correlation between a signal and the next month's return. Zero means no ranking power; a positive mean means higher-ranked stocks tended to earn more. Bars are 90% bootstrap intervals (5,000 resamples). A filled marker and an asterisk mark an interval that excludes zero; none do. A hollow marker means the interval includes zero." },
  { key: "quintile_spread", label: "Quintile spread", fmt: { axis: v => (v * 100).toFixed(1) + "%", val: v => spct(v, 2) },
    text: "Average next-month return of the top-ranked fifth of stocks minus the bottom-ranked fifth. A positive spread means the signal sorted winners from losers in the expected direction." },
  { key: "fama_macbeth_single", label: "Fama-MacBeth", fmt: { axis: v => v.toFixed(3), val: v => sgn(v, 4) },
    text: "Slope from a monthly cross-sectional regression of next-month return on one signal at a time, averaged across months, with a bootstrap interval. The slope is in the signal's own units, so compare each row with zero, not with other rows." },
  { key: "fama_macbeth_joint", label: "Fama-MacBeth, joint", fmt: { axis: v => v.toFixed(3), val: v => sgn(v, 4) },
    text: "The same regression with Momentum and Value entered together, so each slope is net of the other." }
];
/* ---------- shared chart helpers ---------- */
function makeSplitLine(atBottom, noLabels) { return {
  id: "splitLine",
  beforeDatasetsDraw(chart) {
    const x = chart.scales.x.getPixelForValue(U.split);
    const { ctx, chartArea } = chart;
    ctx.save();
    ctx.fillStyle = cssVar("--shade");
    ctx.fillRect(x, chartArea.top, chartArea.right - x, chartArea.bottom - chartArea.top);
    ctx.restore();
  },
  afterDraw(chart) {
    const x = chart.scales.x.getPixelForValue(U.split);
    const { ctx, chartArea } = chart;
    ctx.save();
    ctx.strokeStyle = cssVar("--ref"); ctx.setLineDash([3, 3]); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x, chartArea.top); ctx.lineTo(x, chartArea.bottom); ctx.stroke();
    ctx.setLineDash([]);
    if (noLabels) { ctx.restore(); return; }
    ctx.fillStyle = cssVar("--muted"); ctx.font = "500 11px " + Chart.defaults.font.family;
    const y = atBottom ? chartArea.bottom - 6 : chartArea.top + 12;
    const narrow = chartArea.right - chartArea.left < 420;
    ctx.textAlign = "right"; ctx.fillText(narrow ? "New test" : "2012 to 2020 · new test", x - 6, y);
    ctx.textAlign = "left"; ctx.fillText(narrow ? "Seen before" : "2021 to 2026 · seen in 17-stock study", x + 6, y);
    ctx.restore();
  }
}; }
/* Dashed horizontal reference line with a label at the right edge (used for averages and zero lines) */
function makeRefLine(value, label) { return {
  id: "refLine",
  afterDatasetsDraw(chart) {
    const { ctx, chartArea, scales } = chart;
    const y = scales.y.getPixelForValue(value);
    ctx.save();
    ctx.strokeStyle = cssVar("--muted"); ctx.setLineDash([3, 3]); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(chartArea.left, y); ctx.lineTo(chartArea.right, y); ctx.stroke();
    ctx.setLineDash([]); ctx.fillStyle = cssVar("--muted"); ctx.font = "500 11px " + Chart.defaults.font.family;
    ctx.textAlign = "right"; ctx.fillText(label, chartArea.right - 2, y - 4);
    ctx.restore();
  }
}; }
/* Smallest mean rank IC the 2012-2020 test could reliably detect (90% two-sided interval, 80% power) */
function minDetectableIC() {
  const Z = 1.645 + 0.842, sd = Math.max(...SIGNALS.map(s => icStatistics(s, 0, U.split).sd));
  return Z * sd / Math.sqrt(U.split);
}
/* Direct end labels: the series name and last value are written at the right end of each line, in the line's colour,
   so line charts need no legend. Labels that would overlap are pushed apart. Enabled per chart: plugins.endLabels.enabled. */
const endText = d => (d.endText || d.label || "").replace(/ \(.*\)$/, "");
const WIDE = () => window.innerWidth >= 700;
/* Right-hand space for the end labels: the widest label, measured, plus a gap. Zero on narrow screens. */
function endLabelPad(datasets) {
  if (!WIDE()) return 0;
  const ctx = document.createElement("canvas").getContext("2d"); ctx.font = "500 11px " + Chart.defaults.font.family;
  return Math.ceil(Math.max(...datasets.map(d => ctx.measureText(endText(d)).width))) + 12;
}
Chart.register({
  id: "endLabels",
  afterDatasetsDraw(chart, args, opts) {
    if (!opts || !opts.enabled) return;
    const { ctx, chartArea } = chart, items = [];
    chart.data.datasets.forEach((ds, i) => {
      if (!chart.isDatasetVisible(i) || ds.endLabel === false) return;
      let k = ds.data.length - 1; while (k >= 0 && (ds.data[k] === null || ds.data[k] === undefined)) k--;
      if (k < 0) return;
      const pt = chart.getDatasetMeta(i).data[k];
      items.push({ y: pt.y, x: pt.x, text: endText(ds), color: textFor(ds.borderColor) });
    });
    items.sort((a, b) => a.y - b.y);
    for (let j = 1; j < items.length; j++) if (items[j].y - items[j - 1].y < 13) items[j].y = items[j - 1].y + 13;
    ctx.save(); ctx.font = "500 11px " + Chart.defaults.font.family; ctx.textBaseline = "middle"; ctx.textAlign = "left";
    items.forEach(it => { ctx.fillStyle = it.color; ctx.fillText(it.text, Math.min(it.x + 6, chartArea.right + 6), it.y); });
    ctx.restore();
  }
});
/* Underwater plots: writes the depth and month of the first series' deepest point beside that point. Enabled per chart: plugins.troughLabel.enabled. */
Chart.register({
  id: "troughLabel",
  afterDatasetsDraw(chart, args, opts) {
    if (!opts || !opts.enabled) return;
    const ds = chart.data.datasets[0], { ctx, chartArea } = chart;
    let k = 0; ds.data.forEach((v, i) => { if (v !== null && v < ds.data[k]) k = i; });
    const pt = chart.getDatasetMeta(0).data[k], txt = "Deepest " + pct(ds.data[k], 1) + ", " + ymLabel(U.dates[k]);
    ctx.save(); ctx.font = "500 11px " + Chart.defaults.font.family; ctx.fillStyle = textFor(ds.borderColor); ctx.textBaseline = "middle";
    const right = pt.x + 8 + ctx.measureText(txt).width > chartArea.right;
    ctx.textAlign = right ? "right" : "left"; ctx.fillText(txt, pt.x + (right ? -8 : 8), Math.min(pt.y, chartArea.bottom - 8));
    ctx.restore();
  }
});
function lineChart(canvasId, datasets, yTick, tipFmt, withSplit, splitAtBottom, noSplitLabels) {
  const chart = new Chart(document.getElementById(canvasId), {
    type: "line",
    data: { labels: U.dates, datasets: datasets.map(d => Object.assign({ pointRadius: 0, fill: false, tension: 0.1, borderWidth: 1.4 }, d)) },
    options: {
      responsive: true, maintainAspectRatio: false, layout: { padding: { right: endLabelPad(datasets) } },
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { display: false }, endLabels: { enabled: WIDE() }, tooltip: { callbacks: { label: i => i.dataset.label + ": " + tipFmt(i.parsed.y) } } },
      scales: { y: { ticks: { callback: yTick, maxTicksLimit: 7 } }, x: { ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: window.innerWidth < 600 ? 5 : 8 }, grid: { display: false } } }
    },
    plugins: withSplit ? [makeSplitLine(!!splitAtBottom, noSplitLabels)] : []
  });
  hideLegendWhenLabelled(canvasId);
  return chart;
}
/* The coloured key above a line chart is redundant once the lines carry their own labels (wide screens only). */
function hideLegendWhenLabelled(canvasId) {
  if (!WIDE()) return;
  const wrap = document.getElementById(canvasId).parentElement, prev = wrap && wrap.previousElementSibling;
  if (prev && prev.classList.contains("legend-row")) prev.hidden = true;
}
function growth(returns) { let g = 1; return returns.map(r => (g *= 1 + r)); }
function drawdown(g) { let peak = 1; return g.map(v => { peak = Math.max(peak, v); return v / peak - 1; }); }

function summaryRow(period, strategy, sz, b) {
  return U.summary.find(r => r.period === period && r.strategy === strategy && (r.size || null) === (sz || null) && r.basis === b) ||
         U.summary.find(r => r.period === period && r.strategy === strategy && (r.size || null) === (sz || null) && r.basis === "gross");
}

/* ---------- reading aids for quant readers: drawdown episodes and IC statistics ---------- */
const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function ymLabel(ym) { return MONTH_NAMES[+ym.slice(5, 7) - 1] + " " + ym.slice(0, 4); }

/* Deepest peak-to-trough episodes of a monthly return series. The first peak is the start of the sample. */
function drawdownEpisodes(returns, count) {
  let g = 1, peak = 1, peakIdx = -1, cur = null;
  const eps = [];
  returns.forEach((r, i) => {
    g *= 1 + r;
    if (g >= peak) {
      if (cur) { cur.recovery = i; eps.push(cur); cur = null; }
      peak = g; peakIdx = i;
    } else {
      const dd = g / peak - 1;
      if (!cur) cur = { peak: peakIdx, trough: i, depth: dd, recovery: null };
      else if (dd < cur.depth) { cur.depth = dd; cur.trough = i; }
    }
  });
  if (cur) eps.push(cur);
  return eps.sort((a, b) => a.depth - b.depth).slice(0, count);
}
function drawdownTable(bodyId, returns, count) {
  const body = document.getElementById(bodyId);
  const last = returns.length - 1;
  body.innerHTML = drawdownEpisodes(returns, count).map(e => {
    const under = (e.recovery === null ? last : e.recovery) - e.peak;
    return `<tr><td>${e.peak < 0 ? "Start of sample" : ymLabel(U.dates[e.peak])}</td><td>${ymLabel(U.dates[e.trough])}</td>` +
           `<td>${e.recovery === null ? "Not recovered" : ymLabel(U.dates[e.recovery])}</td>` +
           `<td class="num">${pct(e.depth, 1)}</td><td class="num">${e.trough - e.peak}</td><td class="num">${under}${e.recovery === null ? "+" : ""}</td></tr>`;
  }).join("");
}

/* Mean, dispersion and hit rate of the monthly rank IC for one signal over one slice of months. */
function icStatistics(signal, from, to) {
  const x = U.ic[signal].slice(from, to), n = x.length;
  const mean = x.reduce((a, b) => a + b, 0) / n;
  const sd = Math.sqrt(x.reduce((a, b) => a + (b - mean) * (b - mean), 0) / (n - 1));
  return { n, mean, sd, ir: mean / sd, hit: x.filter(v => v > 0).length / n };
}
function icStatisticsTable(bodyId) {
  const cuts = [[0, U.split], [U.split, U.dates.length], [0, U.dates.length]];
  const body = document.getElementById(bodyId);
  body.innerHTML = "";
  SIGNALS.forEach(sig => {
    const head = document.createElement("tr");
    head.className = "tbl-group";
    head.innerHTML = `<td colspan="6">${sig}</td>`;
    body.appendChild(head);
    PERIODS.forEach((p, k) => {
      const s = icStatistics(sig, cuts[k][0], cuts[k][1]);
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${p.label}</td><td class="num">${s.n}</td><td class="num">${sgn(s.mean, 3)}</td><td class="num">${s.sd.toFixed(3)}</td><td class="num">${sgn(s.ir, 2)}</td><td class="num">${pct(s.hit, 0)}</td>`;
      body.appendChild(tr);
    });
  });
}
function rollingMean(series, window) {
  return series.map((_, i) => i < window - 1 ? null : series.slice(i - window + 1, i + 1).reduce((a, b) => a + b, 0) / window);
}

/* ---------- page chrome, shared selection and shared helpers ---------- */
const PAGES = [
  { href: "index.html", label: "Summary" },
  { href: "signals.html", label: "Signals" },
  { href: "portfolios.html", label: "Portfolios" },
  { href: "universe.html", label: "Universe" },
  { href: "method.html", label: "Method" }
];
const REPO_URL = "https://github.com/ronaldoexmachina13/quant-equity-research";
/* One sentence on the plan log, derived from assets/meta_data.js: entry counts and any gap in the amendment numbering. Shown on the Method page. */
function planLogSentence() {
  if (typeof META === "undefined") return "";
  const nums = META.entries.filter(e => e.id[0] === "A").map(e => +e.id.slice(1));
  const gaps = []; for (let k = 1; k <= Math.max(...nums); k++) if (!nums.includes(k)) gaps.push(k);
  const ds = META.entries.filter(e => e.id.startsWith("PH")).length;
  return "The plan log has " + META.entries.length + " entries: " + nums.length + " numbered amendments and " + ds + " design entries." +
    (gaps.length === 1 ? " The numbering has no Amendment " + gaps[0] + "." : "");
}
function renderChrome(active, subtitle) {
  const cov = U.coverage;
  const members = cov && cov.members ? cov.members[cov.members.length - 1] : null;
  const facts = [
    ["Data through", ymLabel(U.dates[U.dates.length - 1]), true],
    ["Sample", U.dates.length + " months from " + ymLabel(U.dates[0])],
    ["Universe", members ? members + " S&amp;P 500 members" : "S&amp;P 500 members"],
    ["Status", "Pre-specified, free data"]
  ].filter(f => f[1] !== null);
  document.getElementById("chrome").innerHTML =
    `<a class="skip" href="#main">Skip to content</a><nav class="topnav" aria-label="Pages"><div class="topnav-inner"><a class="brand" href="index.html"><svg class="logo" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><line x1="12" y1="2" x2="12" y2="22" stroke="currentColor" stroke-width="1.5"/><g stroke="currentColor" stroke-width="2"><line x1="5" y1="6" x2="17" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="14" y2="18"/></g><g fill="currentColor"><polygon points="11,3.2 13.8,6 11,8.8 8.2,6"/><polygon points="14.5,9.2 17.3,12 14.5,14.8 11.7,12"/><polygon points="8.5,15.2 11.3,18 8.5,20.8 5.7,18"/></g></svg>Quant Equity Research</a><div class="links">` +
    PAGES.map(p => `<a href="${p.href}"${p.href === active ? ' class="active" aria-current="page"' : ""}>${p.label}</a>`).join("") +
    `</div><button class="theme-toggle" id="themeToggle" type="button" aria-label="Switch between dark and light theme"></button></div></nav>` +
    `<div class="statusbar"><div class="statusbar-inner">` + facts.map(f => `<span class="st${f[2] ? " live" : ""}">${f[0] ? `<i>${f[0]}</i>` : ""}<b>${f[1]}</b></span>`).join("") + `</div></div>` +
    `<div class="subtitle-bar">${subtitle}</div>`;
  const wrap = document.querySelector(".wrap"); if (wrap) wrap.id = "main";
  const tt = document.getElementById("themeToggle"), now = document.documentElement.getAttribute("data-theme") || "dark";
  tt.textContent = now === "dark" ? "Light" : "Dark";
  tt.onclick = () => { try { localStorage.setItem("qer-theme", now === "dark" ? "light" : "dark"); } catch (e) { /* ignore */ } location.reload(); };
  renderExhibits();
  document.getElementById("foot").innerHTML =
    `<footer><div class="facts"><span>About 500 S&amp;P 500 members</span><span>${ymLabel(U.dates[0])} to ${ymLabel(U.dates[U.dates.length - 1])}</span><span>Free data, survivor-biased</span></div>` +
    `<div class="lineage">Lineage: results/*.csv &rarr; scripts/universe/generate_universe_dashboard_data.py &rarr; assets/universe_*.js &rarr; this page</div>` +
    `<div class="repo">Quant Equity Research &middot; <a href="${REPO_URL}" target="_blank">github.com/ronaldoexmachina13/quant-equity-research</a></div></footer>`;
}
/* Exhibit labels: every .panel with a data-src attribute is numbered in page order, gets a strip with its status
   (from data-stamp) and a source line naming the committed CSVs. Only attributes are read; no numbers are made here. */
const STATUS_LABEL = { registered: "Registered", exploratory: "Exploratory", sensitivity: "Sensitivity", descriptive: "Descriptive" };
function renderExhibits() {
  const last = ymLabel(U.dates[U.dates.length - 1]);
  let n = 0;
  document.querySelectorAll(".panel[data-src]").forEach(panel => {
    n += 1;
    const st = panel.dataset.stamp;
    const head = document.createElement("div");
    head.className = "exh";
    head.innerHTML = `<span class="exn">Exhibit ${n}</span>` + (STATUS_LABEL[st] ? `<span class="stamp stamp-${st}">${STATUS_LABEL[st]}</span>` : "");
    panel.insertBefore(head, panel.firstChild);
    const src = document.createElement("p");
    src.className = "src";
    src.innerHTML = `<b>Source</b>${panel.dataset.src} &middot; data through ${last}`;
    panel.appendChild(src);
  });
}
/* Amendment log: the newest dated entries of the pre-specification, read from assets/meta_data.js */
function renderTape(containerId, count) {
  const box = document.getElementById(containerId);
  if (!box || typeof META === "undefined") return;
  const rows = META.entries.slice().reverse().slice(0, count);
  box.className = "tape";
  box.innerHTML = rows.map(e => `<div class="tape-row"><span class="t-n">${e.id}</span><span class="t-d">${e.date}</span><span class="t-x">${e.note}</span></div>`).join("") +
    `<div class="tape-foot">Newest ${rows.length} of ${META.entries.length} dated entries &middot; append-only &middot; <a href="${REPO_URL}/blob/main/${META.planFile}" target="_blank">${META.planFile}</a></div>`;
}

const SIZE_LABEL = { top_decile: "Top decile", top_quintile: "Top quintile" };
const BASIS_LABEL = { gross: "Before costs", net: "After 10 bps costs" };
const SEL = { sig: "Value", size: "top_decile", basis: "gross" };
(function loadSelection() {
  try {
    const s = JSON.parse(localStorage.getItem("qer-selection") || "null");
    if (!s) return;
    if (SIGNALS.includes(s.sig)) SEL.sig = s.sig;
    if (SIZE_LABEL[s.size]) SEL.size = s.size;
    if (BASIS_LABEL[s.basis]) SEL.basis = s.basis;
  } catch (e) { /* storage unavailable: defaults apply */ }
})();
function saveSelection() { try { localStorage.setItem("qer-selection", JSON.stringify(SEL)); } catch (e) { /* ignore */ } }

/* Selection bar. fields is a subset of ["sig", "size", "basis"]. sticky keeps it in view while scrolling. */
function contextStrip(containerId, fields, onChange, sticky) {
  const box = document.getElementById(containerId);
  box.className = "ctx-bar" + (sticky ? " sticky" : "");
  box.innerHTML = `<div class="ctx-controls">` + fields.map(f => `<div class="ctrl-group" id="${containerId}-${f}"></div>`).join("") + `</div><div class="ctx-readout" id="${containerId}-readout"></div>`;
  const options = {
    sig: SIGNALS.map(s => ({ key: s, label: s })),
    size: Object.keys(SIZE_LABEL).map(k => ({ key: k, label: SIZE_LABEL[k] })),
    basis: Object.keys(BASIS_LABEL).map(k => ({ key: k, label: BASIS_LABEL[k] }))
  };
  const readout = () => {
    const parts = [];
    if (fields.includes("sig")) parts.push(SEL.sig);
    if (fields.includes("size")) parts.push(SIZE_LABEL[SEL.size]);
    if (fields.includes("basis")) parts.push(BASIS_LABEL[SEL.basis]);
    document.getElementById(containerId + "-readout").textContent = parts.join(" · ");
  };
  fields.forEach(f => buttons(containerId + "-" + f, options[f], SEL[f], k => { SEL[f] = k; saveSelection(); readout(); onChange(f); }));
  readout();
}
function selectionText(fields) {
  const parts = [];
  if (fields.includes("sig")) parts.push(SEL.sig);
  if (fields.includes("size")) parts.push(SIZE_LABEL[SEL.size].toLowerCase());
  if (fields.includes("basis")) parts.push(BASIS_LABEL[SEL.basis].toLowerCase());
  return parts.join(", ");
}

function benchmarkKey(sig) { return sig === "Momentum" ? "Momentum" : "Value and Combined"; }
function benchmarkName(sig) { return sig === "Momentum" ? "Benchmark (Momentum usable)" : "Benchmark (Value and Combined usable)"; }
/* Marks an interval that excludes zero with bold type and an asterisk; colour follows the sign of the value */
function flagText(t, excludes) { return excludes ? `<span class="flagval ${/^\[?\u2212/.test(t) ? "neg" : "pos"}">${t}*</span>` : t; }
function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;"); }

/* Turns "<p><b>Label.</b> text</p>" runs into a definition list: a plain label column and a text column. */
function defList(body) {
  const rows = [...body.matchAll(/<p><b>(.*?)\.<\/b>\s*(.*?)<\/p>/g)];
  return rows.length ? `<dl class="def">${rows.map(r => `<dt>${r[1]}</dt><dd>${r[2]}</dd>`).join("")}</dl>` : body;
}
const DEFINITIONS = {
  Momentum: {
    body: "<p><b>Construction.</b> The signal is the return from 12 months before the trade date to the end of the previous month. No month is skipped, so the latest month's return, which tends to reverse, is included. Each month the stocks with usable prices are ranked. The top decile (about 40 names) or top quintile (about 80) is held at equal weight until the next month.</p><p><b>Hypothesis.</b> Candidate explanations are slow incorporation of news and investor under-reaction, so recent winners may keep outperforming for a while.</p><p><b>Failure modes.</b> Momentum is exposed to sharp reversals at market turning points, and its holdings turn over quickly, so costs matter.</p>",
    note: "Momentum uses prices only, so the book-value sensitivities do not apply to it."
  },
  Value: {
    body: "<p><b>Construction.</b> The signal is minus the price-to-book ratio: the previous month-end price divided by book value per share from SEC filings, aligned to the date each filing became public. Low ratios rank highest. The top decile or quintile is held at equal weight.</p><p><b>Hypothesis.</b> Candidate explanations are compensation for distress risk and investor over-pessimism about cheap names.</p><p><b>Failure modes.</b> Price-to-book is not sector-adjusted, is a poor measure for firms with large intangible assets, and cheap stocks can stay cheap for long periods. Share splits and share-count errors in the filings had to be corrected, which is why the sensitivities exist.</p>",
    note: ""
  },
  Combined: {
    body: "<p><b>Construction.</b> The average of the Momentum and Value z-scores, each standardised across stocks every month. The 50/50 weighting was fixed before testing and was not tuned.</p><p><b>Hypothesis.</b> If the two signals carry different information, averaging them may rank more stably than either alone. Their monthly rank ICs are negatively correlated (-0.53 over 2012 to 2026).</p><p><b>Failure modes.</b> It inherits the weaknesses of both signals, and it exists only for stocks with both a price history and a book value. In practice Combined is mostly Momentum: over 2012 to 2026 its monthly rank IC has a correlation of +0.98 with Momentum's, and 85.8% of its top-decile name-months are also in Momentum's top decile (73.5% the other way round).</p>",
    note: ""
  }
};
