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

/* ---------- reading aids for quant readers: drawdown episodes, monthly heatmap, IC statistics ---------- */
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

/* Year by month grid. With a benchmark it shows the active return (strategy minus benchmark) month by month. */
function monthlyHeatmap(containerId, returns, bench, scale) {
  const years = [...new Set(U.dates.map(d => d.slice(0, 4)))];
  const cell = v => {
    if (v === null) return `<td class="hm-empty"></td>`;
    const a = 0.08 + 0.62 * Math.min(Math.abs(v) / scale, 1);
    const bg = v < 0 ? `rgba(255,90,90,${a.toFixed(2)})` : `rgba(62,216,138,${a.toFixed(2)})`;
    const txt = (v * 100).toFixed(1).replace(/^-0\.0$/, "0.0");
    return `<td class="hm-cell" style="background:${bg}">${txt}</td>`;
  };
  let html = `<table class="heatmap"><thead><tr><th></th>${MONTH_NAMES.map(m => `<th>${m}</th>`).join("")}<th class="hm-year">Year</th></tr></thead><tbody>`;
  years.forEach(y => {
    const row = Array(12).fill(null);
    let compS = 1, compB = 1, n = 0;
    U.dates.forEach((d, i) => {
      if (d.slice(0, 4) !== y) return;
      const v = bench ? returns[i] - bench[i] : returns[i];
      row[+d.slice(5, 7) - 1] = v;
      compS *= 1 + returns[i]; if (bench) compB *= 1 + bench[i]; n++;
    });
    const total = bench ? compS - compB : compS - 1;
    html += `<tr><th>${y}</th>${row.map(cell).join("")}${cell(total).replace("hm-cell", "hm-cell hm-year")}</tr>`;
  });
  document.getElementById(containerId).innerHTML = html + "</tbody></table>";
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
  { href: "holdings.html", label: "Holdings" },
  { href: "data.html", label: "Data" },
  { href: "method.html", label: "Method" }
];
const REPO_URL = "https://github.com/ronaldoexmachina13/quant-equity-research";
function renderChrome(active, subtitle) {
  document.getElementById("chrome").innerHTML =
    `<nav class="topnav"><div class="topnav-inner"><a class="brand" href="index.html">Quant Equity Research</a><div class="links">` +
    PAGES.map(p => `<a href="${p.href}"${p.href === active ? ' class="active"' : ""}>${p.label}</a>`).join("") +
    `</div></div></nav><div class="subtitle-bar">${subtitle}</div>`;
  document.getElementById("foot").innerHTML =
    `<footer><div class="facts"><span>About 500 S&amp;P 500 members</span><span>Jan 2012 &ndash; Aug 2026</span><span>Free data, survivor-biased</span></div>` +
    `<div class="repo">Quant Equity Research &middot; <a href="${REPO_URL}" target="_blank">github.com/ronaldoexmachina13/quant-equity-research</a></div></footer>`;
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
    document.getElementById(containerId + "-readout").textContent = parts.join(" · ").toUpperCase();
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
function flagText(t, excludes) { return excludes ? `<span class="neg">${t}</span>` : t; }
function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;"); }

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
    body: "<p><b>Construction.</b> The average of the Momentum and Value z-scores, each standardised across stocks every month. The 50/50 weighting was fixed before testing and was not tuned.</p><p><b>Hypothesis.</b> The two signals are typically weakly correlated, so the average may rank more stably than either alone.</p><p><b>Failure modes.</b> It inherits the weaknesses of both signals, and it exists only for stocks with both a price history and a book value.</p>",
    note: ""
  }
};
