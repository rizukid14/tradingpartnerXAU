"""
Dashboard Assets & Modern HTML Template for 2-Stage Quant Funnel Trading Bot.
Features:
- Live 22-Pair SMC Radar Matrix
- 2-Pass Cross-Examination Jury & Risk Veto Stream
- Funnel Conversion KPIs (Radar -> Pass 1 -> Pass 2 Veto -> MT5 Dispatch)
- Live MT5 Portfolio & Pending Orders Table
- Dark Obsidian & Glassmorphism Theme (Inter + JetBrains Mono)
"""

TEMPLATE = r"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>2-Stage Quant Funnel & 3-LLM Jury Operations Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root {
  --bg: #07090e;
  --surface: #0e131f;
  --surface-elevated: #141b2d;
  --card: #121829;
  --card-hover: #18223a;
  --border: rgba(255, 255, 255, 0.07);
  --border-strong: rgba(255, 255, 255, 0.14);
  
  --text: #f1f5f9;
  --text-muted: #94a3b8;
  --text-dim: #64748b;
  
  --green: #10b981;
  --green-dim: rgba(16, 185, 129, 0.12);
  --cyan: #06b6d4;
  --cyan-dim: rgba(6, 182, 212, 0.12);
  --rose: #f43f5e;
  --rose-dim: rgba(244, 63, 94, 0.12);
  --amber: #f59e0b;
  --amber-dim: rgba(245, 158, 11, 0.12);
  --purple: #a855f7;
  --purple-dim: rgba(168, 85, 247, 0.12);
  --blue: #3b82f6;
  --blue-dim: rgba(59, 130, 246, 0.12);
  
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 14px;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-sans);
  padding: 20px;
  min-height: 100vh;
  font-size: 13px;
  line-height: 1.5;
}

/* Header */
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
  gap: 12px;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.brand-pill {
  background: linear-gradient(135deg, var(--green), var(--cyan));
  color: #000;
  font-family: var(--font-mono);
  font-weight: 800;
  font-size: 11px;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
}
.header-title {
  font-size: 18px;
  font-weight: 800;
  letter-spacing: -0.3px;
}
.header-sub {
  font-size: 12px;
  color: var(--text-muted);
}
.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
  font-family: var(--font-mono);
  font-size: 12px;
}
.badge-live {
  background: var(--green-dim);
  color: var(--green);
  border: 1px solid rgba(16, 185, 129, 0.3);
  padding: 4px 10px;
  border-radius: 999px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
}
.badge-live::before {
  content: '';
  width: 7px;
  height: 7px;
  background: var(--green);
  border-radius: 50%;
  box-shadow: 0 0 8px var(--green);
}

/* KPI Banner */
.grid-kpi {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}
.kpi-box {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 14px 16px;
}
.kpi-lbl {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}
.kpi-val {
  font-size: 20px;
  font-weight: 800;
  font-family: var(--font-mono);
  line-height: 1.1;
  margin-bottom: 4px;
}
.kpi-sub {
  font-size: 11.5px;
  color: var(--text-muted);
}

/* Bento Grid */
.bento-grid {
  display: grid;
  grid-template-columns: 7fr 5fr;
  gap: 16px;
  margin-bottom: 20px;
}
.bento-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 18px 20px;
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}
.card-title {
  font-size: 13.5px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Tables */
.table-wrap {
  overflow-x: auto;
  max-height: 400px;
  border-radius: var(--radius-sm);
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  text-align: left;
}
th {
  background: var(--surface-elevated);
  color: var(--text-dim);
  font-weight: 600;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 2;
}
td {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  color: var(--text-muted);
}
tr:last-child td { border-bottom: none; }
tr:hover td { background: rgba(255, 255, 255, 0.02); color: var(--text); }
.mono { font-family: var(--font-mono); }

/* Badges */
.tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  font-size: 10.5px;
  font-weight: 600;
  font-family: var(--font-mono);
}
.tag-green { background: var(--green-dim); color: var(--green); border: 1px solid rgba(16, 185, 129, 0.25); }
.tag-cyan { background: var(--cyan-dim); color: var(--cyan); border: 1px solid rgba(6, 182, 212, 0.25); }
.tag-rose { background: var(--rose-dim); color: var(--rose); border: 1px solid rgba(244, 63, 94, 0.25); }
.tag-amber { background: var(--amber-dim); color: var(--amber); border: 1px solid rgba(245, 158, 11, 0.25); }
.tag-purple { background: var(--purple-dim); color: var(--purple); border: 1px solid rgba(168, 85, 247, 0.25); }

/* Jury Feed Cards */
.jury-feed {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 440px;
  overflow-y: auto;
  padding-right: 4px;
}
.jury-item {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.jury-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
}
.jury-models {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
}
.jury-reason {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.4;
}

@media (max-width: 1200px) {
  .grid-kpi { grid-template-columns: repeat(3, 1fr); }
  .bento-grid { grid-template-columns: 1fr; }
}
</style>
</head>
<body>

  <!-- Header -->
  <div class="header">
    <div class="header-left">
      <span class="brand-pill">2-STAGE FUNNEL</span>
      <div>
        <h1 class="header-title">Trading Operations Center</h1>
        <div class="header-sub">22-Pair SMC Fast Radar &bull; 2-Pass Cross-Examination Jury &bull; MT5 Live</div>
      </div>
    </div>
    <div class="header-right">
      <div class="badge-live" id="statusPill">LIVE CONNECTED</div>
      <div style="color: var(--text-dim);" id="clockWib">00:00:00 WIB</div>
    </div>
  </div>

  <!-- KPI Banner -->
  <div class="grid-kpi">
    <div class="kpi-box">
      <div class="kpi-lbl">Balance / Equity</div>
      <div class="kpi-val" id="kpiBalance">$0.00</div>
      <div class="kpi-sub" id="kpiEquity">Eq: $0.00</div>
    </div>
    <div class="kpi-box">
      <div class="kpi-lbl">Today P/L (Realized)</div>
      <div class="kpi-val" id="kpiPnlToday">$0.00</div>
      <div class="kpi-sub" id="kpiPnlPct">0.0% of target</div>
    </div>
    <div class="kpi-box">
      <div class="kpi-lbl">Floating P/L</div>
      <div class="kpi-val" id="kpiFloating">$0.00</div>
      <div class="kpi-sub" id="kpiActivePositions">0 Open Positions</div>
    </div>
    <div class="kpi-box">
      <div class="kpi-lbl">Stage 1 Radar Detections</div>
      <div class="kpi-val mono" style="color: var(--cyan);" id="kpiStage1">0</div>
      <div class="kpi-sub">A+ Trigger Candidates</div>
    </div>
    <div class="kpi-box">
      <div class="kpi-lbl">Pass 2 Veto Shield</div>
      <div class="kpi-val mono" style="color: var(--rose);" id="kpiVetoed">0</div>
      <div class="kpi-sub" id="kpiVetoRate">0.0% Vetoed (Saved)</div>
    </div>
    <div class="kpi-box">
      <div class="kpi-lbl">MT5 Executed Trades</div>
      <div class="kpi-val mono" style="color: var(--green);" id="kpiExecuted">0</div>
      <div class="kpi-sub" id="kpiPendingCount">0 Pending Orders</div>
    </div>
  </div>

  <!-- Bento Grid 1: Radar Matrix & Live Positions -->
  <div class="bento-grid">
    <!-- 22-Pair SMC Radar Matrix -->
    <div class="bento-card">
      <div class="card-head">
        <div class="card-title">📡 22-Pair SMC Fast Radar Matrix (Live Layer)</div>
        <div class="tag tag-cyan">60s Polling</div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Pair</th>
              <th>Compass</th>
              <th>Dealing Range (H1)</th>
              <th>Nearest OB / FVG</th>
              <th>ATR / Spread</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody id="radarTableBody">
            <tr><td colspan="6" style="text-align: center; padding: 24px;">Memuat data radar...</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Active Positions & Pending Limit Queue -->
    <div class="bento-card">
      <div class="card-head">
        <div class="card-title">💼 Active Positions & Pending Orders</div>
        <div class="tag tag-green" id="posCapacityBadge">0/6 Slots</div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Ticket</th>
              <th>Pair</th>
              <th>Type</th>
              <th>Lot</th>
              <th>Entry</th>
              <th>SL / TP</th>
              <th>P/L ($)</th>
            </tr>
          </thead>
          <tbody id="positionsTableBody">
            <tr><td colspan="7" style="text-align: center; padding: 24px;">Tidak ada posisi terbuka.</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Bento Grid 2: 2-Pass Jury Live Feed & Equity Chart -->
  <div class="bento-grid">
    <!-- 2-Pass Jury Verdict Stream -->
    <div class="bento-card">
      <div class="card-head">
        <div class="card-title">⚖️ 2-Pass AI Jury Decisions & Risk Veto Stream</div>
        <div class="tag tag-purple">Sequential Audit</div>
      </div>
      <div class="jury-feed" id="juryFeedBody">
        <div style="text-align: center; padding: 24px; color: var(--text-dim);">Belum ada sesi sidang konsensus baru.</div>
      </div>
    </div>

    <!-- Daily Performance & Funnel Chart -->
    <div class="bento-card">
      <div class="card-head">
        <div class="card-title">📈 Daily Equity & Funnel Conversion</div>
        <div class="tag tag-amber">Performance</div>
      </div>
      <div style="height: 380px; position: relative;">
        <canvas id="perfChart"></canvas>
      </div>
    </div>
  </div>

  <script>
    let perfChart = null;

    function renderDashboard(data) {
      if (!data) return;

      // Clock & Status
      document.getElementById('clockWib').textContent = data.clock_wib || new Date().toLocaleTimeString('id-ID');
      
      // KPIs
      const acc = data.account || {};
      document.getElementById('kpiBalance').textContent = '$' + (acc.balance || 0).toFixed(2);
      document.getElementById('kpiEquity').textContent = 'Eq: $' + (acc.equity || 0).toFixed(2);
      
      const pnl = data.daily_pnl || 0;
      const pnlEl = document.getElementById('kpiPnlToday');
      pnlEl.textContent = (pnl >= 0 ? '+$' : '-$') + Math.abs(pnl).toFixed(2);
      pnlEl.style.color = pnl > 0.04 ? 'var(--green)' : (pnl < -0.04 ? 'var(--rose)' : 'var(--text)');
      
      const fl = data.floating_pnl || 0;
      const flEl = document.getElementById('kpiFloating');
      flEl.textContent = (fl >= 0 ? '+$' : '-$') + Math.abs(fl).toFixed(2);
      flEl.style.color = fl > 0.04 ? 'var(--green)' : (fl < -0.04 ? 'var(--rose)' : 'var(--text)');

      const openPos = data.open_positions || [];
      const pendingOrd = data.pending_orders || [];
      document.getElementById('kpiActivePositions').textContent = `${openPos.length} Open Pos (${pendingOrd.length} Pending)`;
      document.getElementById('posCapacityBadge').textContent = `${openPos.length + pendingOrd.length}/${data.max_positions || 6} Slots`;

      // Funnel KPIs
      const f = data.funnel || {};
      document.getElementById('kpiStage1').textContent = f.stage1_detected || 0;
      document.getElementById('kpiVetoed').textContent = f.pass2_vetoed || 0;
      document.getElementById('kpiExecuted').textContent = f.executed || 0;
      document.getElementById('kpiVetoRate').textContent = `${(f.veto_rate_pct || 0).toFixed(1)}% Veto Rate`;
      document.getElementById('kpiPendingCount').textContent = `${pendingOrd.length} Orders in Queue`;

      // Radar Table
      const radarBody = document.getElementById('radarTableBody');
      const radar = data.radar_pairs || [];
      if (radar.length > 0) {
        radarBody.innerHTML = radar.map(r => {
          const compClass = r.compass === 'BULLISH' ? 'tag-green' : (r.compass === 'BEARISH' ? 'tag-rose' : 'tag-amber');
          const rangeTag = r.range_pos <= 0.38 ? '<span class="tag tag-green">DISCOUNT</span>' : (r.range_pos >= 0.62 ? '<span class="tag tag-rose">PREMIUM</span>' : '<span class="tag tag-cyan">EQ</span>');
          return `
            <tr>
              <td><strong class="mono" style="color: var(--text);">${r.symbol}</strong></td>
              <td><span class="tag ${compClass}">${r.compass}</span></td>
              <td>${(r.range_pos * 100).toFixed(1)}% ${rangeTag}</td>
              <td class="mono" style="font-size: 11px;">${r.ob_zone || '-'}</td>
              <td class="mono">${r.atr_pts} / ${r.spread_pts} pts</td>
              <td><span class="tag tag-cyan">${r.status || 'WATCH'}</span></td>
            </tr>
          `;
        }).join('');
      }

      // Positions Table
      const posBody = document.getElementById('positionsTableBody');
      const allActive = [...openPos, ...pendingOrd];
      if (allActive.length > 0) {
        posBody.innerHTML = allActive.map(p => {
          const isPending = !!p.type_str && p.type_str.includes('LIMIT');
          const pnlVal = p.profit || 0;
          const pnlColor = pnlVal > 0.04 ? 'var(--green)' : (pnlVal < -0.04 ? 'var(--rose)' : 'var(--text-muted)');
          return `
            <tr>
              <td class="mono">#${p.ticket}</td>
              <td><strong class="mono">${p.symbol}</strong></td>
              <td><span class="tag ${isPending ? 'tag-amber' : (p.type_str === 'BUY' ? 'tag-green' : 'tag-rose')}">${p.type_str}</span></td>
              <td class="mono">${p.volume}</td>
              <td class="mono">${p.price_open}</td>
              <td class="mono">${p.sl || '-'} / ${p.tp || '-'}</td>
              <td class="mono" style="color: ${pnlColor}; font-weight: 700;">${isPending ? 'PENDING' : (pnlVal >= 0 ? '+$' : '-$') + Math.abs(pnlVal).toFixed(2)}</td>
            </tr>
          `;
        }).join('');
      } else {
        posBody.innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 24px; color: var(--text-dim);">Tidak ada posisi aktif atau antrian pending order.</td></tr>';
      }

      // Jury Feed
      const juryBody = document.getElementById('juryFeedBody');
      const juryEvents = data.jury_events || [];
      if (juryEvents.length > 0) {
        juryBody.innerHTML = juryEvents.map(j => {
          const vClass = j.verdict === 'APPROVE' ? 'tag-green' : (j.verdict === 'REVISE' ? 'tag-amber' : 'tag-rose');
          return `
            <div class="jury-item">
              <div class="jury-top">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span class="tag ${vClass}">${j.verdict}</span>
                  <strong class="mono">${j.symbol}</strong>
                  <span style="color: var(--text-dim); font-size: 11px;">${j.setup}</span>
                </div>
                <span class="mono" style="color: var(--text-dim); font-size: 11px;">${j.time}</span>
              </div>
              <div class="jury-models">
                ${(j.models || []).map(m => `<span class="tag tag-cyan">${m.name}: ${m.signal} (${(m.conf*100).toFixed(0)}%)</span>`).join('')}
              </div>
              <div class="jury-reason">${j.reason || 'Tidak ada catatan.'}</div>
            </div>
          `;
        }).join('');
      }

      // Performance Chart
      renderPerfChart(data.chart_data || {});
    }

    function renderPerfChart(chartData) {
      const ctx = document.getElementById('perfChart').getContext('2d');
      if (perfChart) {
        perfChart.data.labels = chartData.labels || [];
        perfChart.data.datasets[0].data = chartData.equity || [];
        perfChart.update();
        return;
      }
      perfChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels: chartData.labels || ['08:00', '10:00', '12:00', '14:00', '16:00', '18:00'],
          datasets: [{
            label: 'Portfolio Equity ($)',
            data: chartData.equity || [6000, 6010, 6005, 6025, 6048, 6050],
            borderColor: '#10b981',
            backgroundColor: 'rgba(16, 185, 129, 0.08)',
            fill: true,
            tension: 0.3,
            borderWidth: 2,
            pointRadius: 3
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 } } },
            y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 } } }
          }
        }
      });
    }

    // Auto Polling via /api/data or Initial State
    if (window.__INITIAL_DATA__) {
      renderDashboard(window.__INITIAL_DATA__);
    }

    setInterval(() => {
      fetch('/api/data')
        .then(res => res.json())
        .then(data => renderDashboard(data))
        .catch(() => {});
    }, 3000);
  </script>
</body>
</html>
"""
