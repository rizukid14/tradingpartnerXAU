"""
Template dashboard HTML (mode live/static).

Data TIDAK di-embed di sini. Halaman memuat data via:
  - fetch('/api/data')  → mode live (dashboard.py --serve)
  - window.__INITIAL_DATA__ → mode static (di-inject oleh render_html)
Lalu semua konten dirender via JS. Auto-refresh 5 detik (fetch saja, TANPA reload halaman)
sehingga tidak ada kedipan/animasi ulang.
"""

TEMPLATE = r"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Trading Bot Dashboard — XAUUSD Gold</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root {
  --bg: #141413;
  --panel: #1e1e1d;
  --panel-hover: #262625;
  --border: #2d2d2b;
  --border-light: #3f3f3d;
  --text: #e6e6e3;
  --muted: #8a8a85;
  --muted-light: #b5b5b0;
  --green: #4ade80;
  --green-bg: rgba(74, 222, 128, 0.08);
  --red: #f87171;
  --red-bg: rgba(248, 113, 113, 0.08);
  --blue: #a3a3a3;
  --blue-bg: rgba(163, 163, 163, 0.08);
  --amber: #cc7a5c;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  padding: 16px;
  min-height: 100vh;
  font-size: 13px;
  line-height: 1.5;
}

/* Header Compact */
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
  gap: 12px;
}
.brand { display: flex; align-items: center; gap: 10px; }
.brand h1 { font-size: 18px; font-weight: 700; letter-spacing: -0.3px; color: #fff; }
.badge-live {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--green-bg);
  color: var(--green);
  border: 1px solid rgba(34, 197, 94, 0.2);
  padding: 2px 8px;
  border-radius: 99px;
  font-size: 11px;
  font-weight: 600;
}
.badge-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--green); animation: pulse 2s infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

.sub { color: var(--muted-light); font-size: 12px; font-family: 'JetBrains Mono', monospace; }

.filters { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.filters label { font-size: 12px; color: var(--muted); font-weight: 500; }
.filters select {
  background: var(--panel);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 5px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-family: inherit;
  outline: none;
  cursor: pointer;
  transition: border-color 0.15s;
}
.filters select:hover, .filters select:focus { border-color: var(--amber); }

/* Bento Box Grid System */
.bento-grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 14px;
}

.bento-box {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
  transition: border-color 0.2s;
}
.bento-box:hover { border-color: var(--border-light); }

.bento-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--muted-light);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.bento-title span { color: var(--muted); font-size: 11px; font-weight: 400; text-transform: none; }

/* Grid Spans */
.col-12 { grid-column: span 12; }
.col-8 { grid-column: span 8; }
.col-6 { grid-column: span 6; }
.col-5 { grid-column: span 5; }
.col-4 { grid-column: span 4; }
.col-3 { grid-column: span 3; }
.col-7 { grid-column: span 7; }

@media (max-width: 1024px) {
  .col-8, .col-7, .col-6, .col-5, .col-4, .col-3 { grid-column: span 12; }
}

/* KPI Cards Layout */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 10px;
  width: 100%;
}
.kpi-card {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
}
.kpi-label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; font-weight: 500; }
.kpi-value { font-size: 18px; font-weight: 700; margin-top: 3px; font-family: 'JetBrains Mono', monospace; }

.green { color: var(--green); }
.red { color: var(--red); }
.muted { color: var(--muted); }

/* Charts Inside Bento */
.chart-container { position: relative; width: 100%; height: 220px; }
.chart-container-sm { position: relative; width: 100%; height: 170px; }

/* Tables Clean & Compact */
.table-wrap { width: 100%; overflow-x: auto; max-height: 320px; overflow-y: auto; }
table { width: 100%; border-collapse: collapse; font-size: 12px; font-family: 'JetBrains Mono', monospace; }
th, td { padding: 7px 10px; text-align: left; border-bottom: 1px solid var(--border); white-space: nowrap; }
th { color: var(--muted-light); font-weight: 600; font-family: 'Inter', sans-serif; cursor: pointer; user-select: none; position: sticky; top: 0; background: var(--panel); z-index: 2; }
th:hover { color: var(--amber); }
tr:hover { background: var(--panel-hover); }

/* Cards & Badges */
.sym-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; }
.sym-card { background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; }
.sym-name { font-weight: 700; color: var(--amber); font-size: 13px; margin-bottom: 4px; }

.lesson-item { background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; margin-bottom: 6px; font-size: 12px; }
.theme-tag { display: inline-block; background: rgba(255,255,255,0.05); border-radius: 4px; padding: 1px 6px; font-size: 10px; color: var(--muted-light); margin-right: 6px; text-transform: uppercase; }
.sym-tag { color: var(--amber); font-weight: 600; margin-right: 6px; }

.empty-hint { text-align: center; padding: 30px; color: var(--muted); font-size: 12px; }

/* Scrollbar Customization */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: var(--panel); }
::-webkit-scrollbar-thumb { background: var(--border-light); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--muted); }
</style>
</head>
<body>

<div class="header">
  <div class="brand">
    <h1>🏛️ CONSENSUS TRADING DASHBOARD</h1>
    <div id="live-badge-wrap"></div>
  </div>
  <div class="sub" id="sub-line">Memuat data...</div>
  <div class="filters">
    <label>Simbol: <select id="f-symbol"></select></label>
    <label>Rentang: <select id="f-range">
      <option value="all">Semua Waktu</option>
      <option value="7d">7 Hari</option>
      <option value="30d">30 Hari</option>
    </select></label>
    <label>Mode Trading: <select id="f-trading-mode" title="Pilih mode simbol yang di-scan bot (perlu dashboard mode serve)">
      <option value="xau">🎯 XAU Only</option>
      <option value="xau_pairs">🔄 XAU + Pairs</option>
    </select></label>
    <span id="mode-save-status" class="sub" style="font-size:11px;"></span>
  </div>
</div>

<!-- Bento Grid Layout 1-Halaman -->
<div class="bento-grid">
  
  <!-- Row 1: KPI Grid (Full 12 cols) -->
  <div class="bento-box col-12">
    <div class="kpi-row" id="kpi-grid"></div>
  </div>

  <!-- Row 2: Equity Curve (8 cols) + Per-Symbol Breakdown (4 cols) -->
  <div class="bento-box col-8">
    <div class="bento-title">Equity Curve &amp; Growth <span id="eq-hint"></span></div>
    <div class="chart-container"><canvas id="chart-equity"></canvas></div>
  </div>

  <div class="bento-box col-4">
    <div class="bento-title" style="display:flex; justify-content:space-between; align-items:center;">
      <span>Per-Symbol Performance</span>
      <select id="sort-sym" style="font-size:11px; padding:2px 4px; background:#1e1e1e; color:#ccc; border:1px solid #444; border-radius:3px; outline:none; cursor:pointer;" onchange="renderSym()">
        <option value="default">Default</option>
        <option value="az">A-Z</option>
        <option value="profit-desc">Profit Tertinggi</option>
        <option value="profit-asc">Profit Terendah</option>
      </select>
    </div>
    <div id="sym-cards" style="overflow-y: auto; max-height: 220px;"></div>
  </div>

  <!-- Row 3: Model Decision Distribution (6 cols) + Latency & LLM Accuracy (6 cols) -->
  <div class="bento-box col-6">
    <div class="bento-title">Model Decisions <span>OpenAI vs Gemini vs DeepSeek</span></div>
    <div class="chart-container-sm"><canvas id="chart-decisions"></canvas></div>
  </div>

  <div class="bento-box col-6">
    <div class="bento-title">Model Latency (detik) <span>Ronde 1 Evaluation</span></div>
    <div class="chart-container-sm"><canvas id="chart-latency"></canvas></div>
  </div>

  <!-- Row 4: LLM Model Accuracy Table (6 cols) + SL/TP & R:R Distribution (6 cols) -->
  <div class="bento-box col-6">
    <div class="bento-title">Model Accuracy &amp; Confidence Calibration</div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Model</th><th>N</th><th>BUY</th><th>SELL</th><th>HOLD</th><th>Akurasi</th><th>Avg Conf</th><th>Conf Win</th><th>Conf Loss</th></tr></thead>
        <tbody id="model-tbody"></tbody>
      </table>
    </div>
    <div class="sub" id="agree-line" style="margin-top:8px;"></div>
  </div>

  <div class="bento-box col-6">
    <div class="bento-title">SL/TP &amp; R:R Effectiveness</div>
    <div style="display: flex; gap: 10px;">
      <div style="flex:1;" class="chart-container-sm"><canvas id="chart-sl"></canvas></div>
      <div style="flex:1;" class="chart-container-sm"><canvas id="chart-rr"></canvas></div>
    </div>
    <div class="sub" id="sltp-line" style="margin-top:6px;"></div>
  </div>

  <!-- Row 5: Trade History (7 cols) + Post-Mortem Lessons (5 cols) -->
  <div class="bento-box col-7">
    <div class="bento-title">Riwayat Trade Terakhir</div>
    <div class="table-wrap">
      <table id="trades-table">
        <thead><tr><th>Ticket</th><th>Symbol</th><th>Side</th><th>Lot</th><th>Entry</th><th>SL</th><th>TP</th><th>P/L ($)</th><th>Waktu</th><th>Status</th></tr></thead>
        <tbody id="trades-tbody"></tbody>
      </table>
    </div>
  </div>

  <div class="bento-box col-5">
    <div class="bento-title">Bot Status &amp; Risk Engine</div>
    <div id="status-panel-div" style="overflow-y: auto; max-height: 280px;"></div>
  </div>

</div>

<!-- Unused hidden elements kept for script compatibility -->
<div style="display:none;">
  <canvas id="chart-conf"></canvas>
  <canvas id="chart-agg"></canvas>
</div>

<script>
"use strict";
let DATA = window.__INITIAL_DATA__ || null;
let CONFIG_DATA = null;
let LIVE = false;
const charts = {};
const $ = id => document.getElementById(id);

function fmtMoney(v) { return (v === null || v === undefined) ? "—" : (v>=0?"+":"") + "$" + v.toFixed(2); }
function fmtPct(v) { return (v === null || v === undefined) ? "—" : (v*100).toFixed(1) + "%"; }
function fmtTs(ts) { if (!ts) return ""; const d = new Date(ts*1000); return d.toLocaleString(); }
function esc(s) { return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;"); }

async function loadData() {
  try {
    const r = await fetch('/api/data', {cache:'no-store'});
    if (r.ok) { DATA = await r.json(); LIVE = true; }
  } catch (e) { /* static mode */ }
  if (!DATA) DATA = window.__INITIAL_DATA__ || {meta:{}, summary:{}, trades:[], equity_curve:[], model_stats:{}, per_symbol:{}, sl_buckets:{}, rr_buckets:{}, agreement:{}, latency:{}, position_manager:{}, sltp_floor:{}, forecast_bias:{}};
  await loadTradingMode();
  renderAll();
}

async function loadTradingMode() {
  const sel = $('f-trading-mode');
  if (!sel) return;
  let mode = null;
  try {
    const r = await fetch('/api/config', {cache:'no-store'});
    if (r.ok) {
      const res = await r.json();
      CONFIG_DATA = res.config || null;
      if (CONFIG_DATA) {
        mode = CONFIG_DATA.TRADING_MODE || null;
        const pairs = CONFIG_DATA.FX_PAIR_SYMBOLS || [];
        if (pairs.length && CONFIG_DATA.TRADING_MODE === 'xau_pairs') {
          sel.title = 'Pool: ' + (CONFIG_DATA.WEEKDAY_SYMBOL || 'XAU') + ' → ' + pairs.join(', ');
        }
      }
    }
  } catch (e) { /* static mode — keep default */ }
  if (mode && [...sel.options].some(o => o.value === mode)) sel.value = mode;
}

async function saveTradingMode() {
  const sel = $('f-trading-mode');
  const st = $('mode-save-status');
  if (!sel || !st) return;
  const mode = sel.value;
  st.textContent = 'menyimpan…';
  try {
    const r = await fetch('/api/config', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({TRADING_MODE: mode})
    });
    if (r.ok) {
      st.textContent = '✅ mode ' + (mode === 'xau_pairs' ? 'XAU + Pairs' : 'XAU Only') + ' tersimpan (restart bot untuk apply)';
      st.style.color = '#4ade80';
    } else {
      st.textContent = '⚠️ gagal simpan (HTTP ' + r.status + ') — mode ini aktif di bot setelah restart + config reload';
      st.style.color = '#f87171';
    }
  } catch (e) {
    st.textContent = '⚠️ dashboard static — mode hanya tampilan. Set TRADING_MODE di .env/config lalu restart bot.';
    st.style.color = '#f59e0b';
  }
}

function getFilteredTrades() {
  const sym = $('f-symbol').value;
  const range = $('f-range').value;
  const now = Date.now() / 1000;

  return (DATA.trades || []).filter(t => {
    if (sym && t.symbol !== sym) return false;
    if (range !== 'all') {
      const days = range === '7d' ? 7 : 30;
      if (t.ts && (now - t.ts) > days * 86400) return false;
    }
    return true;
  });
}

function renderSub() {
  const meta = DATA.meta || {};
  let s = "";
  if (meta.accounts && meta.accounts.length) s += 'Akun: <b>' + esc(meta.accounts.join(', ')) + '</b>';
  if (s) s += ' &nbsp;|&nbsp; ';
  s += 'Update: <b>' + esc(meta.generated_at || '') + '</b>';
  $('sub-line').innerHTML = s;

  if (LIVE) {
    $('live-badge-wrap').innerHTML = '<div class="badge-live"><div class="badge-dot"></div> LIVE (5s)</div>';
  } else {
    $('live-badge-wrap').innerHTML = '<div class="badge-live" style="background:rgba(204,122,92,0.1);color:var(--amber);border-color:rgba(204,122,92,0.2);">STATIC</div>';
  }
}

function renderFilters() {
  const symSel = $('f-symbol');
  const prevSym = symSel.value;
  symSel.innerHTML = '<option value="">Semua Simbol</option>';

  (DATA.meta.symbols || []).forEach(s => {
    const o = document.createElement('option');
    o.value = s;
    o.text = s;
    symSel.appendChild(o);
  });

  if (prevSym && [...symSel.options].some(o=>o.value===prevSym)) {
    symSel.value = prevSym;
  } else {
    symSel.value = '';
  }
}

function renderKpi() {
  const filteredTrades = getFilteredTrades();
  const closed = filteredTrades.filter(t => t.status === 'closed' && t.pnl !== null);
  const wins = closed.filter(t => t.pnl > 0.04);
  const losses = closed.filter(t => t.pnl < -0.04);
  const netPnl = closed.reduce((acc, t) => acc + t.pnl, 0);
  const grossWin = wins.reduce((acc, t) => acc + t.pnl, 0);
  const grossLoss = Math.abs(losses.reduce((acc, t) => acc + t.pnl, 0));
  const winRate = (wins.length + losses.length) > 0 ? wins.length / (wins.length + losses.length) : null;
  const pf = grossLoss > 0 ? grossWin / grossLoss : (grossWin > 0 ? grossWin : null);
  const expectancy = closed.length > 0 ? netPnl / closed.length : null;

  let peak = 1000.0, bal = 1000.0, maxDd = 0.0;
  closed.forEach(t => {
    bal += t.pnl;
    if (bal > peak) peak = bal;
    const dd = peak - bal;
    if (dd > maxDd) maxDd = dd;
  });

  const cards = [
    ['Net P/L', fmtMoney(netPnl), netPnl >= 0 ? 'green' : 'red'],
    ['Win Rate', fmtPct(winRate), ''],
    ['Profit Factor', pf != null ? pf.toFixed(2) : '—', ''],
    ['Expectancy', fmtMoney(expectancy), ''],
    ['Max Drawdown', fmtMoney(-maxDd), 'red'],
    ['Closed Trades', String(closed.length), ''],
    ['Open Positions', String(filteredTrades.filter(t => t.status === 'open').length), ''],
    ['Total Cycles', String(DATA.summary ? DATA.summary.total_cycles : 0), ''],
  ];
  $('kpi-grid').innerHTML = cards.map(([l,v,c]) =>
    `<div class="kpi-card"><div class="kpi-label">${esc(l)}</div><div class="kpi-value ${c}">${esc(v)}</div></div>`
  ).join('');
}

function renderSym() {
  const ps = DATA.per_symbol || {};
  const selectedSym = $('f-symbol').value;
  let keys = Object.keys(ps).filter(k => !selectedSym || k === selectedSym);
  
  const sortMode = $('sort-sym') ? $('sort-sym').value : 'default';
  if (sortMode === 'az') {
    keys.sort();
  } else if (sortMode === 'profit-desc') {
    keys.sort((a, b) => (ps[b].pnl || 0) - (ps[a].pnl || 0));
  } else if (sortMode === 'profit-asc') {
    keys.sort((a, b) => (ps[a].pnl || 0) - (ps[b].pnl || 0));
  }
  
  $('sym-cards').innerHTML = keys.length ? keys.map(sym => {
    const st = ps[sym];
    return `<div class="sym-card"><div class="sym-name">${esc(sym)}</div>` +
      `<div><b>${st.n} Trade</b>: ${st.win}W-${st.loss}L (WR ${fmtPct(st.win_rate)})</div>` +
      `<div style="margin-top:2px;">P/L: <b class="${(st.pnl||0)>=0?'green':'red'}">${fmtMoney(st.pnl)}</b></div></div>`;
  }).join('') : '<div class="muted empty-hint">Belum ada trade tertutup.</div>';
}

function renderModelTable() {
  const ms = DATA.model_stats || {};
  const order = ['OpenAI','Gemini','Claude','DeepSeek'];
  const rows = order.filter(m => ms[m]).map(m => {
    const st = ms[m];
    return `<tr><td><b>${esc(m)}</b></td><td>${st.n}</td><td>${st.BUY}</td><td>${st.SELL}</td><td>${st.HOLD}</td>` +
      `<td><b class="${(st.acc||0)>=0.5?'green':'red'}">${fmtPct(st.acc)}</b></td><td>${fmtPct(st.avg_conf)}</td><td>${fmtPct(st.avg_conf_win)}</td><td>${fmtPct(st.avg_conf_loss)}</td></tr>`;
  }).join('');
  $('model-tbody').innerHTML = rows || '<tr><td colspan="9" class="muted">Belum ada data model.</td></tr>';

  const ag = DATA.agreement || {};
  const s = DATA.summary || {};
  $('agree-line').innerHTML =
    `Agreement: ${ag.cycles||0} cycle — ≥2 searah: ${ag.ge2||0} (${fmtPct(ag.cycles?ag.ge2/ag.cycles:null)}), ` +
    `3/3: ${ag.all3||0}, split: ${ag.split||0}. Konsensus OK: ${s.consensus_approved||0} / Fail: ${s.consensus_failed||0}.`;
}

function renderSltp() {
  const pm = DATA.position_manager || {};
  const fl = DATA.sltp_floor || {};
  $('sltp-line').innerHTML =
    `BEP: ${pm.break_even||0}× | Trailing: ${pm.trailing||0}× | Partial: ${pm.partial_close||0}× | SL Floor OK: ${fl.above_floor||0}`;
}

function renderStatusPanel() {
  const div = $('status-panel-div');
  if (!div) return;

  const dyn = DATA.dynamic_rules || {};
  const risk = DATA.risk_state || {};
  
  // Status dari Live API
  let isPaused = CONFIG_DATA ? CONFIG_DATA.TRADING_PAUSED : false;
  let isDry = CONFIG_DATA ? CONFIG_DATA.DRY_RUN : true; // default true for safety in static
  let mode = CONFIG_DATA ? CONFIG_DATA.TRADING_MODE : "xau";
  let oaiModel = CONFIG_DATA ? CONFIG_DATA.OPENAI_MODEL : "gpt-5.4-mini";
  let gemModel = CONFIG_DATA ? CONFIG_DATA.GEMINI_MODEL : "gemini-3.1-flash-lite";
  let cldModel = CONFIG_DATA ? CONFIG_DATA.CLAUDE_MODEL : "deepseek/deepseek-v4-flash";

  let connectionStatus = LIVE ? '<span class="green" style="font-weight: 700;">● CONNECTED (LIVE)</span>' : '<span class="muted" style="font-weight: 700;">○ STATIC MODE (Offline)</span>';

  let html = `
    <div style="margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border);">
      <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
        <span>API Connection:</span>
        <b>${connectionStatus}</b>
      </div>
      <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
        <span>Trading Status:</span>
        <b class="${isPaused ? 'red' : 'green'}">${isPaused ? '🛑 PAUSED' : '🟢 ACTIVE'}</b>
      </div>
      <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
        <span>Execution Mode:</span>
        <b class="${isDry ? 'muted' : 'red'}">${isDry ? '🔍 DRY RUN (Simulated)' : '⚠️ LIVE TRADING (Real Money!)'}</b>
      </div>
      <div style="display:flex; justify-content:space-between;">
        <span>Rotation Mode:</span>
        <b style="color:var(--amber);">${mode === 'xau_pairs' ? '🔄 XAU + FX Pairs' : '🎯 XAUUSD Only'}</b>
      </div>
    </div>

    <div style="margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border);">
      <div style="font-weight: 600; color: var(--muted-light); margin-bottom: 6px; text-transform: uppercase; font-size: 10px;">🛡️ Risk Engine & self-Tuning</div>
      <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
        <span>Recovery Mode:</span>
        <b class="${risk.recovery_mode ? 'red' : 'muted'}">${risk.recovery_mode ? '🚨 ACTIVE' : 'NORMAL'}</b>
      </div>
      <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
        <span>Consecutive Losses:</span>
        <b class="${(risk.consecutive_losses || 0) > 0 ? 'red' : ''}">${risk.consecutive_losses || 0} / 3</b>
      </div>
      <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
        <span>Required Consensus:</span>
        <b>${dyn.consensus_threshold || 2} / 3 Models</b>
      </div>
      <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
        <span>ATR Multiplier (SL/TP):</span>
        <b>${(dyn.sl_multiplier || 1.5).toFixed(2)}x / ${(dyn.tp_multiplier || 3.0).toFixed(2)}x</b>
      </div>
      <div style="display:flex; justify-content:space-between; font-size:10px;">
        <span>Tuning Status:</span>
        <span style="color:var(--muted-light);">${esc(dyn.status_message || '—')}</span>
      </div>
    </div>

    <div>
      <div style="font-weight: 600; color: var(--muted-light); margin-bottom: 6px; text-transform: uppercase; font-size: 10px;">🤖 Active AI Models & Scheduling</div>
      <div style="margin-bottom:6px; font-size:10px; color:var(--muted); line-height: 1.5;">
        Slot 1 (OpenAI): <b>${esc(oaiModel)}</b><br>
        Slot 2 (Gemini): <b>${esc(gemModel)}</b><br>
        Slot 3 (Claude Slot): <b>${esc(cldModel)}</b>
      </div>
      <div style="font-size:10px; line-height: 1.4; background: rgba(255,255,255,0.01); padding: 6px; border-radius: 4px; border: 1px solid var(--border);">
        <b>WIB Time-based AI Mode:</b><br>
        • 00:01-08:59: <span style="color:var(--muted-light);">Single (OpenAI)</span><br>
        • 09:00-13:00: <span style="color:var(--muted-light);">Dual (OpenAI+DeepSeek)</span><br>
        • 13:01-19:29: <span style="color:var(--muted-light);">Single</span><br>
        • 19:30-21:30: <span style="color:var(--amber);">Triple (London-NY Overlap)</span><br>
        • 21:31-23:59: <span style="color:var(--muted-light);">Single</span>
      </div>
    </div>
  `;
  div.innerHTML = html;
}

function renderTrades() {
  const trades = getFilteredTrades();
  trades.sort((a, b) => {
    if (a.status === 'open' && b.status !== 'open') return -1;
    if (a.status !== 'open' && b.status === 'open') return 1;
    return (b.ts || 0) - (a.ts || 0);
  });
  $('trades-tbody').innerHTML = trades.map(t =>
    `<tr data-era="${esc(t.era||'')}" data-symbol="${esc(t.symbol)}" data-ts="${t.ts||0}">` +
    `<td>${t.ticket||'—'}</td><td><b style="color:var(--amber);">${esc(t.symbol)}</b></td>` +
    `<td><b class="${t.side==='BUY'?'green':'red'}">${t.side}</b></td><td>${t.lot||'—'}</td>` +
    `<td>${t.entry||'—'}</td><td>${t.sl||'—'}</td><td>${t.tp||'—'}</td>` +
    `<td class="${t.pnl>0?'green':t.pnl<0?'red':''}"><b>${fmtMoney(t.pnl)}</b></td>` +
    `<td>${fmtTs(t.ts)}</td><td><span class="theme-tag" style="${t.status==='open'?'background:var(--green-bg);color:var(--green);border:1px solid rgba(34,197,94,0.3);':''}">${t.status}</span></td></tr>`
  ).join('') || '<tr><td colspan="10" class="muted empty-hint">Tidak ada trade sesuai filter.</td></tr>';
}

function mkChart(id, cfg) {
  const el = $(id);
  if (!el) return;
  if (charts[id]) { charts[id].destroy(); delete charts[id]; }
  charts[id] = new Chart(el, cfg);
}

function renderCharts() {
  Chart.defaults.color = '#8a8a85';
  Chart.defaults.borderColor = '#2d2d2b';
  Chart.defaults.font.family = "'Inter', sans-serif";

  const trades = getFilteredTrades().filter(t => t.status === 'closed' && t.pnl !== null);
  let bal = 1000.0;
  const eqData = trades.map(t => {
    bal += t.pnl;
    return { ts: t.ts, balance: bal };
  });

  if (eqData.length) {
    $('eq-hint').textContent = '';
    mkChart('chart-equity', {
      type:'line',
      data:{ labels: eqData.map(p => fmtTs(p.ts)), datasets:[{ label:'Balance ($)', data: eqData.map(p=>p.balance), borderColor:'#cc7a5c', backgroundColor:'rgba(204, 122, 92, 0.04)', fill:true, tension:.3, pointRadius:3 }] },
      options:{ responsive:true, maintainAspectRatio:false, plugins:{ legend:{display:false} }, scales:{ y:{ ticks:{ callback:v=>'$'+v.toFixed(0) } } } }
    });
  } else {
    if (charts['chart-equity']) { charts['chart-equity'].destroy(); delete charts['chart-equity']; }
    $('eq-hint').textContent = '— belum ada trade P/L tertutup';
  }

  const models = Object.keys(DATA.model_stats||{});
  mkChart('chart-decisions', {
    type:'bar',
    data:{ labels: models, datasets:[
      {label:'BUY', data:models.map(m=>DATA.model_stats[m].BUY), backgroundColor:'#4ade80'},
      {label:'SELL', data:models.map(m=>DATA.model_stats[m].SELL), backgroundColor:'#f87171'},
      {label:'HOLD', data:models.map(m=>DATA.model_stats[m].HOLD), backgroundColor:'#737373'}
    ]},
    options:{ responsive:true, maintainAspectRatio:false, scales:{ x:{stacked:true}, y:{stacked:true} } }
  });

  const latModels = Object.keys(DATA.latency||{});
  mkChart('chart-latency', {
    type:'bar',
    data:{ labels: latModels, datasets:[{ label:'Avg Latency (s)', data:latModels.map(m=>DATA.latency[m].avg), backgroundColor:'#8a8a85', borderRadius:4 }] },
    options:{ responsive:true, maintainAspectRatio:false, plugins:{ legend:{display:false} } }
  });

  const slKeys = Object.keys(DATA.sl_buckets||{});
  mkChart('chart-sl', {
    type:'bar',
    data:{ labels: slKeys, datasets:[{ label:'SL Points', data:slKeys.map(k=>DATA.sl_buckets[k].n), backgroundColor:'#8a8a85', borderRadius:4 }] },
    options:{ responsive:true, maintainAspectRatio:false, plugins:{ legend:{display:false} } }
  });

  const rrKeys = Object.keys(DATA.rr_buckets||{});
  mkChart('chart-rr', {
    type:'bar',
    data:{ labels: rrKeys, datasets:[{ label:'R:R Ratio', data:rrKeys.map(k=>DATA.rr_buckets[k]), backgroundColor:'#cc7a5c', borderRadius:4 }] },
    options:{ responsive:true, maintainAspectRatio:false, plugins:{ legend:{display:false} } }
  });
}

function renderAll() {
  renderSub();
  renderKpi();
  renderSym();
  renderModelTable();
  renderSltp();
  renderStatusPanel();
  renderCharts();
  renderTrades();
}

function initDashboard() {
  renderSub();
  renderFilters();
  renderAll();
}

['f-symbol','f-range'].forEach(id => $(id).addEventListener('change', renderAll));
const _modeSel = $('f-trading-mode');
if (_modeSel) _modeSel.addEventListener('change', saveTradingMode);

document.querySelectorAll('#trades-table th').forEach(th => {
  th.addEventListener('click', () => {
    const idx = Array.from(th.parentNode.children).indexOf(th);
    const tbody = $('trades-tbody');
    const rows = Array.from(tbody.rows);
    rows.sort((a,b) => {
      const av = a.cells[idx].textContent, bv = b.cells[idx].textContent;
      const an = parseFloat(av.replace(/[$+,—]/g,'')), bn = parseFloat(bv.replace(/[$+,—]/g,''));
      const isNum = !isNaN(an) && !isNaN(bn);
      return isNum ? an-bn : av.localeCompare(bv);
    });
    rows.forEach(r => tbody.appendChild(r));
  });
});

loadData().then(initDashboard);
if (location.protocol === 'http:' || location.protocol === 'https:') {
  setInterval(async () => { await loadData(); renderAll(); }, 5000);
}
</script>
</body>
</html>
"""
