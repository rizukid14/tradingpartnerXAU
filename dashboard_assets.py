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
<title>Trading Bot Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root { --bg:#0d1117; --card:#161b22; --border:#30363d; --text:#e6edf3; --muted:#8b949e; --green:#3fb950; --red:#f85149; --blue:#58a6ff; }
* { box-sizing:border-box; margin:0; padding:0; }
body { background:var(--bg); color:var(--text); font-family:Segoe UI,Roboto,Arial,sans-serif; padding:20px; }
h1 { font-size:22px; margin-bottom:4px; }
.sub { color:var(--muted); font-size:13px; margin-bottom:16px; }
.filters { display:flex; gap:12px; margin:12px 0 20px; flex-wrap:wrap; align-items:center; }
.filters label { font-size:13px; color:var(--muted); }
.filters select { background:var(--card); color:var(--text); border:1px solid var(--border); padding:5px 8px; border-radius:6px; }
.kpi-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:12px; margin-bottom:24px; }
.kpi { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:14px; }
.kpi-label { font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.5px; }
.kpi-value { font-size:22px; font-weight:700; margin-top:4px; }
.green { color:var(--green); } .red { color:var(--red); }
.chart-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(380px,1fr)); gap:16px; margin-bottom:24px; }
.chart-card { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:16px; }
.chart-card h3 { font-size:14px; margin-bottom:12px; color:var(--muted); }
canvas { max-height:280px; }
section { margin-bottom:28px; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th, td { padding:7px 10px; text-align:left; border-bottom:1px solid var(--border); }
th { color:var(--muted); cursor:pointer; user-select:none; }
th:hover { color:var(--blue); }
tr:hover { background:#1c2128; }
.section-title { font-size:16px; font-weight:600; margin-bottom:10px; border-bottom:1px solid var(--border); padding-bottom:6px; }
.lesson { background:var(--card); border:1px solid var(--border); border-radius:8px; padding:8px 12px; margin-bottom:8px; font-size:13px; }
.theme { display:inline-block; background:#21262d; border-radius:4px; padding:1px 6px; font-size:11px; color:var(--muted); margin-right:6px; }
.sym { color:var(--blue); margin-right:6px; font-weight:600; }
.sym-card { background:var(--card); border:1px solid var(--border); border-radius:8px; padding:10px 14px; margin-bottom:8px; font-size:13px; }
.sym-name { font-weight:700; color:var(--blue); margin-bottom:2px; }
.muted { color:var(--muted); font-size:12px; }
.empty-hint { padding:20px; text-align:center; }
</style>
</head>
<body>
<h1>📊 Trading Bot Dashboard</h1>
<div class="sub" id="sub-line">Memuat…</div>

<div class="filters">
  <label>Era: <select id="f-era"></select></label>
  <label>Symbol: <select id="f-symbol"></select></label>
  <label>Rentang: <select id="f-range">
    <option value="all">Semua</option>
    <option value="7d">7 hari</option>
    <option value="30d">30 hari</option>
  </select></label>
</div>

<div class="kpi-grid" id="kpi-grid"></div>

<section>
  <div class="section-title">Equity Curve <span id="eq-hint" class="muted" style="font-size:12px;font-weight:normal;"></span></div>
  <div class="chart-card"><canvas id="chart-equity"></canvas></div>
</section>

<section>
  <div class="section-title">Per-Symbol Breakdown</div>
  <div id="sym-cards"></div>
</section>

<section>
  <div class="section-title">Kualitas Sinyal &amp; LLM</div>
  <div class="chart-grid">
    <div class="chart-card"><h3>Distribusi Keputusan per Model</h3><canvas id="chart-decisions"></canvas></div>
    <div class="chart-card"><h3>Kalibrasi Confidence (Win vs Loss)</h3><canvas id="chart-conf"></canvas></div>
    <div class="chart-card"><h3>Distribusi Keputusan Gabungan</h3><canvas id="chart-agg"></canvas></div>
    <div class="chart-card"><h3>Latensi Rata-rata per Model</h3><canvas id="chart-latency"></canvas></div>
  </div>
  <table>
    <thead><tr><th>Model</th><th>N</th><th>BUY</th><th>SELL</th><th>HOLD</th><th>Akurasi</th><th>Avg Conf</th><th>Conf Win</th><th>Conf Loss</th></tr></thead>
    <tbody id="model-tbody"></tbody>
  </table>
  <div class="muted" id="agree-line" style="margin-top:10px;"></div>
</section>

<section>
  <div class="section-title">SL/TP Effectiveness</div>
  <div class="chart-grid">
    <div class="chart-card"><h3>Distribusi Jarak SL</h3><canvas id="chart-sl"></canvas></div>
    <div class="chart-card"><h3>Distribusi R:R (TP/SL)</h3><canvas id="chart-rr"></canvas></div>
  </div>
  <div class="muted" id="sltp-line"></div>
</section>

<section>
  <div class="section-title">Riwayat Trade</div>
  <div style="overflow-x:auto; max-height:480px; overflow-y:auto;">
    <table id="trades-table">
      <thead><tr><th>Ticket</th><th>Symbol</th><th>Side</th><th>Lot</th><th>Entry</th><th>SL</th><th>TP</th><th>P/L</th><th>Waktu</th><th>Status</th></tr></thead>
      <tbody id="trades-tbody"></tbody>
    </table>
  </div>
</section>

<section>
  <div class="section-title">Lessons &amp; Post-Mortem</div>
  <div id="lessons-div"></div>
</section>

<script>
"use strict";
let DATA = window.__INITIAL_DATA__ || null;
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
  if (!DATA) DATA = window.__INITIAL_DATA__ || {meta:{}, summary:{}, trades:[], equity_curve:[], model_stats:{}, per_symbol:{}, sl_buckets:{}, rr_buckets:{}, lessons:[], agreement:{}, latency:{}, position_manager:{}, sltp_floor:{}, forecast_bias:{}};
  renderAll();
}

function renderSub() {
  const meta = DATA.meta || {};
  let s = 'Era aktif: <b>' + esc(meta.active_era || '?') + '</b>';
  if (meta.accounts && meta.accounts.length) s += ' &nbsp;|&nbsp; Akun: ' + esc(meta.accounts.join(', '));
  s += ' &nbsp;|&nbsp; Data: ' + esc(fmtTs(meta.first_ts)) + ' → ' + esc(fmtTs(meta.last_ts));
  s += ' &nbsp;|&nbsp; Generated: ' + esc(meta.generated_at || '');
  if (LIVE) s += ' &nbsp;🟢 <span class="muted">live (auto-refresh 5 detik)</span>';
  $('sub-line').innerHTML = s;
}

function renderFilters() {
  const eraSel = $('f-era'), symSel = $('f-symbol');
  const prevEra = eraSel.value, prevSym = symSel.value;
  eraSel.innerHTML = ''; symSel.innerHTML = '';
  (DATA.meta.eras || []).forEach(e => { const o=document.createElement('option'); o.value=e; o.text=e; eraSel.appendChild(o); });
  (DATA.meta.symbols || []).forEach(s => { const o=document.createElement('option'); o.value=s; o.text=s; symSel.appendChild(o); });
  if (prevEra && [...eraSel.options].some(o=>o.value===prevEra)) eraSel.value = prevEra;
  else if (DATA.meta.active_era) eraSel.value = DATA.meta.active_era;
  if (prevSym && [...symSel.options].some(o=>o.value===prevSym)) symSel.value = prevSym;
}

function renderKpi() {
  const s = DATA.summary || {};
  const cards = [
    ['Net P/L', fmtMoney(s.net_pnl), (s.net_pnl||0)>=0?'green':'red'],
    ['Win Rate', fmtPct(s.win_rate), ''],
    ['Profit Factor', s.profit_factor!=null ? s.profit_factor.toFixed(2) : '—', ''],
    ['Expectancy', fmtMoney(s.expectancy), ''],
    ['Max Drawdown', fmtMoney(-(s.max_drawdown||0)), 'red'],
    ['Closed Trades', String(s.total_closed||0), ''],
    ['Open Positions', String(s.total_open||0), ''],
    ['Total Cycles', String(s.total_cycles||0), ''],
  ];
  $('kpi-grid').innerHTML = cards.map(([l,v,c]) =>
    `<div class="kpi"><div class="kpi-label">${esc(l)}</div><div class="kpi-value ${c}">${esc(v)}</div></div>`
  ).join('');
}

function renderSym() {
  const ps = DATA.per_symbol || {};
  const keys = Object.keys(ps);
  $('sym-cards').innerHTML = keys.length ? keys.map(sym => {
    const st = ps[sym];
    return `<div class="sym-card"><div class="sym-name">${esc(sym)}</div>` +
      `<div>${st.n}T ${st.win}W-${st.loss}L (WR ${fmtPct(st.win_rate)}) | P/L ${fmtMoney(st.pnl)}</div></div>`;
  }).join('') : '<div class="muted empty-hint">Belum ada trade tertutup.</div>';
}

function renderModelTable() {
  const ms = DATA.model_stats || {};
  const order = ['OpenAI','Gemini','Claude','DeepSeek'];
  const rows = order.filter(m => ms[m]).map(m => {
    const st = ms[m];
    return `<tr><td>${esc(m)}</td><td>${st.n}</td><td>${st.BUY}</td><td>${st.SELL}</td><td>${st.HOLD}</td>` +
      `<td>${fmtPct(st.acc)}</td><td>${fmtPct(st.avg_conf)}</td><td>${fmtPct(st.avg_conf_win)}</td><td>${fmtPct(st.avg_conf_loss)}</td></tr>`;
  }).join('');
  $('model-tbody').innerHTML = rows || '<tr><td colspan="9" class="muted">Belum ada data.</td></tr>';

  const ag = DATA.agreement || {};
  const s = DATA.summary || {};
  $('agree-line').innerHTML =
    `Agreement: ${ag.cycles||0} cycle berisi keputusan — ≥2 searah: ${ag.ge2||0} (${fmtPct(ag.cycles?ag.ge2/ag.cycles:null)}), ` +
    `3/3: ${ag.all3||0}, split: ${ag.split||0}. Konsensus approve: ${s.consensus_approved||0} / reject: ${s.consensus_failed||0}.`;
}

function renderSltp() {
  const pm = DATA.position_manager || {};
  const fl = DATA.sltp_floor || {};
  $('sltp-line').innerHTML =
    `Aktivasi: Break-even ${pm.break_even||0}×, Trailing ${pm.trailing||0}×, Partial close ${pm.partial_close||0}×. ` +
    `SL floor: ${fl.below_floor||0} di bawah / ${fl.above_floor||0} di atas / ${fl.unknown||0} tidak diketahui.`;
}

function renderLessons() {
  const ls = DATA.lessons || [];
  $('lessons-div').innerHTML = ls.length ? ls.map(l =>
    `<div class="lesson"><span class="theme">${esc(l.theme)}</span><span class="sym">${esc(l.symbol)}</span>${esc(l.lesson)}</div>`
  ).join('') : '<div class="muted empty-hint">Belum ada lesson.</div>';
}

function renderTrades() {
  const era = $('f-era').value, sym = $('f-symbol').value, range = $('f-range').value;
  const now = Date.now()/1000;
  const trades = (DATA.trades||[]).filter(t => {
    if (era && t.era !== era) return false;
    if (sym && t.symbol !== sym) return false;
    if (range !== 'all') { const days = range==='7d'?7:30; if (t.ts && (now-t.ts) > days*86400) return false; }
    return true;
  });
  $('trades-tbody').innerHTML = trades.map(t =>
    `<tr data-era="${esc(t.era||'')}" data-symbol="${esc(t.symbol)}" data-ts="${t.ts||0}">` +
    `<td>${t.ticket||'—'}</td><td>${esc(t.symbol)}</td><td>${t.side}</td><td>${t.lot||'—'}</td>` +
    `<td>${t.entry||'—'}</td><td>${t.sl||'—'}</td><td>${t.tp||'—'}</td>` +
    `<td class="${t.pnl>0?'green':t.pnl<0?'red':''}">${fmtMoney(t.pnl)}</td>` +
    `<td>${fmtTs(t.ts)}</td><td>${t.status}</td></tr>`
  ).join('') || '<tr><td colspan="10" class="muted">Tidak ada trade sesuai filter.</td></tr>';
}

function mkChart(id, cfg) {
  const el = $(id);
  if (!el) return;
  if (charts[id]) { charts[id].destroy(); delete charts[id]; }
  charts[id] = new Chart(el, cfg);
}

function renderCharts() {
  const eq = DATA.equity_curve || [];
  const eqWrap = $('chart-equity').closest('.chart-card');
  const oldHint = eqWrap.querySelector('.eq-empty'); if (oldHint) oldHint.remove();
  if (eq.length) {
    $('eq-hint').textContent = '';
    mkChart('chart-equity', {
      type:'line',
      data:{ labels: eq.map(p => fmtTs(p.ts)), datasets:[{ label:'Balance', data: eq.map(p=>p.balance), borderColor:'#58a6ff', backgroundColor:'rgba(88,166,255,.1)', fill:true, tension:.2 }] },
      options:{ plugins:{ legend:{display:false} }, scales:{ y:{ ticks:{ callback:v=>'$'+v.toFixed(0) } } } }
    });
  } else {
    if (charts['chart-equity']) { charts['chart-equity'].destroy(); delete charts['chart-equity']; }
    $('eq-hint').textContent = '— belum ada data P/L tertutup (muncul setelah post-mortem)';
    const d = document.createElement('div'); d.className='eq-empty muted empty-hint';
    d.textContent = 'Belum ada data P/L tertutup. Equity curve muncul setelah ada trade close dengan P/L.';
    eqWrap.appendChild(d);
  }

  const models = Object.keys(DATA.model_stats||{});
  mkChart('chart-decisions', {
    type:'bar',
    data:{ labels: models, datasets:[
      {label:'BUY', data:models.map(m=>DATA.model_stats[m].BUY), backgroundColor:'#3fb950'},
      {label:'SELL', data:models.map(m=>DATA.model_stats[m].SELL), backgroundColor:'#f85149'},
      {label:'HOLD', data:models.map(m=>DATA.model_stats[m].HOLD), backgroundColor:'#8b949e'}
    ]},
    options:{ scales:{ x:{stacked:true}, y:{stacked:true} } }
  });

  mkChart('chart-conf', {
    type:'bar',
    data:{ labels: models, datasets:[
      {label:'Avg Conf (menang)', data:models.map(m=>DATA.model_stats[m].avg_conf_win), backgroundColor:'#3fb950'},
      {label:'Avg Conf (kalah)', data:models.map(m=>DATA.model_stats[m].avg_conf_loss), backgroundColor:'#f85149'}
    ]},
    options:{ scales:{ y:{ max:1, ticks:{ callback:v=>(v*100).toFixed(0)+'%' } } } }
  });

  let agg = {BUY:0, SELL:0, HOLD:0};
  (DATA.trades||[]).forEach(t => { if (['BUY','SELL'].includes(t.side)) agg[t.side]++; });
  mkChart('chart-agg', {
    type:'doughnut',
    data:{ labels:['BUY','SELL','HOLD'], datasets:[{ data:[agg.BUY,agg.SELL,agg.HOLD], backgroundColor:['#3fb950','#f85149','#8b949e'] }] }
  });

  const latModels = Object.keys(DATA.latency||{});
  mkChart('chart-latency', {
    type:'bar',
    data:{ labels: latModels, datasets:[{ label:'Rata-rata (detik)', data:latModels.map(m=>DATA.latency[m].avg), backgroundColor:'#58a6ff' }] },
    options:{ plugins:{ legend:{display:false} } }
  });

  const slKeys = Object.keys(DATA.sl_buckets||{});
  mkChart('chart-sl', {
    type:'bar',
    data:{ labels: slKeys, datasets:[{ label:'Jumlah trade', data:slKeys.map(k=>DATA.sl_buckets[k].n), backgroundColor:'#58a6ff' }] },
    options:{ plugins:{ legend:{display:false} } }
  });

  const rrKeys = Object.keys(DATA.rr_buckets||{});
  mkChart('chart-rr', {
    type:'bar',
    data:{ labels: rrKeys, datasets:[{ label:'Jumlah', data:rrKeys.map(k=>DATA.rr_buckets[k]), backgroundColor:'#d29922' }] },
    options:{ plugins:{ legend:{display:false} } }
  });
}

function renderAll() {
  renderSub();
  renderFilters();
  renderKpi();
  renderSym();
  renderModelTable();
  renderSltp();
  renderLessons();
  renderCharts();
  renderTrades();
}

['f-era','f-symbol','f-range'].forEach(id => $(id).addEventListener('change', renderTrades));

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

loadData();
if (location.protocol === 'http:' || location.protocol === 'https:') {
  setInterval(async () => { await loadData(); }, 5000);
}
</script>
</body>
</html>
"""
