"""
dashboard_assets.py — Anti-UI-Slop Institutional Quant Decision Cockpit Assets.
Terminal-grade TradingView Lightweight Charts + 7-Gate X-Ray Surveillance + Proximity Radar.
"""

TEMPLATE = r"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Quant Decision Surveillance Cockpit | Institutional MT5 X-Ray</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<!-- TradingView Lightweight Charts v4.1.1 CDN -->
<script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
<style>
:root {
  --bg-base: #0b0e14;
  --bg-surface: #12161f;
  --bg-elevated: #1a202c;
  --bg-hover: #222938;
  --border: #1e2533;
  --border-strong: #2d3748;

  --text-main: #f1f5f9;
  --text-muted: #94a3b8;
  --text-dim: #64748b;

  --green: #00e676;
  --green-dim: rgba(0, 230, 118, 0.12);
  --red: #ff5252;
  --red-dim: rgba(255, 82, 82, 0.12);
  --amber: #ffd740;
  --amber-dim: rgba(255, 215, 64, 0.12);
  --cyan: #00e5ff;
  --cyan-dim: rgba(0, 229, 255, 0.12);
  --purple: #b388ff;
  --purple-dim: rgba(179, 136, 255, 0.12);

  --font-ui: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: 'JetBrains Mono', ui-monospace, monospace;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  height: 100%;
  width: 100%;
  background: var(--bg-base);
  color: var(--text-main);
  font-family: var(--font-ui);
  font-size: 12px;
  line-height: 1.35;
  overflow: hidden;
  -webkit-font-smoothing: antialiased;
}

/* TOP STATUS BAR (36px) */
.header-bar {
  height: 36px;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 14px;
  user-select: none;
}
.header-left, .header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}
.app-brand {
  font-weight: 700;
  font-size: 12px;
  letter-spacing: 0.5px;
  color: var(--cyan);
  display: flex;
  align-items: center;
  gap: 6px;
}
.heartbeat-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 6px var(--green);
}
.account-stat {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-mono);
  font-size: 11px;
}
.stat-label { color: var(--text-dim); text-transform: uppercase; font-size: 10px; font-family: var(--font-ui); font-weight: 600; }
.stat-val { color: var(--text-main); font-weight: 600; }
.stat-pnl-pos { color: var(--green); }
.stat-pnl-neg { color: var(--red); }
.clock-text {
  font-family: var(--font-mono);
  color: var(--text-muted);
  font-size: 11px;
}

/* MAIN WORKSPACE GRID */
.workspace {
  display: grid;
  grid-template-columns: 290px 1fr 330px;
  height: calc(100vh - 36px);
  width: 100vw;
}

/* LEFT SIDEBAR: PROXIMITY WATCHLIST */
.left-panel {
  background: var(--bg-surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.panel-header {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-surface);
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.panel-title {
  font-weight: 700;
  text-transform: uppercase;
  font-size: 10px;
  letter-spacing: 0.6px;
  color: var(--text-muted);
}
.search-input {
  width: 100%;
  background: var(--bg-base);
  border: 1px solid var(--border);
  color: var(--text-main);
  padding: 5px 8px;
  font-size: 11px;
  border-radius: 3px;
  outline: none;
  font-family: var(--font-mono);
  margin: 6px 10px;
  width: calc(100% - 20px);
}
.search-input:focus { border-color: var(--cyan); }
.filter-tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
  background: var(--bg-base);
}
.filter-tab {
  flex: 1;
  text-align: center;
  padding: 5px 2px;
  font-size: 9.5px;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--text-dim);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  user-select: none;
}
.filter-tab.active {
  color: var(--cyan);
  border-bottom-color: var(--cyan);
  background: var(--bg-surface);
}
.watchlist-scroll {
  flex: 1;
  overflow-y: auto;
}
.pair-row {
  display: grid;
  grid-template-columns: 78px 1fr 68px;
  padding: 7px 10px;
  border-bottom: 1px solid rgba(255,255,255,0.03);
  cursor: pointer;
  align-items: center;
  user-select: none;
  transition: background 0.1s ease;
}
.pair-row:hover { background: var(--bg-hover); }
.pair-row.selected {
  background: var(--bg-elevated);
  border-left: 3px solid var(--cyan);
}
.pair-symbol {
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 11.5px;
  color: var(--text-main);
}
.pair-setup-pill {
  font-size: 9px;
  font-weight: 700;
  padding: 1px 4px;
  border-radius: 2px;
  display: inline-block;
  font-family: var(--font-mono);
  text-transform: uppercase;
}
.setup-near { background: rgba(0, 230, 118, 0.18); color: var(--green); border: 1px solid var(--green); }
.setup-standby { background: rgba(255, 215, 64, 0.15); color: var(--amber); border: 1px solid var(--amber); }
.setup-idle { background: rgba(148, 163, 184, 0.1); color: var(--text-dim); }

.setup-pill-bull { background: rgba(0, 230, 118, 0.16); color: var(--green); border: 1px solid var(--green); }
.setup-pill-bear { background: rgba(255, 82, 82, 0.16); color: var(--red); border: 1px solid var(--red); }
.setup-pill-neutral { background: rgba(0, 229, 255, 0.14); color: var(--cyan); border: 1px solid var(--cyan); }
.setup-pill-amber { background: rgba(255, 215, 64, 0.14); color: var(--amber); border: 1px solid var(--amber); }
.setup-pill-idle { background: rgba(148, 163, 184, 0.1); color: var(--text-dim); border: 1px solid rgba(148, 163, 184, 0.2); }

.pair-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.pair-dist-text {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-muted);
}
.pair-dist-bold {
  font-weight: 700;
  color: var(--text-main);
}
.pair-right {
  text-align: right;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}
.tier-badge {
  font-size: 8.5px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 2px;
  font-family: var(--font-mono);
  text-transform: uppercase;
}
.tier-go { background: var(--green); color: #000; }
.tier-arm { background: var(--amber); color: #000; }
.tier-watch { background: #38bdf8; color: #000; }
.tier-lock { background: var(--red); color: #fff; }

.csm-badge {
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 600;
}
.csm-pos { color: var(--green); }
.csm-neg { color: var(--red); }

/* CENTER STAGE */
.center-panel {
  display: flex;
  flex-direction: column;
  background: var(--bg-base);
  overflow: hidden;
  border-right: 1px solid var(--border);
}
.pair-header-bar {
  padding: 8px 14px;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.pair-headline {
  display: flex;
  align-items: center;
  gap: 12px;
}
.pair-title-big {
  font-family: var(--font-mono);
  font-size: 16px;
  font-weight: 800;
  color: var(--text-main);
}
.tf-group {
  display: flex;
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: 3px;
  overflow: hidden;
}
.tf-btn {
  padding: 3px 8px;
  font-size: 10px;
  font-weight: 700;
  cursor: pointer;
  color: var(--text-muted);
  border: none;
  background: transparent;
  user-select: none;
}
.tf-btn.active {
  background: var(--cyan);
  color: #000;
}
.pair-metrics-strip {
  display: flex;
  align-items: center;
  gap: 14px;
  font-family: var(--font-mono);
  font-size: 11px;
}
.strip-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}
.strip-lbl {
  font-size: 8.5px;
  text-transform: uppercase;
  color: var(--text-dim);
  font-family: var(--font-ui);
  font-weight: 600;
}
.strip-val {
  font-weight: 700;
  color: var(--text-main);
}

/* FILTER STRIP BAR (High-Density Multi-Horizon Control) */
.filter-strip-bar {
  padding: 5px 14px;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 16px;
  user-select: none;
}
.filter-group {
  display: flex;
  align-items: center;
  gap: 8px;
}
.filter-strip-title {
  font-family: var(--font-ui);
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: var(--text-dim);
}
.strip-btn-group {
  display: flex;
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: 3px;
  overflow: hidden;
}
.strip-btn {
  padding: 3px 8px;
  font-size: 9.5px;
  font-weight: 700;
  font-family: var(--font-mono);
  cursor: pointer;
  color: var(--text-muted);
  border: none;
  background: transparent;
  user-select: none;
  transition: all 0.12s ease;
}
.strip-btn:hover {
  color: var(--text-main);
}
.strip-btn.active {
  background: var(--cyan);
  color: #000;
}
.filter-divider {
  width: 1px;
  height: 14px;
  background: var(--border-strong);
}

/* CHART CONTAINER */
.chart-wrapper {
  flex: 1;
  position: relative;
  width: 100%;
  height: 100%;
}
#tv-chart {
  width: 100%;
  height: 100%;
}
#chart-shading-canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 1;
}

/* MULTI-TF COMPASS & STATE HUD */
.chart-intel-hud {
  position: absolute;
  top: 12px;
  left: 14px;
  z-index: 2;
  pointer-events: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.hud-line-1 {
  display: flex;
  align-items: center;
  gap: 8px;
}
.hud-symbol-tag {
  font-family: var(--font-mono);
  font-weight: 800;
  font-size: 13px;
  letter-spacing: 0.5px;
  color: var(--text-main);
  background: rgba(18, 22, 31, 0.85);
  border: 1px solid var(--border-strong);
  padding: 2px 7px;
  border-radius: 3px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.5);
  backdrop-filter: blur(4px);
}
.compass-pills {
  display: flex;
  align-items: center;
  gap: 4px;
}
.compass-pill {
  font-family: var(--font-mono);
  font-size: 9.5px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 3px;
  text-transform: uppercase;
  background: rgba(18, 22, 31, 0.85);
  border: 1px solid var(--border);
  backdrop-filter: blur(4px);
}
.pill-bull {
  color: var(--green);
  border-color: rgba(0, 230, 118, 0.35);
  background: rgba(0, 230, 118, 0.12);
}
.pill-bear {
  color: var(--red);
  border-color: rgba(255, 82, 82, 0.35);
  background: rgba(255, 82, 82, 0.12);
}
.pill-side {
  color: var(--amber);
  border-color: rgba(255, 215, 64, 0.35);
  background: rgba(255, 215, 64, 0.12);
}
.hud-line-2 {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-muted);
  background: rgba(18, 22, 31, 0.80);
  border: 1px solid var(--border);
  padding: 3px 8px;
  border-radius: 3px;
  backdrop-filter: blur(4px);
  width: fit-content;
}
.hud-metric {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.hud-dot {
  color: var(--text-dim);
}
.hud-highlight {
  font-weight: 700;
  color: var(--text-main);
}

/* BOTTOM DRAWER / TABS */
.bottom-drawer {
  height: 190px;
  background: var(--bg-surface);
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.drawer-tabs {
  display: flex;
  background: var(--bg-base);
  border-bottom: 1px solid var(--border);
}
.drawer-tab {
  padding: 6px 14px;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--text-dim);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  user-select: none;
}
.drawer-tab.active {
  color: var(--cyan);
  background: var(--bg-surface);
  border-bottom-color: var(--cyan);
}
.drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px 12px;
}
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-family: var(--font-mono);
  font-size: 10.5px;
}
.data-table th {
  text-align: left;
  padding: 4px 8px;
  color: var(--text-dim);
  border-bottom: 1px solid var(--border);
  font-weight: 600;
  font-size: 9px;
  text-transform: uppercase;
}
.data-table td {
  padding: 5px 8px;
  border-bottom: 1px solid rgba(255,255,255,0.03);
  color: var(--text-main);
}
.data-table tr:hover { background: var(--bg-hover); }

/* RIGHT PANEL: GATE INSPECTOR X-RAY */
.right-panel {
  background: var(--bg-surface);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.gate-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.gate-card {
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.gate-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.gate-title-box {
  display: flex;
  align-items: center;
  gap: 6px;
}
.gate-num {
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 700;
  color: var(--text-dim);
}
.gate-title {
  font-weight: 700;
  font-size: 11px;
  color: var(--text-main);
}
.gate-status-pill {
  font-size: 8.5px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 2px;
  font-family: var(--font-mono);
  text-transform: uppercase;
}
.status-pass { background: var(--green); color: #000; }
.status-block { background: var(--red); color: #fff; }
.status-wait { background: var(--amber); color: #000; }

.gate-detail {
  font-size: 10.5px;
  color: var(--text-muted);
  line-height: 1.35;
}
.gate-reason-box {
  background: rgba(255,255,255,0.02);
  border-left: 2px solid var(--border-strong);
  padding: 4px 6px;
  font-family: var(--font-mono);
  font-size: 9.5px;
  color: #cbd5e1;
  word-break: break-word;
}
.gate-reason-box.block { border-left-color: var(--red); color: #fca5a5; }
.gate-reason-box.pass { border-left-color: var(--green); color: #86efac; }
.gate-reason-box.wait { border-left-color: var(--amber); color: #fde047; }

/* TELEMETRY CARDS */
.telemetry-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}
.telemetry-card {
  background: var(--bg-base);
  border: 1px solid var(--border);
  padding: 8px;
  border-radius: 3px;
}
.tele-title { font-weight: 700; font-size: 10px; color: var(--cyan); text-transform: uppercase; margin-bottom: 4px; }
.tele-row { display: flex; justify-content: space-between; font-family: var(--font-mono); font-size: 10px; margin-bottom: 2px; }
.tele-lbl { color: var(--text-dim); }
.tele-val { color: var(--text-main); font-weight: 600; }

/* ERROR OVERLAY */
#error-banner {
  display: none;
  background: var(--red);
  color: #fff;
  padding: 6px 14px;
  font-weight: 700;
  font-size: 11px;
  text-align: center;
}
</style>
</head>
<body>

<div id="error-banner">⚠️ Terputus dari server backend atau terminal MT5. Mencoba menghubungkan kembali...</div>

<!-- TOP STATUS BAR -->
<div class="header-bar">
  <div class="header-left">
    <div class="app-brand">
      <div class="heartbeat-dot" id="live-dot"></div>
      <span>QUANT X-RAY COCKPIT</span>
    </div>
    <div class="account-stat">
      <span class="stat-label">Acct:</span>
      <span class="stat-val" id="acc-login">—</span>
    </div>
    <div class="account-stat">
      <span class="stat-label">Balance:</span>
      <span class="stat-val" id="acc-balance">$0.00</span>
    </div>
    <div class="account-stat">
      <span class="stat-label">Equity:</span>
      <span class="stat-val" id="acc-equity">$0.00</span>
    </div>
    <div class="account-stat">
      <span class="stat-label">Float P/L:</span>
      <span class="stat-val" id="acc-float">$0.00</span>
    </div>
    <div class="account-stat">
      <span class="stat-label">Closed Today:</span>
      <span class="stat-val" id="acc-closed">$0.00</span>
    </div>
  </div>
  <div class="header-right">
    <div class="account-stat">
      <span class="stat-label">Mode:</span>
      <span class="stat-val" style="color:var(--cyan);">STANDALONE OBSERVER</span>
    </div>
    <div class="clock-text" id="live-clock">--:--:-- WIB</div>
  </div>
</div>

<!-- WORKSPACE -->
<div class="workspace">
  
  <!-- LEFT: PROXIMITY WATCHLIST -->
  <div class="left-panel">
    <div class="panel-header">
      <span class="panel-title">26-Pair Proximity Radar</span>
      <span id="watchlist-count" style="font-family:var(--font-mono);font-size:10px;color:var(--text-dim);">26 pairs</span>
    </div>
    <input type="text" id="pair-search" class="search-input" placeholder="Cari pair (e.g. CAD, JPY)...">
    <div class="filter-tabs">
      <div class="filter-tab active" data-filter="all">ALL (26)</div>
      <div class="filter-tab" data-filter="near">NEAR (<1x ATR)</div>
      <div class="filter-tab" data-filter="allowed">GO / ARM</div>
      <div class="filter-tab" data-filter="open">MT5 OPEN</div>
    </div>
    <div class="watchlist-scroll" id="watchlist-container">
      <!-- Pair rows injected via JS -->
    </div>
  </div>

  <!-- CENTER: CHART & TELEMETRY -->
  <div class="center-panel">
    <!-- SUB-HEADER -->
    <div class="pair-header-bar">
      <div class="pair-headline">
        <span class="pair-title-big" id="active-symbol">—</span>
        <div class="tf-group">
          <button class="tf-btn active" data-tf="H1">H1 Structure</button>
          <button class="tf-btn" data-tf="M30">M30 JPY</button>
          <button class="tf-btn" data-tf="M5">M5 CRO Microscope</button>
        </div>
      </div>
      <div class="pair-metrics-strip">
        <div class="strip-item">
          <span class="strip-lbl">Live Bid / Ask</span>
          <span class="strip-val" id="strip-price">— / —</span>
        </div>
        <div class="strip-item">
          <span class="strip-lbl">Spread</span>
          <span class="strip-val" id="strip-spread">— pts</span>
        </div>
        <div class="strip-item">
          <span class="strip-lbl">ATR H1</span>
          <span class="strip-val" id="strip-atr">— pts</span>
        </div>
        <div class="strip-item">
          <span class="strip-lbl">Dealing Range</span>
          <span class="strip-val" id="strip-dr">—%</span>
        </div>
        <div class="strip-item">
          <span class="strip-lbl">CSM Delta</span>
          <span class="strip-val" id="strip-csm">—</span>
        </div>
        <div class="strip-item">
          <span class="strip-lbl">MSE Action Tier</span>
          <span class="strip-val" id="strip-tier">—</span>
        </div>
      </div>
    </div>

    <!-- FILTER STRIP BAR (High-Density Multi-Horizon Control) -->
    <div class="filter-strip-bar">
      <div class="filter-group">
        <span class="filter-strip-title">Vertical Shading:</span>
        <div class="strip-btn-group" id="vertical-filter-group">
          <button class="strip-btn active" data-vertical="sessions">Sessions</button>
          <button class="strip-btn" data-vertical="regimes">Regimes</button>
          <button class="strip-btn" data-vertical="both">Both</button>
          <button class="strip-btn" data-vertical="off">Off</button>
        </div>
      </div>
      <div class="filter-divider"></div>
      <div class="filter-group">
        <span class="filter-strip-title">ZCE Fortress Ladder:</span>
        <div class="strip-btn-group" id="zce-filter-group">
          <button class="strip-btn active" data-zce="all">All Zones (Clustered)</button>
          <button class="strip-btn" data-zce="macro">G2+G3 Macro</button>
          <button class="strip-btn" data-zce="primary">F1/C1 Primary</button>
        </div>
      </div>
    </div>

    <!-- CHART WRAPPER -->
    <div class="chart-wrapper">
      <div id="tv-chart"></div>
      <canvas id="chart-shading-canvas"></canvas>
      <div class="chart-intel-hud" id="chart-intel-hud">
        <div class="hud-line-1">
          <div class="hud-symbol-tag" id="hud-sym-tag">EURCAD H1</div>
          <div class="compass-pills">
            <span class="compass-pill pill-side" id="pill-w1">W1: —</span>
            <span class="compass-pill pill-side" id="pill-d1">D1: —</span>
            <span class="compass-pill pill-side" id="pill-h4">H4: —</span>
            <span class="compass-pill pill-side" id="pill-h1">H1: —</span>
          </div>
        </div>
        <div class="hud-line-2">
          <span class="hud-metric">ADX: <span class="hud-highlight" id="hud-adx">—</span></span>
          <span class="hud-dot">•</span>
          <span class="hud-metric">STATE: <span class="hud-highlight" id="hud-state">—</span></span>
          <span class="hud-dot">•</span>
          <span class="hud-metric">SESSION: <span class="hud-highlight" id="hud-session">—</span></span>
          <span class="hud-dot">•</span>
          <span class="hud-metric">PRE-ROLLOVER: <span class="hud-highlight" id="hud-rollover">—</span></span>
        </div>
      </div>
    </div>

    <!-- BOTTOM DRAWER -->
    <div class="bottom-drawer">
      <div class="drawer-tabs">
        <div class="drawer-tab active" data-drawer="orders">MT5 Live Positions & Pending</div>
        <div class="drawer-tab" data-drawer="telemetry">Radar Telemetry (M1, M2, M3, M4)</div>
        <div class="drawer-tab" data-drawer="rules">Active Rules & .env Inventory</div>
      </div>
      <div class="drawer-body" id="drawer-content">
        <!-- Content injected via JS -->
      </div>
    </div>
  </div>

  <!-- RIGHT: 7-GATE X-RAY SURVEILLANCE -->
  <div class="right-panel">
    <div class="panel-header">
      <span class="panel-title">Decision Gates Audit (X-Ray)</span>
      <span id="gate-symbol-label" style="font-family:var(--font-mono);font-size:10px;color:var(--cyan);">—</span>
    </div>
    <div class="gate-scroll" id="gates-container">
      <!-- 7 Gate cards injected via JS -->
    </div>
  </div>

</div>

<script>
// State Management
let currentSymbol = "EURCAD-ECNc";
let currentTF = "H1";
let currentFilter = "all";
let currentDrawerTab = "orders";
let activeVerticalFilter = "sessions"; // "sessions", "regimes", "both", "off"
let activeZceFilter = "all"; // "all", "macro", "primary"
let chart = null;
let candleSeries = null;
let ema20Series = null;
let ema50Series = null;
let ema200Series = null;
let priceLines = [];
let activeRenderedLevels = [];
let lastRenderedSymbol = null;
let lastRenderedTF = null;
let shadingCanvas = null;
let shadingCtx = null;

let cachedOverview = null;
let cachedSymbolData = null;
let cachedRules = null;

// Initialize Overlay Canvas for Vertical Shading
function initOverlayCanvas() {
  shadingCanvas = document.getElementById("chart-shading-canvas");
  if (!shadingCanvas) return;
  shadingCtx = shadingCanvas.getContext("2d");
  resizeOverlayCanvas();
  window.addEventListener("resize", resizeOverlayCanvas);
}

function resizeOverlayCanvas() {
  if (!shadingCanvas || !shadingCtx) return;
  const container = document.getElementById("tv-chart");
  const dpr = window.devicePixelRatio || 1;
  shadingCanvas.width = container.clientWidth * dpr;
  shadingCanvas.height = container.clientHeight * dpr;
  shadingCtx.resetTransform();
  shadingCtx.scale(dpr, dpr);
  renderVerticalShading();
}

function renderVerticalShading() {
  if (!shadingCanvas || !shadingCtx || !chart || !cachedSymbolData || !cachedSymbolData.candles) return;
  const container = document.getElementById("tv-chart");
  const width = container.clientWidth;
  const height = container.clientHeight;

  shadingCtx.clearRect(0, 0, width, height);

  // 1. Session & Regime Vertical Shading
  if (activeVerticalFilter !== "off") {
    const timeScale = chart.timeScale();
    const candles = cachedSymbolData.candles;
    if (candles.length > 0) {
      for (let i = 0; i < candles.length; i++) {
        const c = candles[i];
        const x1 = timeScale.timeToCoordinate(c.time);
        if (x1 === null || x1 < -30 || x1 > width + 30) continue;

        let x2 = width;
        if (i < candles.length - 1) {
          const nextX = timeScale.timeToCoordinate(candles[i + 1].time);
          if (nextX !== null) x2 = nextX;
          else x2 = x1 + 10;
        } else {
          if (i > 0) {
            const prevX = timeScale.timeToCoordinate(candles[i - 1].time);
            x2 = x1 + (prevX !== null ? Math.max(2, x1 - prevX) : 10);
          } else {
            x2 = x1 + 10;
          }
        }

        const barW = Math.max(1, x2 - x1);

        // 1. Session vertical shading
        if (activeVerticalFilter === "sessions" || activeVerticalFilter === "both") {
          let sessionColor = null;
          if (c.session === "TOKYO") sessionColor = "rgba(234, 179, 8, 0.045)"; // amber
          else if (c.session === "LONDON") sessionColor = "rgba(56, 189, 248, 0.055)"; // cyan
          else if (c.session === "OVERLAP") sessionColor = "rgba(168, 85, 247, 0.065)"; // purple
          else if (c.session === "LATE_NY") sessionColor = "rgba(99, 102, 241, 0.040)"; // indigo
          else if (c.session === "DEAD_ZONE") sessionColor = "rgba(239, 68, 68, 0.045)"; // red

          if (sessionColor) {
            shadingCtx.fillStyle = sessionColor;
            shadingCtx.fillRect(x1, 0, barW, height);
          }
        }

        // 2. Regime vertical shading
        if (activeVerticalFilter === "regimes" || activeVerticalFilter === "both") {
          let regimeColor = null;
          if (c.regime === "BULL_EXP") regimeColor = "rgba(0, 230, 118, 0.05)";
          else if (c.regime === "BEAR_EXP") regimeColor = "rgba(255, 82, 82, 0.05)";

          if (regimeColor) {
            shadingCtx.fillStyle = regimeColor;
            shadingCtx.fillRect(x1, 0, barW, height);
            // Bottom subtle regime indicator stripe (3px)
            shadingCtx.fillStyle = (c.regime === "BULL_EXP") ? "rgba(0, 230, 118, 0.65)" : "rgba(255, 82, 82, 0.65)";
            shadingCtx.fillRect(x1, height - 3, barW, 3);
          }
        }
      }
    }
  }

  // 2. Render Left Price Line Labels (Clean Institutional Badges on Far Left with Collision Avoidance)
  if (activeRenderedLevels && activeRenderedLevels.length > 0 && candleSeries) {
    shadingCtx.font = "bold 9.5px 'JetBrains Mono', monospace";
    shadingCtx.textBaseline = "middle";

    // Map and collect raw Y coordinates
    const mapped = [];
    activeRenderedLevels.forEach(lvl => {
      const rawY = candleSeries.priceToCoordinate(lvl.price);
      if (rawY !== null && rawY >= 10 && rawY <= height - 10) {
        mapped.push({
          lvl: lvl,
          rawY: rawY,
          targetY: rawY
        });
      }
    });

    // Sort by Y ascending (top to bottom)
    mapped.sort((a, b) => a.rawY - b.rawY);

    // Stagger / adjust overlapping badges (minimum 18px distance)
    let lastY = -999;
    mapped.forEach(item => {
      let adjY = item.rawY;
      if (adjY - lastY < 18) {
        adjY = lastY + 18;
      }
      item.targetY = Math.min(adjY, height - 10);
      lastY = item.targetY;
    });

    mapped.forEach(item => {
      const y = item.targetY;
      const lvl = item.lvl;
      const txt = lvl.label;
      const metrics = shadingCtx.measureText(txt);
      const txtW = metrics.width;
      const badgeH = 16;
      // Jika label berada di dekat HUD pojok kiri atas (y < 70), geser ke kanan sedikit agar tidak bertabrakan
      const badgeX = (y < 70) ? 310 : 14;
      const badgeY = y - badgeH / 2;

      // Draw subtle pill background
      shadingCtx.fillStyle = "rgba(11, 14, 20, 0.90)";
      shadingCtx.fillRect(badgeX, badgeY, txtW + 12, badgeH);

      // Draw left accent border indicator
      shadingCtx.fillStyle = lvl.color;
      shadingCtx.fillRect(badgeX, badgeY, 3, badgeH);

      // Draw text
      shadingCtx.fillStyle = lvl.color;
      shadingCtx.fillText(txt, badgeX + 7, y);
    });
  }
}

// Initialize Lightweight Chart
function initChart() {
  const container = document.getElementById("tv-chart");
  chart = LightweightCharts.createChart(container, {
    layout: {
      background: { color: "#0b0e14" },
      textColor: "#94a3b8",
      fontFamily: "'JetBrains Mono', monospace",
      fontSize: 10
    },
    grid: {
      vertLines: { color: "#161b26" },
      horzLines: { color: "#161b26" }
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: { color: "#38bdf8", width: 1, style: 2 },
      horzLine: { color: "#38bdf8", width: 1, style: 2 }
    },
    rightPriceScale: {
      borderColor: "#1e2533",
      scaleMargins: { top: 0.12, bottom: 0.12 }
    },
    timeScale: {
      borderColor: "#1e2533",
      timeVisible: true,
      secondsVisible: false,
      rightOffset: 15
    }
  });

  candleSeries = chart.addCandlestickSeries({
    upColor: "#00e676",
    downColor: "#ff5252",
    borderVisible: false,
    wickUpColor: "#00e676",
    wickDownColor: "#ff5252"
  });

  ema20Series = chart.addLineSeries({ color: "#00e5ff", lineWidth: 1, title: "EMA20" });
  ema50Series = chart.addLineSeries({ color: "#ffd740", lineWidth: 1, title: "EMA50" });
  ema200Series = chart.addLineSeries({ color: "#b388ff", lineWidth: 1.5, title: "EMA200" });

  initOverlayCanvas();

  chart.timeScale().subscribeVisibleLogicalRangeChange(renderVerticalShading);

  // Redraw labels immediately on pan, zoom, or scale drag
  container.addEventListener("wheel", () => {
    requestAnimationFrame(renderVerticalShading);
  }, { passive: true });

  container.addEventListener("pointermove", (e) => {
    if (e.buttons > 0) requestAnimationFrame(renderVerticalShading);
  });

  window.addEventListener("resize", () => {
    chart.resize(container.clientWidth, container.clientHeight);
    resizeOverlayCanvas();
  });
}

// Clear active price lines & temporal markers
function clearPriceLines() {
  priceLines.forEach(pl => {
    try { candleSeries.removePriceLine(pl); } catch(e) {}
  });
  priceLines = [];
  if (candleSeries) {
    try { candleSeries.setMarkers([]); } catch(e) {}
  }
}

// Render chart levels (ZCE Multi-Horizon Fortress Ladder + M1..M4 Reticles & Temporal Markers)
function renderChartLevels(data) {
  clearPriceLines();
  activeRenderedLevels = [];
  if (!data || !candleSeries) return;

  const rawLadder = (data.zce_ladder && data.zce_ladder.length > 0) ? data.zce_ladder : (data.zce_walls || []);
  let filteredLadder = [];

  if (activeZceFilter === "primary") {
    filteredLadder = rawLadder.filter(w => w.tier === "F1" || w.tier === "C1");
  } else if (activeZceFilter === "macro") {
    filteredLadder = rawLadder.filter(w => w.tier === "F1" || w.tier === "C1" || w.grade === "GRADE_3_MACRO" || w.grade === "GRADE_2_INTERMEDIATE");
  } else {
    filteredLadder = rawLadder;
  }

  filteredLadder.forEach(w => {
    const isFloor = w.type === "floor";
    let color = isFloor ? "#00e676" : "#ff5252";
    let lineWidth = 1;
    let lineStyle = LightweightCharts.LineStyle.Solid;

    if (w.grade === "GRADE_3_MACRO" || w.tier === "F1" || w.tier === "C1") {
      lineWidth = 2;
      lineStyle = LightweightCharts.LineStyle.Solid;
      color = isFloor ? "#00e676" : "#ff5252";
    } else if (w.grade === "GRADE_2_INTERMEDIATE") {
      lineWidth = 1.5;
      lineStyle = LightweightCharts.LineStyle.Dashed;
      color = isFloor ? "#4ade80" : "#f87171";
    } else {
      lineWidth = 1;
      lineStyle = LightweightCharts.LineStyle.Dotted;
      color = isFloor ? "rgba(74, 222, 128, 0.7)" : "rgba(248, 113, 113, 0.7)";
    }

    const titleText = w.label || `${w.tier} (${w.price.toFixed(data.digits || 5)})`;
    activeRenderedLevels.push({
      price: w.price,
      color: color,
      label: titleText
    });

    const line = candleSeries.createPriceLine({
      price: w.price,
      color: color,
      lineWidth: lineWidth,
      lineStyle: lineStyle,
      axisLabelVisible: true,
      title: "" // Dikosongkan agar sisi kanan (candle live) tidak tertutup
    });
    priceLines.push(line);
  });

  // 2. M1..M4 Radar Standbys (Dashed Price Lines & Temporal Candle Markers)
  const temporalMarkers = [];
  if (data.m_standbys && data.m_standbys.length > 0) {
    data.m_standbys.forEach(s => {
      let color = "#ffd740";
      if (s.type === "M1") color = "#fb923c";
      else if (s.type === "M2") color = "#38bdf8";
      else if (s.type === "M3") color = "#c084fc";
      else if (s.type === "M4") color = "#facc15";

      const standText = `[${s.type}] ${s.label} @ ${s.price.toFixed(data.digits || 5)}`;
      activeRenderedLevels.push({
        price: s.price,
        color: color,
        label: standText
      });

      // 1. Dashed Price Line (Garis Putus-Putus Presisi)
      const line = candleSeries.createPriceLine({
        price: s.price,
        color: color,
        lineWidth: 1.5,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: "" // Sisi kanan tetap bersih
      });
      priceLines.push(line);

      // 2. Temporal Candle Marker (Titik Terjadinya / Proyeksi Kapan)
      if (s.event_time && s.event_time > 0) {
        let shape = "circle";
        let pos = (s.direction === 1) ? "belowBar" : "aboveBar";
        let markerText = `[${s.type}]`;

        if (s.type === "M3") {
          shape = (s.direction === 1) ? "arrowUp" : "arrowDown";
          const statusDesc = (s.status === 'WAITING_RETEST') ? 'Waiting Retest' : 'Retest Active';
          const ageDesc = s.bar_age > 0 ? `${s.bar_age}b ago` : 'now';
          markerText = `[M3 BREAK] ${statusDesc} (${ageDesc})`;
        } else if (s.type === "M1") {
          shape = "circle";
          const statusDesc = (s.status === 'WAITING_CLOSE_RECLAIM') ? 'Waiting Close Reclaim' : (s.status === 'RECLAIMED_FADING' ? 'Reclaimed & Fading' : 'Sweep Watch');
          markerText = `[M1 SWEEP] ${statusDesc}`;
        } else if (s.type === "M2") {
          shape = (s.direction === 1) ? "arrowUp" : "arrowDown";
          markerText = `[M2 PULLBACK] Target @ ${s.price.toFixed(data.digits || 5)}`;
        } else if (s.type === "M4") {
          shape = (s.direction === 1) ? "arrowUp" : "arrowDown";
          markerText = `[M4 FLOW] Breakdown @ ${s.price.toFixed(data.digits || 5)}`;
        }

        temporalMarkers.push({
          time: s.event_time,
          position: pos,
          color: color,
          shape: shape,
          text: markerText
        });
      }
    });
  }

  // Set sorted temporal markers on candlestick series
  if (temporalMarkers.length > 0 && candleSeries) {
    temporalMarkers.sort((a, b) => a.time - b.time);
    candleSeries.setMarkers(temporalMarkers);
  } else if (candleSeries) {
    candleSeries.setMarkers([]);
  }

  // Render ulang label kiri setelah level diupdate
  renderVerticalShading();
}

// Fetch Overview Data (2.5s poll)
async function fetchOverview() {
  try {
    const res = await fetch("/api/overview");
    if (!res.ok) throw new Error("Network error");
    const data = await res.json();
    cachedOverview = data;
    document.getElementById("error-banner").style.display = "none";
    renderHeader(data.account, data.timestamp_wib);
    renderWatchlist(data.pairs);
  } catch (err) {
    document.getElementById("error-banner").style.display = "block";
  }
}

// Fetch Symbol Detailed Data
async function fetchSymbolData() {
  try {
    const res = await fetch(`/api/symbol/${encodeURIComponent(currentSymbol)}?tf=${currentTF}`);
    if (!res.ok) return;
    const data = await res.json();
    cachedSymbolData = data;
    renderSymbolHeader(data);
    renderChartData(data);
    renderGates(data.gates);
    renderDrawer();
  } catch (err) {
    console.error("Symbol fetch error:", err);
  }
}

// Render Top Header
function renderHeader(acc, clock) {
  if (!acc) return;
  document.getElementById("acc-login").textContent = acc.login || "Live MT5";
  document.getElementById("acc-balance").textContent = `$${(acc.balance || 0).toLocaleString('en-US', {minimumFractionDigits: 2})}`;
  document.getElementById("acc-equity").textContent = `$${(acc.equity || 0).toLocaleString('en-US', {minimumFractionDigits: 2})}`;
  
  const flEl = document.getElementById("acc-float");
  const flVal = acc.floating_pnl || 0;
  flEl.textContent = `${flVal >= 0 ? '+' : ''}$${flVal.toFixed(2)}`;
  flEl.className = `stat-val ${flVal >= 0 ? 'stat-pnl-pos' : 'stat-pnl-neg'}`;

  const clEl = document.getElementById("acc-closed");
  const clVal = acc.daily_closed_pnl || 0;
  clEl.textContent = `${clVal >= 0 ? '+' : ''}$${clVal.toFixed(2)}`;
  clEl.className = `stat-val ${clVal >= 0 ? 'stat-pnl-pos' : 'stat-pnl-neg'}`;

  if (clock) document.getElementById("live-clock").textContent = clock;
}

// Render Left Watchlist
function renderWatchlist(pairs) {
  if (!pairs) return;
  const container = document.getElementById("watchlist-container");
  const searchVal = document.getElementById("pair-search").value.toUpperCase();

  let filtered = pairs.filter(p => {
    if (searchVal && !p.symbol.includes(searchVal)) return false;
    if (currentFilter === "near") return p.is_near;
    if (currentFilter === "allowed") return p.tier === "FULL_ALLOW" || p.tier === "REDUCED_CONFIDENCE" || p.tier === "TP1_ONLY_SCALP";
    if (currentFilter === "open") return p.has_open_pos;
    return true;
  });

  document.getElementById("watchlist-count").textContent = `${filtered.length} of ${pairs.length} pairs`;

  let html = "";
  filtered.forEach(p => {
    const isSelected = (p.symbol === currentSymbol) ? "selected" : "";
    const cleanSym = p.symbol.replace("-ECNc", "").replace(".c", "").replace("-ECN", "");
    
    let setupPillClass = "setup-pill-idle";
    const sName = (p.active_setup || "").toUpperCase();
    const bName = (p.bias || "").toUpperCase();

    if (sName.includes("BEAR") || sName.includes("SELL") || (!sName.includes("BULL") && bName.includes("BEAR"))) {
      setupPillClass = "setup-pill-bear";
    } else if (sName.includes("BULL") || sName.includes("BUY") || (!sName.includes("BEAR") && bName.includes("BULL"))) {
      setupPillClass = "setup-pill-bull";
    } else if (p.is_near) {
      setupPillClass = "setup-pill-neutral";
    } else if (p.active_setup) {
      setupPillClass = "setup-pill-amber";
    }

    let tierClass = "tier-watch";
    if (p.tier === "FULL_ALLOW") tierClass = "tier-go";
    else if (p.tier === "REDUCED_CONFIDENCE" || p.tier === "TP1_ONLY_SCALP") tierClass = "tier-arm";
    else if (p.tier === "HARD_BLOCK") tierClass = "tier-lock";

    const csmClass = p.csm_delta >= 0 ? "csm-pos" : "csm-neg";
    const csmText = `${p.csm_delta >= 0 ? '+' : ''}${p.csm_delta.toFixed(1)}`;

    let biasColor = "var(--text-dim)";
    if (p.bias && p.bias.includes("BULL")) biasColor = "var(--green)";
    else if (p.bias && p.bias.includes("BEAR")) biasColor = "var(--red)";
    else biasColor = "var(--amber)";

    html += `
      <div class="pair-row ${isSelected}" onclick="selectSymbol('${p.symbol}')">
        <div>
          <div class="pair-symbol">${cleanSym}</div>
          <span class="pair-setup-pill ${setupPillClass}">${p.active_setup || "WATCH"}</span>
        </div>
        <div class="pair-meta">
          <div class="pair-dist-text">${p.dist_desc}</div>
          <div style="font-size:9px;font-weight:600;color:${biasColor};font-family:var(--font-mono);letter-spacing:0.3px;">${p.bias}</div>
        </div>
        <div class="pair-right">
          <span class="tier-badge ${tierClass}">${p.perm_label}</span>
          <span class="csm-badge ${csmClass}">CSM ${csmText}</span>
        </div>
      </div>
    `;
  });

  container.innerHTML = html;
}

// Select Symbol
function selectSymbol(sym) {
  currentSymbol = sym;
  fetchSymbolData();
  if (cachedOverview) renderWatchlist(cachedOverview.pairs);
}

// Render Center Sub-Header & Multi-TF Intel HUD
function renderSymbolHeader(d) {
  const clean = d.symbol.replace("-ECNc", "").replace(".c", "").replace("-ECN", "");
  document.getElementById("active-symbol").textContent = clean;
  document.getElementById("gate-symbol-label").textContent = clean;
  document.getElementById("strip-price").textContent = `${d.bid.toFixed(d.digits)} / ${d.ask.toFixed(d.digits)}`;
  document.getElementById("strip-spread").textContent = `${d.spread_pts} pts`;
  document.getElementById("strip-atr").textContent = `${d.atr_pts} pts`;
  document.getElementById("strip-dr").textContent = `${d.dr_pos.toFixed(1)}% (${d.dr_label})`;
  
  const csmEl = document.getElementById("strip-csm");
  csmEl.textContent = `${d.csm_delta >= 0 ? '+' : ''}${d.csm_delta.toFixed(2)}`;
  csmEl.className = `strip-val ${d.csm_delta >= 0 ? 'stat-pnl-pos' : 'stat-pnl-neg'}`;

  document.getElementById("strip-tier").textContent = `${d.action_tier} (${d.perm_label})`;

  // Render Multi-TF Compass & State HUD
  document.getElementById("hud-sym-tag").textContent = `${clean} ${currentTF}`;
  if (d.intel) {
    const it = d.intel;
    setCompassPill("pill-w1", "W1", it.w1_trend);
    setCompassPill("pill-d1", "D1", it.d1_trend);
    setCompassPill("pill-h4", "H4", it.h4_trend);
    setCompassPill("pill-h1", "H1", it.h1_trend);

    document.getElementById("hud-adx").textContent = `${it.adx}`;
    document.getElementById("hud-state").textContent = it.mse_state;
    document.getElementById("hud-session").textContent = it.active_session;
    document.getElementById("hud-rollover").textContent = it.pre_rollover_countdown;
  }
}

function setCompassPill(id, tfName, trend) {
  const el = document.getElementById(id);
  if (!el) return;
  const tr = (trend || "SIDE").toUpperCase();
  el.textContent = `${tfName}: ${tr}`;
  el.className = `compass-pill ${tr === 'BULL' ? 'pill-bull' : (tr === 'BEAR' ? 'pill-bear' : 'pill-side')}`;
}

// Render Candlestick & EMA
function renderChartData(d) {
  if (!d.candles || d.candles.length === 0) return;

  // 1. Bersihkan garis harga pair lama terlebih dahulu agar skala vertikal tidak tertarik/terjepit
  clearPriceLines();

  const isScopeChanged = (lastRenderedSymbol !== d.symbol || lastRenderedTF !== currentTF);

  // 2. Terapkan presisi desimal dinamis jika simbol berganti (3 digit JPY, 5 digit FX)
  if (isScopeChanged) {
    const pPrecision = d.digits || 5;
    const pMinMove = 1 / Math.pow(10, pPrecision);
    candleSeries.applyOptions({
      priceFormat: {
        type: 'price',
        precision: pPrecision,
        minMove: pMinMove
      }
    });
  }

  const candleData = [];
  const ema20Data = [];
  const ema50Data = [];
  const ema200Data = [];

  d.candles.forEach(c => {
    const t = c.time; // epoch seconds
    candleData.push({ time: t, open: c.open, high: c.high, low: c.low, close: c.close });
    if (c.ema20) ema20Data.push({ time: t, value: c.ema20 });
    if (c.ema50) ema50Data.push({ time: t, value: c.ema50 });
    if (c.ema200) ema200Data.push({ time: t, value: c.ema200 });
  });

  candleSeries.setData(candleData);
  ema20Series.setData(ema20Data);
  ema50Series.setData(ema50Data);
  ema200Series.setData(ema200Data);

  // 3. Auto-scale & Snap to Center HANYA saat ganti pair/timeframe (Zero flicker saat polling 3 detik)
  if (isScopeChanged) {
    chart.priceScale('right').applyOptions({ autoScale: true });
    chart.timeScale().fitContent();
    chart.timeScale().applyOptions({ rightOffset: 15 });
    lastRenderedSymbol = d.symbol;
    lastRenderedTF = currentTF;
  }

  // 4. Gambar ulang garis ZCE & M1..M4 pada skala pair yang sudah rapi
  renderChartLevels(d);
  renderVerticalShading();
}

// Render Right Gate Checklist
function renderGates(gates) {
  const container = document.getElementById("gates-container");
  if (!gates || gates.length === 0) {
    container.innerHTML = `<div style="padding:10px;color:var(--text-dim);">Memuat data gate...</div>`;
    return;
  }

  let html = "";
  gates.forEach(g => {
    let statusClass = "status-wait";
    let boxClass = "wait";
    if (g.status === "PASS") { statusClass = "status-pass"; boxClass = "pass"; }
    else if (g.status === "BLOCK") { statusClass = "status-block"; boxClass = "block"; }

    html += `
      <div class="gate-card">
        <div class="gate-header">
          <div class="gate-title-box">
            <span class="gate-num">G${g.id}</span>
            <span class="gate-title">${g.title}</span>
          </div>
          <span class="gate-status-pill ${statusClass}">${g.status}</span>
        </div>
        <div class="gate-detail">${g.desc}</div>
        <div class="gate-reason-box ${boxClass}">${g.reason}</div>
      </div>
    `;
  });

  container.innerHTML = html;
}

// Render Bottom Drawer
function renderDrawer() {
  const container = document.getElementById("drawer-content");
  const d = cachedSymbolData;

  if (currentDrawerTab === "orders") {
    if (!d || (!d.open_positions?.length && !d.pending_orders?.length)) {
      container.innerHTML = `<div style="padding:10px;color:var(--text-dim);font-family:var(--font-mono);">Tidak ada open position atau pending orders untuk ${currentSymbol}. Total Akun Open: ${cachedOverview?.account?.open_count || 0}.</div>`;
      return;
    }

    let html = `<table class="data-table"><thead><tr>
      <th>Ticket</th><th>Type</th><th>Volume</th><th>Open Price</th><th>Current SL</th><th>Current TP</th><th>Profit</th><th>Management Stage</th><th>Pre-Rollover Dist</th>
    </tr></thead><tbody>`;

    (d.open_positions || []).forEach(p => {
      const pnlClass = p.profit >= 0 ? "stat-pnl-pos" : "stat-pnl-neg";
      html += `<tr>
        <td>#${p.ticket}</td>
        <td style="color:${p.type_str === 'BUY' ? 'var(--green)' : 'var(--red)'};font-weight:700;">${p.type_str}</td>
        <td>${p.volume.toFixed(2)}</td>
        <td>${p.price_open.toFixed(d.digits)}</td>
        <td>${p.sl ? p.sl.toFixed(d.digits) : '—'}</td>
        <td>${p.tp ? p.tp.toFixed(d.digits) : '—'}</td>
        <td class="${pnlClass}" style="font-weight:700;">${p.profit >= 0 ? '+' : ''}$${p.profit.toFixed(2)}</td>
        <td><span style="color:var(--cyan);font-weight:600;">${p.mgt_badge || 'ACTIVE BREATHING'}</span></td>
        <td>${p.rollover_dist || 'Safe (>200 pts)'}</td>
      </tr>`;
    });

    (d.pending_orders || []).forEach(o => {
      html += `<tr>
        <td>#${o.ticket}</td>
        <td style="color:var(--amber);font-weight:700;">${o.type_str}</td>
        <td>${o.volume.toFixed(2)}</td>
        <td>${o.price_open.toFixed(d.digits)}</td>
        <td>${o.sl ? o.sl.toFixed(d.digits) : '—'}</td>
        <td>${o.tp ? o.tp.toFixed(d.digits) : '—'}</td>
        <td>PENDING</td>
        <td><span style="color:var(--amber);">WAITING FILL</span></td>
        <td>—</td>
      </tr>`;
    });

    html += `</tbody></table>`;
    container.innerHTML = html;

  } else if (currentDrawerTab === "telemetry") {
    if (!d || !d.telemetry) {
      container.innerHTML = `<div style="padding:10px;color:var(--text-dim);">Memuat telemetry radar...</div>`;
      return;
    }
    const t = d.telemetry;
    container.innerHTML = `
      <div class="telemetry-grid">
        <div class="telemetry-card">
          <div class="tele-title">M1: Universal Liquidity Sweep</div>
          <div class="tele-row"><span class="tele-lbl">Target Sweep:</span><span class="tele-val">${t.m1_target || '—'}</span></div>
          <div class="tele-row"><span class="tele-lbl">Penetration:</span><span class="tele-val">${t.m1_penetration || 'No (>0.04 ATR)'}</span></div>
          <div class="tele-row"><span class="tele-lbl">Reclaim Status:</span><span class="tele-val">${t.m1_reclaim || 'Unconfirmed'}</span></div>
          <div class="tele-row"><span class="tele-lbl">Rejection Wick:</span><span class="tele-val">${t.m1_wick || '0.0% (Req >=33%)'}</span></div>
        </div>
        <div class="telemetry-card">
          <div class="tele-title">M2: Trend Pullback Retest</div>
          <div class="tele-row"><span class="tele-lbl">ADX Trend Strength:</span><span class="tele-val">${t.m2_adx || '—'}</span></div>
          <div class="tele-row"><span class="tele-lbl">Fib 50% Level:</span><span class="tele-val">${t.m2_fib50 || '—'}</span></div>
          <div class="tele-row"><span class="tele-lbl">Fib 61.8% Pocket:</span><span class="tele-val">${t.m2_fib618 || '—'}</span></div>
          <div class="tele-row"><span class="tele-lbl">Discount Status:</span><span class="tele-val">${t.m2_zone || 'EQUILIBRIUM'}</span></div>
        </div>
        <div class="telemetry-card">
          <div class="tele-title">M3: Breakout Retest Guard</div>
          <div class="tele-row"><span class="tele-lbl">Broken SBR/RBS:</span><span class="tele-val">${t.m3_level || '—'}</span></div>
          <div class="tele-row"><span class="tele-lbl">15-Bar Recency:</span><span class="tele-val">${t.m3_recency || 'PASS'}</span></div>
          <div class="tele-row"><span class="tele-lbl">Runaway Push:</span><span class="tele-val">${t.m3_runaway || '1.10x ATR (Max 2.5x)'}</span></div>
          <div class="tele-row"><span class="tele-lbl">Target Runway:</span><span class="tele-val">${t.m3_runway || '1.40x ATR (Req >=0.8x)'}</span></div>
        </div>
        <div class="telemetry-card">
          <div class="tele-title">M4: Systemic Flow Continuation</div>
          <div class="tele-row"><span class="tele-lbl">Currency Z-Score:</span><span class="tele-val">${t.m4_z || '—'} (Req >=1.5)</span></div>
          <div class="tele-row"><span class="tele-lbl">120-Bar Breakdown:</span><span class="tele-val">${t.m4_breakdown || '—'}</span></div>
          <div class="tele-row"><span class="tele-lbl">Structural SL/TP:</span><span class="tele-val">SL 0.45x ATR | TP 1.1R</span></div>
          <div class="tele-row"><span class="tele-lbl">Standby Order:</span><span class="tele-val">${t.m4_pending || 'None'}</span></div>
        </div>
      </div>
    `;
  } else if (currentDrawerTab === "rules") {
    if (!cachedRules) {
      fetchRules();
      container.innerHTML = `<div style="padding:10px;color:var(--text-dim);">Mengambil data inventaris konfigurasi aktif...</div>`;
      return;
    }
    let html = `<table class="data-table"><thead><tr><th>Kategori Fitur</th><th>Parameter (.env / config.py)</th><th>Nilai Aktif</th><th>Deskripsi Fungsi & Formula</th></tr></thead><tbody>`;
    cachedRules.forEach(r => {
      html += `<tr>
        <td style="color:var(--cyan);font-weight:700;">${r.category}</td>
        <td style="font-weight:600;">${r.param}</td>
        <td style="color:var(--amber);font-weight:700;">${r.value}</td>
        <td style="color:var(--text-muted);">${r.desc}</td>
      </tr>`;
    });
    html += `</tbody></table>`;
    container.innerHTML = html;
  }
}

async function fetchRules() {
  try {
    const res = await fetch("/api/rules");
    cachedRules = await res.json();
    if (currentDrawerTab === "rules") renderDrawer();
  } catch(e) {}
}

// Setup Event Handlers
function setupEvents() {
  // Filter tabs
  document.querySelectorAll(".filter-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".filter-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      currentFilter = tab.getAttribute("data-filter");
      if (cachedOverview) renderWatchlist(cachedOverview.pairs);
    });
  });

  // Timeframe buttons
  document.querySelectorAll(".tf-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tf-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentTF = btn.getAttribute("data-tf");
      fetchSymbolData();
    });
  });

  // Drawer tabs
  document.querySelectorAll(".drawer-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".drawer-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      currentDrawerTab = tab.getAttribute("data-drawer");
      renderDrawer();
    });
  });

  // Vertical filter strip buttons
  document.querySelectorAll("#vertical-filter-group .strip-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#vertical-filter-group .strip-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      activeVerticalFilter = btn.getAttribute("data-vertical");
      renderVerticalShading();
    });
  });

  // ZCE ladder filter strip buttons
  document.querySelectorAll("#zce-filter-group .strip-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#zce-filter-group .strip-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      activeZceFilter = btn.getAttribute("data-zce");
      if (cachedSymbolData) renderChartLevels(cachedSymbolData);
    });
  });

  // Search input
  document.getElementById("pair-search").addEventListener("input", () => {
    if (cachedOverview) renderWatchlist(cachedOverview.pairs);
  });
}

// Bootstrap
window.addEventListener("DOMContentLoaded", () => {
  initChart();
  setupEvents();
  fetchOverview();
  fetchSymbolData();
  fetchRules();

  // Fast Polling loop: 2.5s
  setInterval(fetchOverview, 2500);
  setInterval(fetchSymbolData, 3000);
});
</script>
</body>
</html>
"""
