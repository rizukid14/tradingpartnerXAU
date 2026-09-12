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
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200" />
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
.material-symbols-outlined {
  font-family: 'Material Symbols Outlined';
  font-weight: normal;
  font-style: normal;
  font-size: 14px;
  line-height: 1;
  display: inline-block;
  vertical-align: middle;
  -webkit-font-smoothing: antialiased;
}
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

/* TOP STATUS BAR (44px Institutional Standard) */
.header-bar {
  height: 44px;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  user-select: none;
  gap: 12px;
  overflow-x: auto;
}
.header-bar::-webkit-scrollbar {
  display: none;
}
.header-left, .header-right {
  display: flex;
  align-items: center;
  gap: 10px;
  white-space: nowrap;
  flex-shrink: 0;
}
.app-brand {
  font-weight: 800;
  font-size: 11.5px;
  letter-spacing: 0.5px;
  color: var(--cyan);
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  flex-shrink: 0;
}
.heartbeat-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 5px var(--green);
  flex-shrink: 0;
}
.account-stat {
  display: flex;
  align-items: center;
  gap: 5px;
  font-family: var(--font-mono);
  font-size: 10.5px;
  white-space: nowrap;
  flex-shrink: 0;
}
.stat-label { color: var(--text-dim); text-transform: uppercase; font-size: 10px; font-family: var(--font-ui); font-weight: 600; }
.stat-val { color: var(--text-main); font-weight: 600; }
.stat-pnl-pos { color: var(--green); }
.stat-pnl-neg { color: var(--red); }
.clock-text {
  font-family: var(--font-mono);
  color: var(--text-muted);
  font-size: 11px;
  white-space: nowrap;
  flex-shrink: 0;
}

/* MAIN WORKSPACE GRID */
.workspace {
  display: grid;
  grid-template-columns: 340px 1fr 330px;
  height: calc(100vh - 44px);
  width: 100vw;
  transition: grid-template-columns 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.workspace.xray-collapsed {
  grid-template-columns: 340px 1fr 38px;
}
.workspace.left-collapsed {
  grid-template-columns: 38px 1fr 330px;
}
.workspace.left-collapsed.xray-collapsed {
  grid-template-columns: 38px 1fr 38px;
}
.workspace.left-collapsed .left-panel .panel-header span,
.workspace.left-collapsed .left-panel .search-input,
.workspace.left-collapsed .left-panel .filter-tabs,
.workspace.left-collapsed .left-panel .watchlist-scroll {
  display: none !important;
}
.workspace.left-collapsed .left-panel {
  cursor: pointer;
}
.workspace.left-collapsed .left-collapsed-label {
  display: flex !important;
}
.left-collapsed-label {
  display: none;
  writing-mode: vertical-rl;
  text-orientation: mixed;
  transform: rotate(180deg);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1.5px;
  color: var(--text-dim);
  text-align: center;
  padding: 15px 0;
  cursor: pointer;
  height: 100%;
  align-items: center;
  justify-content: center;
}
.workspace.xray-collapsed .right-panel .panel-header span,
.workspace.xray-collapsed #gates-container {
  display: none !important;
}
.workspace.xray-collapsed .right-panel {
  cursor: pointer;
}
.workspace.xray-collapsed .xray-collapsed-label {
  display: flex !important;
}
.xray-collapsed-label {
  display: none;
  writing-mode: vertical-rl;
  text-orientation: mixed;
  transform: rotate(180deg);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 1.5px;
  color: var(--text-dim);
  text-align: center;
  padding: 15px 0;
  cursor: pointer;
  height: 100%;
  align-items: center;
  justify-content: center;
}
.btn-toggle-panel {
  background: rgba(255,255,255,0.06);
  border: 1px solid var(--border);
  color: var(--text-dim);
  padding: 1px 6px;
  border-radius: 2px;
  font-size: 9px;
  cursor: pointer;
  transition: all 0.15s ease;
  line-height: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.btn-toggle-panel:hover {
  color: var(--cyan);
  border-color: var(--cyan);
  background: rgba(0,229,255,0.1);
}
.btn-toggle-xray {
  background: rgba(255,255,255,0.06);
  border: 1px solid var(--border);
  color: var(--text-dim);
  padding: 1px 6px;
  border-radius: 2px;
  font-size: 9px;
  cursor: pointer;
  transition: all 0.15s ease;
  line-height: 1;
}
.btn-toggle-xray:hover {
  color: var(--cyan);
  border-color: var(--cyan);
  background: rgba(0,229,255,0.1);
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
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 9px 10px;
  border-bottom: 1px solid rgba(255,255,255,0.03);
  cursor: pointer;
  user-select: none;
  transition: background 0.1s ease;
}
.pair-row:hover { background: var(--bg-hover); }
.pair-row.selected {
  background: var(--bg-elevated);
  border-left: 3.5px solid var(--cyan);
}
.pair-row.m4-shock-row {
  border-left: 3.5px solid #facc15;
  background: rgba(250, 204, 21, 0.04);
}
.pair-row.m4-shock-row:hover {
  background: rgba(250, 204, 21, 0.08);
}
.pair-row.m4-shock-row.selected {
  background: rgba(250, 204, 21, 0.12);
  border-left: 3.5px solid #facc15;
}
.m4-shock-pill {
  background: rgba(250, 204, 21, 0.16);
  color: #facc15;
  border: 1px solid rgba(250, 204, 21, 0.45);
  padding: 1px 5px;
  border-radius: 2.5px;
  font-size: 8.5px;
  font-family: var(--font-mono);
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  white-space: nowrap;
}
.pair-row.m4-cont-row {
  border-left: 3.5px solid rgba(56, 189, 248, 0.65);
  background: rgba(56, 189, 248, 0.03);
}
.pair-row.m4-cont-row:hover {
  background: rgba(56, 189, 248, 0.06);
}
.pair-row.m4-cont-row.selected {
  background: rgba(56, 189, 248, 0.10);
  border-left: 3.5px solid #38bdf8;
}
.m4-cont-pill {
  background: rgba(56, 189, 248, 0.14);
  color: #38bdf8;
  border: 1px solid rgba(56, 189, 248, 0.35);
  padding: 1px 5px;
  border-radius: 2.5px;
  font-size: 8.5px;
  font-family: var(--font-mono);
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  white-space: nowrap;
}
.box-compress-pill {
  background: rgba(56, 189, 248, 0.16);
  color: #38bdf8;
  border: 1px solid rgba(56, 189, 248, 0.45);
  padding: 1px 4px;
  border-radius: 2.5px;
  font-size: 8px;
  font-family: var(--font-mono);
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  white-space: nowrap;
}
.w1-conflict-pill {
  background: rgba(245, 158, 11, 0.18);
  color: #fbbf24;
  border: 1px solid rgba(245, 158, 11, 0.5);
  padding: 1px 4px;
  border-radius: 2.5px;
  font-size: 8px;
  font-family: var(--font-mono);
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  white-space: nowrap;
}
.header-alerts-inline {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: 6px;
}
.header-alert-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 7px;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  cursor: help;
  transition: all 0.15s ease;
  user-select: none;
  line-height: 1.2;
}
.header-alert-chip.chip-m4 {
  background: rgba(250, 204, 21, 0.12);
  border: 1px solid rgba(250, 204, 21, 0.45);
  color: #facc15;
}
.header-alert-chip.chip-w1 {
  background: rgba(245, 158, 11, 0.15);
  border: 1px solid rgba(245, 158, 11, 0.50);
  color: #fbbf24;
}
.header-alert-chip:hover {
  filter: brightness(1.25);
  transform: translateY(-1px);
}
.pair-row-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  white-space: nowrap;
}
.pair-col-left {
  width: 100px;
  min-width: 100px;
  max-width: 100px;
  display: flex;
  align-items: center;
  gap: 4px;
  overflow: hidden;
}
.pair-col-mid {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
  overflow: hidden;
  font-family: var(--font-mono);
  font-size: 9px;
}
.pair-col-right {
  min-width: 52px;
  display: flex;
  justify-content: flex-end;
  align-items: center;
}
.pair-symbol {
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 11.5px;
  color: var(--text-main);
  letter-spacing: 0.2px;
}
.pair-setup-pill {
  font-size: 8.5px;
  font-weight: 700;
  padding: 1px 3.5px;
  border-radius: 2px;
  display: inline-block;
  font-family: var(--font-mono);
  text-transform: uppercase;
  white-space: nowrap;
}
.tactical-pill {
  background: rgba(255,183,3,0.15);
  color: var(--amber);
  border: 1px solid rgba(255,183,3,0.3);
  padding: 0px 4px;
  border-radius: 2px;
  font-size: 8px;
  font-family: var(--font-mono);
  white-space: nowrap;
  letter-spacing: 0.2px;
}
.setup-near { background: rgba(0, 230, 118, 0.18); color: var(--green); border: 1px solid var(--green); }
.setup-standby { background: rgba(255, 215, 64, 0.15); color: var(--amber); border: 1px solid var(--amber); }
.setup-idle { background: rgba(148, 163, 184, 0.1); color: var(--text-dim); }

.setup-pill-bull { background: rgba(0, 230, 118, 0.16); color: var(--green); border: 1px solid var(--green); }
.setup-pill-bear { background: rgba(255, 82, 82, 0.16); color: var(--red); border: 1px solid var(--red); }
.setup-pill-confl-bull { background: rgba(0, 230, 118, 0.22); color: var(--green); border: 1px solid #ffd700; box-shadow: 0 0 5px rgba(255, 215, 0, 0.35); font-weight: 800; }
.setup-pill-confl-bear { background: rgba(255, 82, 82, 0.22); color: var(--red); border: 1px solid #ffd700; box-shadow: 0 0 5px rgba(255, 215, 0, 0.35); font-weight: 800; }
.setup-pill-neutral { background: rgba(0, 229, 255, 0.14); color: var(--cyan); border: 1px solid var(--cyan); }
.setup-pill-amber { background: rgba(255, 215, 64, 0.14); color: var(--amber); border: 1px solid var(--amber); }
.setup-pill-idle { background: rgba(148, 163, 184, 0.1); color: var(--text-dim); border: 1px solid rgba(148, 163, 184, 0.2); }
.extra-setup-pill {
  font-size: 7.5px;
  font-weight: 700;
  background: rgba(148, 163, 184, 0.18);
  color: var(--text-dim);
  border: 1px solid rgba(148, 163, 184, 0.3);
  padding: 0px 3px;
  border-radius: 2px;
  font-family: var(--font-mono);
}
.htf-bias-tag {
  padding: 1px 4px;
  border-radius: 2px;
  font-size: 8.5px;
  font-family: var(--font-mono);
  font-weight: 700;
  letter-spacing: 0.3px;
  display: inline-block;
}
.htf-bull { background: rgba(0, 230, 118, 0.14); color: var(--green); border: 1px solid rgba(0, 230, 118, 0.3); }
.htf-bear { background: rgba(255, 82, 82, 0.14); color: var(--red); border: 1px solid rgba(255, 82, 82, 0.3); }
.htf-flat { background: rgba(255, 215, 64, 0.14); color: var(--amber); border: 1px solid rgba(255, 215, 64, 0.3); }


.pair-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.pair-dist-text {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex-shrink: 1;
  min-width: 0;
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

.csm-text {
  font-family: var(--font-mono);
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.2px;
  white-space: nowrap;
}
.csm-pos { color: var(--green); }
.csm-neg { color: var(--red); }

/* CENTER STAGE */
.center-panel {
  position: relative;
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
  gap: 12px;
  user-select: none;
  overflow-x: auto;
}
.filter-strip-bar::-webkit-scrollbar {
  height: 2px;
}
.filter-group {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.filter-strip-title {
  font-family: var(--font-ui);
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: var(--text-dim);
  white-space: nowrap;
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
  white-space: nowrap;
}
.strip-btn:hover {
  color: var(--text-main);
}
.strip-btn.active {
  background: var(--cyan);
  color: #000;
}
.chip-toggle-group {
  display: flex;
  gap: 4px;
  align-items: center;
}
.chip-btn {
  padding: 2px 7px;
  font-size: 9px;
  font-weight: 700;
  font-family: var(--font-mono);
  cursor: pointer;
  border-radius: 3px;
  border: 1px solid var(--border);
  background: var(--bg-base);
  color: var(--text-muted);
  user-select: none;
  transition: all 0.12s ease;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  line-height: 1.2;
  white-space: nowrap;
}
.chip-btn:hover {
  border-color: var(--border-strong);
  color: var(--text-main);
}
.chip-btn.active {
  background: rgba(0, 229, 255, 0.14);
  border-color: var(--cyan);
  color: var(--cyan);
}
.chip-btn.active-green {
  background: rgba(56, 189, 248, 0.14);
  border-color: #38bdf8;
  color: #38bdf8;
}
.chip-btn.active-red {
  background: rgba(251, 191, 36, 0.14);
  border-color: #fbbf24;
  color: #fbbf24;
}
.chip-btn.active-purple {
  background: rgba(192, 132, 252, 0.14);
  border-color: #c084fc;
  color: #c084fc;
}
.chip-btn.active-amber {
  background: rgba(251, 191, 36, 0.14);
  border-color: #facc15;
  color: #facc15;
}
.chip-btn.active-cyan {
  background: rgba(56, 189, 248, 0.14);
  border-color: #38bdf8;
  color: #38bdf8;
}
.filter-divider {
  width: 1px;
  height: 14px;
  background: var(--border-strong);
  flex-shrink: 0;
}

/* CHART CONTAINER */
.chart-wrapper {
  flex: 1 1 0;
  min-height: 0;
  position: relative;
  width: 100%;
  height: auto;
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

/* ZCE INTERACTIVE HOVER MICRO-POPUP */
.zce-hover-tooltip {
  position: absolute;
  display: none;
  pointer-events: none;
  z-index: 50;
  background: rgba(15, 23, 42, 0.96);
  backdrop-filter: blur(10px);
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  padding: 8px 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.65);
  font-family: var(--font-mono);
  font-size: 10px;
  line-height: 1.45;
  color: var(--text-main);
  max-width: 320px;
  transition: opacity 0.1s ease;
}
.zce-tt-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--border);
}
.zce-tt-tier {
  font-weight: 700;
  font-size: 11px;
}
.zce-tt-score {
  color: var(--amber);
  font-weight: 700;
}
.zce-tt-confluences {
  color: var(--text-muted);
  font-size: 9.5px;
  margin-bottom: 4px;
  word-break: break-word;
}
.zce-tt-meta {
  display: flex;
  justify-content: space-between;
  color: var(--text-dim);
  font-size: 9px;
  border-top: 1px dashed var(--border);
  padding-top: 3px;
}

/* FILTER STRIP LEGENDS (Right Aligned on Toolbar) */
.filter-strip-legends {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  padding: 2px 8px;
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: 4px;
}

/* HORIZONTAL HUD ROW: 100% FULL WIDTH INFO OVERLAY */
.chart-hud-row {
  position: absolute;
  top: 10px;
  left: 12px;
  right: 70px;
  display: flex;
  align-items: center;
  pointer-events: none;
  z-index: 2;
}
.chart-intel-hud {
  pointer-events: auto;
  width: 100%;
  min-width: 0;
}

/* MINI LEGEND OVERLAY (Context-Aware Legend) */
.toolbar-ema-legend {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-mono);
  font-size: 9.5px;
  font-weight: 600;
  color: var(--text-muted);
  white-space: nowrap;
}
.ema-leg-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.ema-leg-bar {
  width: 10px;
  height: 2px;
  border-radius: 1px;
  display: inline-block;
}

.toolbar-mini-legend {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-dim);
  white-space: nowrap;
}
.mini-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  white-space: nowrap;
}
.mini-legend-dot {
  width: 6px;
  height: 6px;
  border-radius: 2px;
  display: inline-block;
  flex-shrink: 0;
}

/* SINGLE-LINE MINIMAL GLASS HUD CAPSULE */
.hud-capsule {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 4px 12px;
  background: rgba(15, 23, 42, 0.78);
  border: 1px solid rgba(255, 255, 255, 0.10);
  border-radius: 20px;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.45);
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
  user-select: none;
  white-space: nowrap;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
}
.hud-capsule-sym {
  font-weight: 800;
  color: #f8fafc;
  letter-spacing: 0.3px;
}
.compass-pills {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
.compass-pill {
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 700;
  padding: 1px 4px;
  border-radius: 2px;
  text-transform: uppercase;
  background: rgba(18, 22, 31, 0.85);
  border: 1px solid var(--border);
}
.pill-bull { color: var(--green); border-color: rgba(0, 230, 118, 0.35); background: rgba(0, 230, 118, 0.12); }
.pill-bear { color: var(--red); border-color: rgba(255, 82, 82, 0.35); background: rgba(255, 82, 82, 0.12); }
.pill-side { color: var(--amber); border-color: rgba(255, 215, 64, 0.35); background: rgba(255, 215, 64, 0.12); }
.hud-capsule-sep {
  color: rgba(255, 255, 255, 0.22);
  font-size: 8px;
}
.hud-capsule-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--text-muted);
}
.hud-capsule-badge {
  font-weight: 700;
  font-size: 9.5px;
  padding: 1px 5px;
  border-radius: 3px;
  background: rgba(56, 189, 248, 0.12);
  color: #38bdf8;
  border: 1px solid rgba(56, 189, 248, 0.35);
}
.hud-capsule-pat {
  font-weight: 700;
  color: #fbbf24;
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
  height: 200px;
  flex-shrink: 0;
  background: var(--bg-surface);
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: height 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.bottom-drawer.bottom-collapsed {
  height: 28px !important;
  flex-shrink: 0;
}
.bottom-drawer.bottom-collapsed .drawer-body {
  display: none !important;
}
.bottom-drawer.bottom-maximized {
  position: absolute !important;
  top: 0 !important;
  bottom: 0 !important;
  left: 0 !important;
  right: 0 !important;
  height: 100% !important;
  z-index: 50 !important;
  box-shadow: 0 -8px 24px rgba(0,0,0,0.85);
}
.drawer-tabs {
  display: flex;
  background: var(--bg-base);
  border-bottom: 1px solid var(--border);
  justify-content: space-between;
  align-items: center;
}
.drawer-tab-group {
  display: flex;
  align-items: center;
}
.drawer-toggle-box {
  padding: 0 8px;
  display: flex;
  align-items: center;
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
.status-observe { background: var(--cyan); color: #000; }
.status-paper { background: #38bdf8; color: #000; font-weight: 800; }

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
.gate-reason-box.observe { border-left-color: var(--cyan); color: #67e8f9; }
.gate-reason-box.paper { border-left-color: #38bdf8; color: #7dd3fc; }

/* TELEMETRY CARDS */
.telemetry-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px;
}
@media (max-width: 1200px) {
  .telemetry-grid { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 768px) {
  .telemetry-grid { grid-template-columns: 1fr; }
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

<div id="error-banner"><span class="material-symbols-outlined" style="font-size:14px;vertical-align:-2px;margin-right:4px;">warning</span>Terputus dari server backend atau terminal MT5. Mencoba menghubungkan kembali...</div>

<!-- TOP STATUS BAR -->
<div class="header-bar">
  <div class="header-left">
    <div class="app-brand" title="Quant Institutional Decision Cockpit">
      <div class="heartbeat-dot" id="live-dot"></div>
      <span>QUANT X-RAY</span>
    </div>
    <div class="account-stat">
      <span class="stat-label">Acct:</span>
      <span class="stat-val" id="acc-login">—</span>
    </div>
    <div class="account-stat">
      <span class="stat-label">Bal:</span>
      <span class="stat-val" id="acc-balance">$0.00</span>
    </div>
    <div class="account-stat">
      <span class="stat-label">Eq:</span>
      <span class="stat-val" id="acc-equity">$0.00</span>
    </div>
    <div class="account-stat">
      <span class="stat-label">Float:</span>
      <span class="stat-val" id="acc-float">$0.00</span>
    </div>
    <div class="account-stat">
      <span class="stat-label">Closed:</span>
      <span class="stat-val" id="acc-closed">$0.00</span>
    </div>
  </div>
  <div class="header-right">
    <div class="account-stat">
      <span class="stat-label">Shadow:</span>
      <span class="stat-val" id="shadow-stat-val" style="color:var(--purple);font-size:10.5px;">0 rec (0% WR)</span>
      <a href="/shadow" target="_blank" title="Buka Laporan Lengkap Quant Shadow (HTML)" style="margin-left:4px;padding:2px 5px;border-radius:3px;background:rgba(192,132,252,0.18);border:1px solid #c084fc;color:#c084fc;text-decoration:none;font-size:9px;font-weight:700;display:inline-flex;align-items:center;gap:3px;"><span class="material-symbols-outlined" style="font-size:11px;vertical-align:-1px;">monitoring</span> LAPORAN</a>
    </div>
    <div class="account-stat">
      <span class="stat-label">Mode:</span>
      <span class="stat-val" id="engine-mode-val" style="color:var(--cyan);font-size:10.5px;font-weight:700;" title="Pure Quant Direct Execution (0 Token API) • CBSS Lead-Lag Active">QUANT (0-TOKEN)</span>
    </div>
    <div class="account-stat" id="timing-phase-stat">
      <span class="stat-label">Timing:</span>
      <span class="stat-val" id="timing-phase-val" style="color:var(--green);font-size:10.5px;font-weight:700;">EXPANSION</span>
    </div>
    <div class="clock-text" id="live-clock">--:--:-- WIB</div>
  </div>
</div>

<!-- WORKSPACE -->
<div class="workspace left-collapsed xray-collapsed">
  
  <!-- LEFT: PROXIMITY WATCHLIST -->
  <div class="left-panel">
    <div class="panel-header" onclick="if(document.querySelector('.workspace').classList.contains('left-collapsed')) toggleLeftPanel();">
      <div style="display:flex;align-items:center;gap:6px;">
        <span class="panel-title">26-Pair Proximity Radar</span>
        <span id="watchlist-count" style="font-family:var(--font-mono);font-size:10px;color:var(--text-dim);">Pairs</span>
      </div>
      <button id="btn-toggle-left" class="btn-toggle-panel" onclick="event.stopPropagation(); toggleLeftPanel();" title="Toggle Proximity Watchlist"><span class="material-symbols-outlined" style="font-size:11px;vertical-align:-1px;">chevron_right</span></button>
    </div>
    <div class="left-collapsed-label" onclick="toggleLeftPanel()" title="Klik untuk membuka Radar Watchlist">
      <span>RADAR WATCHLIST</span>
    </div>
    <input type="text" id="pair-search" class="search-input" placeholder="Cari pair (e.g. CAD, JPY)...">
    <div class="filter-tabs">
      <div class="filter-tab active" data-filter="all">ALL</div>
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
          <button class="tf-btn" data-tf="H4">H4 Pattern</button>
          <button class="tf-btn active" data-tf="H1">H1 Structure</button>
          <button class="tf-btn" data-tf="M30">M30 Swing</button>
          <button class="tf-btn" data-tf="M5">M5 Micro</button>
        </div>
        <div class="header-alerts-inline" id="header-alerts-inline">
          <span id="chip-m4-shock" class="header-alert-chip chip-m4" style="display:none;" title="Systemic Flow Shock">
            <span class="material-symbols-outlined" style="font-size:12px;vertical-align:-1px;">bolt</span>
            <span id="m4-chip-label">SFR ACTIVE</span>
          </span>
          <span id="chip-w1-slope" class="header-alert-chip chip-w1" style="display:none;" title="W1 Slope Ceiling">
            <span class="material-symbols-outlined" style="font-size:12px;vertical-align:-1px;">trending_down</span>
            <span id="w1-chip-label">W1 SLOPE CEILING</span>
          </span>
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
          <span class="strip-lbl">ZCE Runway</span>
          <span class="strip-val" id="strip-dr" style="color:var(--cyan);font-weight:600;">—</span>
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
        <span class="filter-strip-title">Vertical:</span>
        <div class="strip-btn-group" id="vertical-filter-group">
          <button class="strip-btn" data-vertical="sessions">Sessions</button>
          <button class="strip-btn active" data-vertical="regimes">Regimes</button>
          <button class="strip-btn" data-vertical="both">Both</button>
          <button class="strip-btn" data-vertical="off">Off</button>
        </div>
      </div>

      <div class="filter-divider"></div>

      <div class="filter-group">
        <span class="filter-strip-title">Filter 1-1:</span>
        <div class="chip-toggle-group" id="zce-chips-group">
          <button class="chip-btn active-purple" id="chip-radar" data-chip="radar" title="Toggle Garis Putus-Putus & Marker M1..M4 Radar"><span class="material-symbols-outlined" style="font-size:12px;vertical-align:-1px;color:#c084fc;">radar</span> M1-M4</button>
          <button class="chip-btn active" id="chip-f1c1" data-chip="f1c1" title="Toggle Level F1 & C1 (Primary Support & Resistance)">F1/C1</button>
          <button class="chip-btn" id="chip-f2c2" data-chip="f2c2" title="Toggle Level F2 & C2 (Secondary Support & Resistance)">F2/C2</button>
          <button class="chip-btn" id="chip-ext" data-chip="ext" title="Toggle Level Extension di atas F2 & C2 (F3+, C3+)">EXT</button>
          <button class="chip-btn active-cyan" id="chip-pattern" data-chip="pattern" title="Toggle SMC Dealing Range & Order Flow"><span class="material-symbols-outlined" style="font-size:12px;vertical-align:-1px;color:#38bdf8;">tune</span> SMC Range</button>
          <button class="chip-btn active-cyan" id="chip-ema" data-chip="ema" title="Toggle Garis EMA (20, 50, 200)"><span class="material-symbols-outlined" style="font-size:12px;vertical-align:-1px;color:#38bdf8;">show_chart</span> EMA</button>
        </div>
      </div>

      <!-- LEGENDS ALIGNED TO RIGHT OF TOOLBAR -->
      <div class="filter-strip-legends">
        <div id="chart-ema-legend" class="toolbar-ema-legend">
          <div class="ema-leg-item"><span class="ema-leg-bar" style="background:#00e5ff;"></span>EMA 20</div>
          <div class="ema-leg-item"><span class="ema-leg-bar" style="background:#ffd740;"></span>EMA 50</div>
          <div class="ema-leg-item"><span class="ema-leg-bar" style="background:#b388ff;"></span>EMA 200</div>
        </div>
        <span class="hud-capsule-sep" id="chart-mini-legend-sep">•</span>
        <div id="chart-mini-legend" class="toolbar-mini-legend"></div>
      </div>
    </div>

    <!-- CHART WRAPPER -->
    <div class="chart-wrapper">
      <div id="tv-chart"></div>
      <canvas id="chart-shading-canvas"></canvas>
      <div id="zce-hover-tooltip" class="zce-hover-tooltip"></div>
      
      <!-- HORIZONTAL HUD ROW: 100% FULL WIDTH INFO -->
      <div class="chart-hud-row">
        <div class="chart-intel-hud" id="chart-intel-hud">
          <div class="hud-capsule">
            <span class="hud-capsule-sym" id="hud-sym-tag">EURUSD H1</span>
            <div class="compass-pills" id="compass-pills">
              <span class="compass-pill pill-side" id="pill-w1">W1: —</span>
              <span class="compass-pill pill-side" id="pill-d1">D1: —</span>
              <span class="compass-pill pill-side" id="pill-h4">H4: —</span>
              <span class="compass-pill pill-side" id="pill-h1">H1: —</span>
            </div>
            <span class="hud-capsule-sep">•</span>
            <span class="hud-capsule-item" id="hud-session">LONDON</span>
            <span class="hud-capsule-sep">•</span>
            <span class="hud-capsule-item">ADX <strong id="hud-adx" class="hud-highlight">—</strong></span>
            <span class="hud-capsule-sep">•</span>
            <span class="hud-capsule-badge" id="hud-state">—</span>
            <span class="hud-capsule-sep">•</span>
            <span class="hud-capsule-pat" id="hud-pattern-capsule">
              <strong id="hud-pattern-name">—</strong>
            </span>
            <!-- Hidden fallback nodes to maintain backward compatibility -->
            <span id="hud-upper-slope" style="display:none;"></span>
            <span id="hud-lower-slope" style="display:none;"></span>
            <span id="hud-pattern-tau" style="display:none;"></span>
            <span id="hud-wave-regime" style="display:none;"></span>
            <span id="hud-rollover" style="display:none;"></span>
          </div>
        </div>
      </div>
    </div>

    <!-- BOTTOM DRAWER -->
    <div class="bottom-drawer bottom-collapsed" id="bottom-drawer">
      <div class="drawer-tabs">
        <div class="drawer-tab-group">
          <div class="drawer-tab active" data-drawer="orders">MT5 Live Positions & Pending</div>
          <div class="drawer-tab" data-drawer="cbss">CBSS Currency Baskets Matrix</div>
          <div class="drawer-tab" data-drawer="telemetry">Radar Telemetry (M1A, M1B, M2, M3, M4)</div>
          <div class="drawer-tab" data-drawer="predictive">Where to Wait (Next Stations)</div>
        </div>
        <div class="drawer-toggle-box" style="gap:4px;">
          <button id="btn-maximize-bottom" class="btn-toggle-panel" onclick="toggleMaximizeDrawer()" title="Perbesar Maksimal (Fullscreen / Normal)"><span class="material-symbols-outlined" style="font-size:12px;vertical-align:-1px;">open_in_full</span></button>
          <button id="btn-toggle-bottom" class="btn-toggle-panel" onclick="toggleBottomDrawer()" title="Sembunyikan / Buka Drawer"><span class="material-symbols-outlined" style="font-size:12px;vertical-align:-1px;">expand_less</span></button>
        </div>
      </div>
      <div class="drawer-body" id="drawer-content">
        <!-- Content injected via JS -->
      </div>
    </div>
  </div>

  <!-- RIGHT: 7-GATE X-RAY SURVEILLANCE -->
  <div class="right-panel">
    <div class="panel-header" onclick="if(document.querySelector('.workspace').classList.contains('xray-collapsed')) toggleXrayPanel();">
      <div style="display:flex;align-items:center;gap:6px;">
        <button id="btn-toggle-xray" class="btn-toggle-xray" onclick="event.stopPropagation(); toggleXrayPanel();" title="Toggle Decision Gates Audit (X-Ray)"><span class="material-symbols-outlined" style="font-size:11px;vertical-align:-1px;">chevron_right</span></button>
        <span class="panel-title">Decision Gates Audit (X-Ray)</span>
      </div>
      <span id="gate-symbol-label" style="font-family:var(--font-mono);font-size:10px;color:var(--cyan);">—</span>
    </div>
    <div class="gate-scroll" id="gates-container">
      <!-- 7 Gate cards injected via JS -->
    </div>
    <div class="xray-collapsed-label" onclick="toggleXrayPanel()">
      DECISION GATES X-RAY
    </div>
  </div>

</div>

<script>
// State Management
let currentSymbol = "EURCAD-ECNc";
let currentTF = "H1";
let currentFilter = "all";
let currentDrawerTab = "orders";
let activeVerticalFilter = "regimes"; // "sessions", "regimes", "both", "off"
let activeZcePreset = "primary"; // "primary", "macro", "all", "off", "custom"
let filterShowRadar = true;
let filterShowPatterns = true;
let filterShowEMA = true;
let filterChipF1C1 = true;
let filterChipF2C2 = false;
let filterChipEXT = false;
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

function updateMiniLegend() {
  const legendEl = document.getElementById("chart-mini-legend");
  const sepEl = document.getElementById("chart-mini-legend-sep");
  if (!legendEl) return;

  if (activeVerticalFilter === "off") {
    legendEl.style.display = "none";
    if (sepEl) sepEl.style.display = "none";
    return;
  }

  legendEl.style.display = "flex";
  if (sepEl) sepEl.style.display = "inline";
  let html = "";

  const isBtc = currentSymbol.toUpperCase().includes("BTC");

  if (activeVerticalFilter === "sessions" || activeVerticalFilter === "both") {
    if (isBtc) {
      html += `
        <div class="mini-legend-item" title="24/7 Crypto Trading: Bebas Dead Zone & Asian Lock"><span class="mini-legend-dot" style="background:#3b82f6;"></span><span>Crypto 24/7 (Active)</span></div>
      `;
    } else {
      html += `
        <div class="mini-legend-item" title="00:00-08:00 WIB: Rollover & Likuiditas Tipis (Hard Block)"><span class="mini-legend-dot" style="background:#ef4444;"></span><span>Dead Zone (Block)</span></div>
        <div class="mini-legend-item" title="08:00-14:00 WIB: Non-Asian driver FX terkunci"><span class="mini-legend-dot" style="background:#f59e0b;"></span><span>Asian Locked</span></div>
        <div class="mini-legend-item" title="08:00-14:00 WIB: JPY/AUD/NZD diizinkan trade"><span class="mini-legend-dot" style="background:#10b981;"></span><span>Asian Driver</span></div>
        <div class="mini-legend-item" title="14:00-23:00 WIB: London & Overlap Peak Liquidity"><span class="mini-legend-dot" style="background:#0ea5e9;"></span><span>Expansion</span></div>
      `;
    }
  }

  if (activeVerticalFilter === "both") {
    html += `<span style="color:var(--border-strong);margin:0 2px;">|</span>`;
  }

  if (activeVerticalFilter === "regimes" || activeVerticalFilter === "both") {
    html += `
      <div class="mini-legend-item" title="Konsolidasi < 24h: Universal Sweeps & Mean Reversion Valid"><span class="mini-legend-dot" style="background:#38bdf8;"></span><span>Young &lt;24h (Sweep)</span></div>
      <div class="mini-legend-item" title="Konsolidasi 24-72h: Squeeze Maturing, Wajib SL H4"><span class="mini-legend-dot" style="background:#f59e0b;"></span><span>Mature 24-72h</span></div>
      <div class="mini-legend-item" title="Konsolidasi > 72h / Triangle: Sweeps Dilarang, Breakout Imminent"><span class="mini-legend-dot" style="background:#ec4899;"></span><span>Super &gt;72h (Breakout)</span></div>
    `;
  }

  legendEl.innerHTML = html;
}

function renderVerticalShading() {
  if (!shadingCanvas || !shadingCtx || !chart || !cachedSymbolData || !cachedSymbolData.candles) return;
  const container = document.getElementById("tv-chart");
  const width = container.clientWidth;
  const height = container.clientHeight;

  shadingCtx.clearRect(0, 0, width, height);
  updateMiniLegend();

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

        // 1. Session vertical shading (Context-Aware Execution Window)
        if (activeVerticalFilter === "sessions" || activeVerticalFilter === "both") {
          let sessionColor = c.session_color || null;
          const isBlocked = (c.session_status === "BLOCKED");

          if (!sessionColor) {
            if (c.session_type === "CRYPTO_247" || c.session === "CRYPTO") sessionColor = "rgba(59, 130, 246, 0.07)";
            else if (c.session_type === "DEAD_ZONE" || c.session === "DEAD_ZONE") sessionColor = "rgba(239, 68, 68, 0.075)";
            else if (c.session_type === "FRIDAY_LOCK" || c.session === "CLOSED") sessionColor = "rgba(239, 68, 68, 0.09)";
            else if (c.session_type === "ASIAN_LOCKED" || c.session === "TOKYO_LOCK") sessionColor = "rgba(245, 158, 11, 0.075)";
            else if (c.session_type === "ASIAN_ACTIVE" || c.session === "TOKYO") sessionColor = "rgba(16, 185, 129, 0.065)";
            else if (c.session_type === "LONDON_EXPANSION" || c.session === "LONDON") sessionColor = "rgba(14, 165, 233, 0.065)";
            else if (c.session_type === "NY_OVERLAP" || c.session === "OVERLAP") sessionColor = "rgba(168, 85, 247, 0.075)";
            else if (c.session_type === "LATE_NY" || c.session === "LATE_NY") sessionColor = "rgba(99, 102, 241, 0.055)";
          }

          if (sessionColor) {
            shadingCtx.fillStyle = sessionColor;
            shadingCtx.fillRect(x1, 0, barW, height);

            // Top Execution Permission Stripe (3px)
            if (isBlocked) {
              shadingCtx.fillStyle = "rgba(239, 68, 68, 0.85)";
              shadingCtx.fillRect(x1, 0, barW, 3);
            } else if (c.session_status === "PERMITTED") {
              const pStripe = (c.session_type === "ASIAN_ACTIVE") ? "rgba(16, 185, 129, 0.85)" :
                              (c.session_type === "CRYPTO_247" ? "rgba(59, 130, 246, 0.85)" : "rgba(14, 165, 233, 0.85)");
              shadingCtx.fillStyle = pStripe;
              shadingCtx.fillRect(x1, 0, barW, 3);
            }
          }
        }

        // 2. Macro Wave Consolidation Age Regime (wave_regime.py)
        if (activeVerticalFilter === "regimes" || activeVerticalFilter === "both") {
          let regimeColor = null;
          let stripeColor = null;
          const reg = c.regime || "YOUNG_OSCILLATION";

          if (reg === "SUPER_COMPRESSION" || reg === "SUPER_COMPRESSION_THRUST") {
            regimeColor = "rgba(236, 72, 153, 0.085)"; // Magenta / Deep Pink
            stripeColor = "rgba(236, 72, 153, 0.85)";
          } else if (reg === "MATURE_SQUEEZE") {
            regimeColor = "rgba(245, 158, 11, 0.070)"; // Amber / Gold
            stripeColor = "rgba(245, 158, 11, 0.80)";
          } else {
            // YOUNG_OSCILLATION (< 24h)
            regimeColor = "rgba(56, 189, 248, 0.055)"; // Soft Sky Cyan
            stripeColor = "rgba(56, 189, 248, 0.70)";
          }

          if (regimeColor) {
            shadingCtx.fillStyle = regimeColor;
            shadingCtx.fillRect(x1, 0, barW, height);
            // Bottom 3px Wave Regime Indicator Stripe
            shadingCtx.fillStyle = stripeColor;
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
      // Hard Lock: Sisi kiri 100% khusus ZCE, drop seluruh label M1..M4
      if (lvl.label && (lvl.label.startsWith("[M1") || lvl.label.startsWith("[M2") || lvl.label.startsWith("[M3") || lvl.label.startsWith("[M4") || lvl.label.includes("Macro SFP") || lvl.label.includes("Pullback") || lvl.label.includes("Retest)"))) {
        return;
      }
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

      // Save bounding box for interactive hover micro-popup
      lvl.box = { x: badgeX, y: badgeY, w: txtW + 12, h: badgeH };

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

  // 4. (W1 Descending Slope rendered cleanly as horizontal price line in renderChartLevels)

  // 5. Render Macro H4 Structural Swings & Pattern Corridor
  if (filterShowPatterns && cachedSymbolData && cachedSymbolData.envelope_visual && candleSeries && chart) {
    const timeScale = chart.timeScale();
    const ev = cachedSymbolData.envelope_visual;
    const ss = ev.swing_structure || {};
    const uBody = ev.upper_body || [];
    const lBody = ev.lower_body || [];

    // 5a. Render HTF Dealing Range & Equilibrium Bands (SMC Foundation)
    const dr = ev.dealing_range || ss.dealing_range || null;
    const dol = ev.draw_on_liquidity || ss.draw_on_liquidity || null;
    const oflow = ev.order_flow || ss.order_flow || null;

    if (dr && dr.range_high > 0 && dr.range_low > 0) {
      const yHigh = candleSeries.priceToCoordinate(dr.range_high);
      const yLow = candleSeries.priceToCoordinate(dr.range_low);
      const yEq = candleSeries.priceToCoordinate(dr.equilibrium_50);
      const span = dr.range_high - dr.range_low;
      const f382 = dr.fib_382 || (dr.range_low + 0.382 * span);
      const f618 = dr.fib_618 || (dr.range_low + 0.618 * span);
      const y382 = candleSeries.priceToCoordinate(f382);
      const y618 = candleSeries.priceToCoordinate(f618);

      if (yHigh !== null && yLow !== null && yEq !== null) {
        // Deep Premium Zone (yHigh down to y618) - Institutional OTE Sell
        if (y618 !== null) {
          shadingCtx.fillStyle = "rgba(244, 63, 94, 0.04)";
          shadingCtx.fillRect(0, yHigh, width, Math.max(0, y618 - yHigh));
        }

        // Shallow Premium Inducement Corridor (y618 down to yEq)
        if (y618 !== null) {
          shadingCtx.fillStyle = "rgba(245, 158, 11, 0.025)";
          shadingCtx.fillRect(0, y618, width, Math.max(0, yEq - y618));
        }

        // Shallow Discount Inducement Corridor (yEq down to y382)
        if (y382 !== null) {
          shadingCtx.fillStyle = "rgba(245, 158, 11, 0.025)";
          shadingCtx.fillRect(0, yEq, width, Math.max(0, y382 - yEq));
        }

        // Deep Discount Zone (y382 down to yLow) - Institutional OTE Buy
        if (y382 !== null) {
          shadingCtx.fillStyle = "rgba(16, 185, 129, 0.04)";
          shadingCtx.fillRect(0, y382, width, Math.max(0, yLow - y382));
        }

        // 1. Dealing Range High (BSL External Pool)
        shadingCtx.beginPath();
        shadingCtx.setLineDash([6, 4]);
        shadingCtx.lineWidth = 1.6;
        shadingCtx.strokeStyle = "rgba(192, 132, 252, 0.85)"; // Purple BSL
        shadingCtx.moveTo(10, yHigh);
        shadingCtx.lineTo(width - 25, yHigh);
        shadingCtx.stroke();

        // High Pill Label
        const bslTxt = `RANGE HIGH (BSL) ${dr.range_high.toFixed(cachedSymbolData.digits || 5)}${dr.high_confirmed ? ' [CONFIRMED]' : ''}`;
        shadingCtx.font = "bold 9px 'JetBrains Mono', monospace";
        const bslW = shadingCtx.measureText(bslTxt).width;
        shadingCtx.fillStyle = "rgba(15, 23, 42, 0.90)";
        shadingCtx.fillRect(width - bslW - 35, yHigh - 15, bslW + 8, 13);
        shadingCtx.fillStyle = "#c084fc";
        shadingCtx.fillText(bslTxt, width - bslW - 31, yHigh - 5);

        // 2. 61.8% OTE Line (Subtle hairline)
        if (y618 !== null) {
          shadingCtx.beginPath();
          shadingCtx.setLineDash([2, 4]);
          shadingCtx.lineWidth = 0.7;
          shadingCtx.strokeStyle = "rgba(192, 132, 252, 0.35)";
          shadingCtx.moveTo(10, y618);
          shadingCtx.lineTo(width - 25, y618);
          shadingCtx.stroke();

          const oteTxt = `61.8% OTE ${f618.toFixed(cachedSymbolData.digits || 5)}`;
          shadingCtx.font = "bold 8px 'JetBrains Mono', monospace";
          const oteW = shadingCtx.measureText(oteTxt).width;
          shadingCtx.fillStyle = "rgba(15, 23, 42, 0.75)";
          shadingCtx.fillRect(width - oteW - 35, y618 - 6, oteW + 6, 12);
          shadingCtx.fillStyle = "rgba(192, 132, 252, 0.65)";
          shadingCtx.fillText(oteTxt, width - oteW - 32, y618 + 3);
        }

        // 3. 50% Equilibrium Line
        shadingCtx.beginPath();
        shadingCtx.setLineDash([3, 3]);
        shadingCtx.lineWidth = 1.0;
        shadingCtx.strokeStyle = "rgba(148, 163, 184, 0.70)"; // Slate Hairline
        shadingCtx.moveTo(10, yEq);
        shadingCtx.lineTo(width - 25, yEq);
        shadingCtx.stroke();

        // EQ Pill Label
        const eqTxt = `50% EQ ${dr.equilibrium_50.toFixed(cachedSymbolData.digits || 5)} [${dr.zone_status}]`;
        shadingCtx.font = "bold 9px 'JetBrains Mono', monospace";
        const eqW = shadingCtx.measureText(eqTxt).width;
        shadingCtx.fillStyle = "rgba(15, 23, 42, 0.88)";
        shadingCtx.fillRect(width - eqW - 35, yEq - 7, eqW + 8, 13);
        shadingCtx.fillStyle = dr.zone_status.includes("PREMIUM") ? "#f43f5e" : (dr.zone_status.includes("INDUCEMENT") ? "#f59e0b" : "#10b981");
        shadingCtx.fillText(eqTxt, width - eqW - 31, yEq + 3);

        // 4. 38.2% Inducement Boundary Line (Subtle hairline)
        if (y382 !== null) {
          shadingCtx.beginPath();
          shadingCtx.setLineDash([2, 4]);
          shadingCtx.lineWidth = 0.7;
          shadingCtx.strokeStyle = "rgba(56, 189, 248, 0.35)";
          shadingCtx.moveTo(10, y382);
          shadingCtx.lineTo(width - 25, y382);
          shadingCtx.stroke();

          const indTxt = `38.2% INDUCEMENT ${f382.toFixed(cachedSymbolData.digits || 5)}`;
          shadingCtx.font = "bold 8px 'JetBrains Mono', monospace";
          const indW = shadingCtx.measureText(indTxt).width;
          shadingCtx.fillStyle = "rgba(15, 23, 42, 0.75)";
          shadingCtx.fillRect(width - indW - 35, y382 - 6, indW + 6, 12);
          shadingCtx.fillStyle = "rgba(56, 189, 248, 0.65)";
          shadingCtx.fillText(indTxt, width - indW - 32, y382 + 3);
        }

        // 5. Dealing Range Low (SSL External Pool)
        shadingCtx.beginPath();
        shadingCtx.setLineDash([6, 4]);
        shadingCtx.lineWidth = 1.6;
        shadingCtx.strokeStyle = "rgba(56, 189, 248, 0.85)"; // Sky Blue SSL
        shadingCtx.moveTo(10, yLow);
        shadingCtx.lineTo(width - 25, yLow);
        shadingCtx.stroke();

        // Low Pill Label
        const sslTxt = `RANGE LOW (SSL) ${dr.range_low.toFixed(cachedSymbolData.digits || 5)}${dr.low_confirmed ? ' [CONFIRMED]' : ''}`;
        const sslW = shadingCtx.measureText(sslTxt).width;
        shadingCtx.fillStyle = "rgba(15, 23, 42, 0.90)";
        shadingCtx.fillRect(width - sslW - 35, yLow + 2, sslW + 8, 13);
        shadingCtx.fillStyle = "#38bdf8";
        shadingCtx.fillText(sslTxt, width - sslW - 31, yLow + 12);

        shadingCtx.setLineDash([]);
      }
    }

    // 5b. Render Structural Channel Envelope Rails (High-to-High Ceiling & Low-to-Low Floor)
    // Upper Rail (Plafon: High to High)
    const upperSegments = ss.all_upper_segments || [];
    if (upperSegments.length > 0) {
      shadingCtx.beginPath();
      shadingCtx.setLineDash([4, 3]);
      shadingCtx.lineWidth = 1.4;
      shadingCtx.strokeStyle = "rgba(251, 191, 36, 0.75)"; // Amber / Gold Ceiling Rail
      upperSegments.forEach(seg => {
        const p1 = seg.p1;
        const p2 = seg.p2;
        if (p1 && p2) {
          const x1 = p1.time > 0 ? timeScale.timeToCoordinate(p1.time) : null;
          const y1 = candleSeries.priceToCoordinate(p1.price);
          const x2 = p2.time > 0 ? timeScale.timeToCoordinate(p2.time) : null;
          const y2 = candleSeries.priceToCoordinate(p2.price);

          if (x1 !== null && y1 !== null && x2 !== null && y2 !== null) {
            shadingCtx.moveTo(x1, y1);
            shadingCtx.lineTo(x2, y2);
          }
        }
      });
      shadingCtx.stroke();
      shadingCtx.setLineDash([]);
    }

    // Lower Rail (Lantai: Low to Low)
    const lowerSegments = ss.all_lower_segments || [];
    if (lowerSegments.length > 0) {
      shadingCtx.beginPath();
      shadingCtx.setLineDash([4, 3]);
      shadingCtx.lineWidth = 1.4;
      shadingCtx.strokeStyle = "rgba(56, 189, 248, 0.75)"; // Sky Blue Floor Rail
      lowerSegments.forEach(seg => {
        const p1 = seg.p1;
        const p2 = seg.p2;
        if (p1 && p2) {
          const x1 = p1.time > 0 ? timeScale.timeToCoordinate(p1.time) : null;
          const y1 = candleSeries.priceToCoordinate(p1.price);
          const x2 = p2.time > 0 ? timeScale.timeToCoordinate(p2.time) : null;
          const y2 = candleSeries.priceToCoordinate(p2.price);

          if (x1 !== null && y1 !== null && x2 !== null && y2 !== null) {
            shadingCtx.moveTo(x1, y1);
            shadingCtx.lineTo(x2, y2);
          }
        }
      });
      shadingCtx.stroke();
      shadingCtx.setLineDash([]);
    }

    // 5c. Draw on Liquidity (DOL) Magnet Flag on Live Bar
    if (dol && dol.target_price > 0 && candleSeries) {
      const yDol = candleSeries.priceToCoordinate(dol.target_price);
      if (yDol !== null) {
        const xDol = width - 25;
        shadingCtx.beginPath();
        shadingCtx.arc(xDol, yDol, 4.5, 0, 2 * Math.PI);
        shadingCtx.fillStyle = dol.direction.includes("BSL") ? "#c084fc" : "#38bdf8";
        shadingCtx.fill();
        shadingCtx.lineWidth = 1.2;
        shadingCtx.strokeStyle = "#ffffff";
        shadingCtx.stroke();
      }
    }

    // 5d. Pivot Point Circles & Labels (HH / LH, HL / LL) with Anti-Collision
    const peaks = ss.peaks || [];
    const troughs = ss.troughs || [];

    // Peaks markers
    let lastPeakX = -999;
    peaks.forEach(pk => {
      const x = pk.time > 0 ? timeScale.timeToCoordinate(pk.time) : null;
      const y = candleSeries.priceToCoordinate(pk.price);
      if (x !== null && y !== null) {
        const isDense = (Math.abs(x - lastPeakX) < 28);
        if (!isDense) lastPeakX = x;

        shadingCtx.beginPath();
        shadingCtx.arc(x, y, isDense ? 2.0 : 3.5, 0, 2 * Math.PI);
        shadingCtx.fillStyle = "#fbbf24";
        shadingCtx.fill();
        shadingCtx.lineWidth = 1.2;
        shadingCtx.strokeStyle = "#0f172a";
        shadingCtx.stroke();

        if (!isDense) {
          const lbl = pk.label || "H";
          const bgCol = lbl === "HH" ? "rgba(16, 185, 129, 0.90)" : (lbl === "LH" ? "rgba(244, 63, 94, 0.90)" : "rgba(251, 191, 36, 0.90)");
          shadingCtx.font = "bold 8.5px 'JetBrains Mono', monospace";
          const lblW = shadingCtx.measureText(lbl).width;
          shadingCtx.fillStyle = bgCol;
          shadingCtx.fillRect(x - lblW / 2 - 3, y - 16, lblW + 6, 11);
          shadingCtx.fillStyle = "#ffffff";
          shadingCtx.fillText(lbl, x - lblW / 2, y - 7);
        }
      }
    });

    // Troughs markers
    let lastTroughX = -999;
    troughs.forEach(tr => {
      const x = tr.time > 0 ? timeScale.timeToCoordinate(tr.time) : null;
      const y = candleSeries.priceToCoordinate(tr.price);
      if (x !== null && y !== null) {
        const isDense = (Math.abs(x - lastTroughX) < 28);
        if (!isDense) lastTroughX = x;

        shadingCtx.beginPath();
        shadingCtx.arc(x, y, isDense ? 2.0 : 3.5, 0, 2 * Math.PI);
        shadingCtx.fillStyle = "#38bdf8";
        shadingCtx.fill();
        shadingCtx.lineWidth = 1.2;
        shadingCtx.strokeStyle = "#0f172a";
        shadingCtx.stroke();

        if (!isDense) {
          const lbl = tr.label || "L";
          const bgCol = lbl === "HL" ? "rgba(16, 185, 129, 0.90)" : (lbl === "LL" ? "rgba(244, 63, 94, 0.90)" : "rgba(56, 189, 248, 0.90)");
          shadingCtx.font = "bold 8.5px 'JetBrains Mono', monospace";
          const lblW = shadingCtx.measureText(lbl).width;
          shadingCtx.fillStyle = bgCol;
          shadingCtx.fillRect(x - lblW / 2 - 3, y + 6, lblW + 6, 11);
          shadingCtx.fillStyle = "#ffffff";
          shadingCtx.fillText(lbl, x - lblW / 2, y + 15);
        }
      }
    });

    shadingCtx.restore();
  }

  // 6. Render Historical M1..M4 Strategy Audit Markers (Dealing Range Intersection)
  if (filterShowRadar && cachedSymbolData && cachedSymbolData.strategy_audit_markers && candleSeries && chart) {
    const timeScale = chart.timeScale();
    const markers = cachedSymbolData.strategy_audit_markers;
    shadingCtx.save();
    shadingCtx.font = "bold 9px 'JetBrains Mono', monospace";
    shadingCtx.textBaseline = "middle";

    markers.forEach(m => {
      const x = timeScale.timeToCoordinate(m.time);
      if (x === null || x < -30 || x > width + 30) {
        m.box = null;
        return;
      }

      const y = candleSeries.priceToCoordinate(m.price);
      if (y === null) {
        m.box = null;
        return;
      }

      const isBuy = (m.direction === "BUY");
      let baseColor = "#38bdf8";
      let shortTag = m.label || m.type || "M";

      if (m.type === "M1A" || m.type === "M1_SWEEP" || m.type === "M1") {
        baseColor = isBuy ? "#10b981" : "#f43f5e";
        shortTag = isBuy ? "▲ M1A" : "▼ M1A";
      } else if (m.type === "M1B" || m.type === "M1B_INDUCEMENT") {
        baseColor = "#f59e0b";
        shortTag = isBuy ? "▲ M1B" : "▼ M1B";
      } else if (m.type === "M2" || m.type === "M2_PULLBACK") {
        baseColor = isBuy ? "#06b6d4" : "#818cf8";
        shortTag = isBuy ? "▲ M2" : "▼ M2";
      } else if (m.type === "M3" || m.type === "M3_RETEST") {
        baseColor = isBuy ? "#a855f7" : "#c084fc";
        shortTag = isBuy ? "▲ M3" : "▼ M3";
      } else if (m.type === "M4" || m.type === "M4_EXPANSION") {
        baseColor = "#fbbf24";
        shortTag = isBuy ? "▲ M4" : "▼ M4";
      }

      const txt = shortTag;
      const metrics = shadingCtx.measureText(txt);
      const pillW = metrics.width + 12;
      const pillH = 15;
      const pillX = x - pillW / 2;
      const pillY = isBuy ? (y + 10) : (y - pillH - 10);

      // Save bounding box for mouse hover tooltip
      m.box = { x: pillX, y: pillY, w: pillW, h: pillH, color: baseColor };

      // Micro dashed line connecting badge to candle extreme
      shadingCtx.beginPath();
      shadingCtx.strokeStyle = baseColor;
      shadingCtx.lineWidth = 1;
      shadingCtx.setLineDash([2, 2]);
      shadingCtx.moveTo(x, y);
      shadingCtx.lineTo(x, isBuy ? pillY : (pillY + pillH));
      shadingCtx.stroke();
      shadingCtx.setLineDash([]);

      // Draw Pill background
      shadingCtx.fillStyle = "rgba(11, 14, 20, 0.94)";
      shadingCtx.fillRect(pillX, pillY, pillW, pillH);

      // Draw left accent border indicator
      shadingCtx.fillStyle = baseColor;
      shadingCtx.fillRect(pillX, pillY, 2.5, pillH);

      // Outline pill border
      shadingCtx.strokeStyle = baseColor;
      shadingCtx.lineWidth = 1;
      shadingCtx.strokeRect(pillX, pillY, pillW, pillH);

      // Text label
      shadingCtx.fillStyle = baseColor;
      shadingCtx.fillText(txt, pillX + 6, pillY + pillH / 2);
    });

    shadingCtx.restore();
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

  ema20Series = chart.addLineSeries({
    color: "#00e5ff",
    lineWidth: 1,
    title: "",
    priceLineVisible: false,
    lastValueVisible: false
  });
  ema50Series = chart.addLineSeries({
    color: "#ffd740",
    lineWidth: 1,
    title: "",
    priceLineVisible: false,
    lastValueVisible: false
  });
  ema200Series = chart.addLineSeries({
    color: "#b388ff",
    lineWidth: 1.5,
    title: "",
    priceLineVisible: false,
    lastValueVisible: false
  });

  initOverlayCanvas();

  chart.timeScale().subscribeVisibleLogicalRangeChange(renderVerticalShading);

  // Redraw labels immediately on pan, zoom, or scale drag
  container.addEventListener("wheel", () => {
    requestAnimationFrame(renderVerticalShading);
  }, { passive: true });

  container.addEventListener("pointermove", (e) => {
    if (e.buttons > 0) requestAnimationFrame(renderVerticalShading);
  });

  // Interactive Hover Micro-Popup on ZCE Level Badges
  const chartWrapper = container.parentElement;
  const tooltipEl = document.getElementById("zce-hover-tooltip");

  if (chartWrapper && tooltipEl) {
    chartWrapper.addEventListener("pointermove", (e) => {
      const rect = chartWrapper.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;

      // 1. Check Strategy Audit Marker hover (M1..M4 historical triggers)
      let hoveredMarker = null;
      if (filterShowRadar && cachedSymbolData && cachedSymbolData.strategy_audit_markers) {
        for (let j = 0; j < cachedSymbolData.strategy_audit_markers.length; j++) {
          const mk = cachedSymbolData.strategy_audit_markers[j];
          if (mk.box && mx >= mk.box.x && mx <= mk.box.x + mk.box.w && my >= mk.box.y && my <= mk.box.y + mk.box.h) {
            hoveredMarker = mk;
            break;
          }
        }
      }

      if (hoveredMarker) {
        chartWrapper.style.cursor = "pointer";
        const isB = (hoveredMarker.direction === "BUY");
        const dirBadge = isB ? '<span style="color:#10b981;font-weight:bold;">BUY</span>' : '<span style="color:#f43f5e;font-weight:bold;">SELL</span>';
        const dDigits = cachedSymbolData ? (cachedSymbolData.digits || 5) : 5;
        const touchHtml = (hoveredMarker.touch_count && hoveredMarker.touch_count > 1)
          ? `<div style="display:flex;align-items:center;gap:6px;margin:4px 0 3px 0;font-size:10px;color:#fbbf24;font-weight:600;"><span style="background:rgba(251,191,36,0.15);padding:1px 6px;border-radius:3px;border:1px solid rgba(251,191,36,0.4);">⚡ Touch Count: ${hoveredMarker.touch_count}x</span><span style="color:#cbd5e1;">(Level tested ${hoveredMarker.touch_count} times)</span></div>`
          : ((hoveredMarker.type === "M3" || hoveredMarker.type === "M1B") ? `<div style="margin:4px 0 3px 0;font-size:10px;color:#94a3b8;"><span style="background:rgba(148,163,184,0.12);padding:1px 6px;border-radius:3px;">⚡ Touch Count: 1st Test</span></div>` : '');
        const verdictBadge = `<span style="background:rgba(16,185,129,0.16);color:#10b981;padding:1px 6px;border-radius:3px;font-weight:700;font-size:9px;letter-spacing:0.4px;border:1px solid rgba(16,185,129,0.3);">✓ 8-GATE PASS [A+ VALID]</span>`;
        const metricsHtml = (hoveredMarker.runway_atr !== undefined)
          ? `<div style="display:flex;flex-wrap:wrap;gap:8px;font-size:10px;color:#94a3b8;margin:5px 0 3px 0;border-top:1px dashed rgba(255,255,255,0.1);padding-top:4px;">
               <span>Runway: <b style="color:#38bdf8;">${hoveredMarker.runway_atr}x ATR</b></span>
               ${hoveredMarker.rr ? `<span>Net R:R: <b style="color:#10b981;">1:${hoveredMarker.rr}</b></span>` : ''}
               ${hoveredMarker.sl ? `<span>SL: <b style="color:#f43f5e;">${hoveredMarker.sl}</b></span>` : ''}
               ${hoveredMarker.tp ? `<span>TP: <b style="color:#10b981;">${hoveredMarker.tp}</b></span>` : ''}
             </div>`
          : '';
        tooltipEl.innerHTML = `
          <div class="zce-tt-header">
            <span class="zce-tt-tier" style="color:${hoveredMarker.box.color};">${hoveredMarker.label} [${dirBadge}] @ ${hoveredMarker.price.toFixed(dDigits)}</span>
            <span class="zce-tt-score">DR ${hoveredMarker.dr_pos_pct}%</span>
          </div>
          <div style="margin:3px 0 2px 0;">${verdictBadge}</div>
          ${touchHtml}
          <div class="zce-tt-confluences">${hoveredMarker.reason}</div>
          ${metricsHtml}
          <div class="zce-tt-meta" style="margin-top:4px;">
            <span>Zone: <b style="color:${hoveredMarker.box.color};">${hoveredMarker.zone}</b></span>
            <span>${hoveredMarker.bar_age} bars ago</span>
          </div>
        `;
        tooltipEl.style.display = "block";
        tooltipEl.style.left = `${Math.min(rect.width - 290, Math.max(10, hoveredMarker.box.x + hoveredMarker.box.w + 10))}px`;
        tooltipEl.style.top = `${Math.max(10, Math.min(rect.height - 145, hoveredMarker.box.y - 10))}px`;
        return;
      }

      if (!activeRenderedLevels || activeRenderedLevels.length === 0) {
        tooltipEl.style.display = "none";
        return;
      }

      let hoveredLevel = null;
      for (let i = 0; i < activeRenderedLevels.length; i++) {
        const lvl = activeRenderedLevels[i];
        if (lvl.box) {
          if (mx >= lvl.box.x && mx <= lvl.box.x + lvl.box.w &&
              my >= lvl.box.y && my <= lvl.box.y + lvl.box.h) {
            hoveredLevel = lvl;
            break;
          }
        }
      }

      if (hoveredLevel) {
        chartWrapper.style.cursor = "pointer";
        let pipsDiff = "";
        if (cachedSymbolData && cachedSymbolData.bid) {
          const pt = (cachedSymbolData.digits === 3 || cachedSymbolData.digits === 5) ? 0.0001 : 0.01;
          const diffPips = ((hoveredLevel.price - cachedSymbolData.bid) / pt).toFixed(1);
          pipsDiff = `${diffPips >= 0 ? '+' : ''}${diffPips}p from live`;
        }
        tooltipEl.innerHTML = `
          <div class="zce-tt-header">
            <span class="zce-tt-tier" style="color:${hoveredLevel.color};">${hoveredLevel.tier} ${hoveredLevel.grade_str} @ ${hoveredLevel.price.toFixed(cachedSymbolData ? cachedSymbolData.digits : 5)}</span>
            <span class="zce-tt-score">${hoveredLevel.score > 0 ? hoveredLevel.score.toFixed(1) + ' pts' : ''}</span>
          </div>
          <div class="zce-tt-confluences">${hoveredLevel.confluences}</div>
          <div class="zce-tt-meta">
            <span>${hoveredLevel.is_slope ? `TF: W1 (${hoveredLevel.sources_count} touches)` : `TFs: ${hoveredLevel.timeframes || 'H1'} (${hoveredLevel.sources_count} src)`}</span>
            <span>${pipsDiff}</span>
          </div>
        `;
        tooltipEl.style.display = "block";
        tooltipEl.style.left = `${hoveredLevel.box.x + hoveredLevel.box.w + 10}px`;
        tooltipEl.style.top = `${Math.max(10, Math.min(rect.height - 90, hoveredLevel.box.y - 10))}px`;
      } else {
        chartWrapper.style.cursor = "default";
        tooltipEl.style.display = "none";
      }
    });

    chartWrapper.addEventListener("pointerleave", () => {
      tooltipEl.style.display = "none";
      chartWrapper.style.cursor = "default";
    });
  }

  // Zero-glitch responsive resizing via ResizeObserver & window resize
  window.addEventListener("resize", () => {
    if (container && container.clientWidth > 0 && container.clientHeight > 0) {
      chart.resize(container.clientWidth, container.clientHeight);
      resizeOverlayCanvas();
    }
  });

  document.addEventListener("fullscreenchange", () => {
    setTimeout(() => {
      if (container && container.clientWidth > 0 && container.clientHeight > 0) {
        chart.resize(container.clientWidth, container.clientHeight);
        resizeOverlayCanvas();
      }
    }, 80);
  });

  if (window.ResizeObserver) {
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const cr = entry.contentRect;
        if (cr.width > 0 && cr.height > 0 && chart) {
          chart.resize(cr.width, cr.height);
          resizeOverlayCanvas();
        }
      }
    });
    ro.observe(container);
  }
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

  const rawLadder = (data.zce_walls && data.zce_walls.length > 0) ? data.zce_walls : (data.zce_ladder || []);
  let filteredLadder = [];

  // Guarantee primary floor and ceiling fallbacks
  let primaryFloor = rawLadder.find(w => w.tier === "F1");
  if (!primaryFloor) {
    const fls = rawLadder.filter(w => w.type === "floor" || (w.tier && w.tier.startsWith("F")));
    if (fls.length > 0) primaryFloor = fls[0];
  }
  let primaryCeil = rawLadder.find(w => w.tier === "C1");
  if (!primaryCeil) {
    const cls = rawLadder.filter(w => w.type === "ceiling" || w.type === "ceil" || (w.tier && w.tier.startsWith("C")));
    if (cls.length > 0) primaryCeil = cls[0];
  }

  if (activeZcePreset === "off") {
    filteredLadder = [];
  } else {
    filteredLadder = rawLadder.filter(w => {
      let tierNum = 1;
      const match = (w.tier || "").match(/[CF](\d+)/i);
      if (match) {
        tierNum = parseInt(match[1], 10);
      }

      const isF1C1 = (tierNum === 1) || (w.tier === "F1" || w.tier === "C1") || (primaryFloor && w === primaryFloor) || (primaryCeil && w === primaryCeil);
      const isF2C2 = (tierNum === 2) || (w.tier === "F2" || w.tier === "C2");
      const isEXT = (tierNum >= 3);

      if (isF1C1) return filterChipF1C1;
      if (isF2C2) return filterChipF2C2;
      if (isEXT) return filterChipEXT;
      return true;
    });
  }

  filteredLadder.forEach(w => {
    const isFloor = (w.type === "floor" || (w.tier && w.tier.startsWith("F")));
    const baseRgb = isFloor ? "56, 189, 248" : "251, 191, 36"; // Cyan / Amber

    // Extract numeric tier (e.g. C1 -> 1, F5 -> 5, C8 -> 8)
    let tierNum = 1;
    const match = (w.tier || "").match(/[CF](\d+)/i);
    if (match) {
      tierNum = parseInt(match[1], 10);
    }

    // Opacity: C1..C3 & F1..F3 = 100% (1.00)
    // C4..C8 & F4..F8: reduced by 10% per tier above 3
    // C4/F4 = 90% (0.90), C5/F5 = 80% (0.80), C6/F6 = 70% (0.70), C7/F7 = 60% (0.60), C8/F8 = 50% (0.50)
    let tierOpacity = 1.0;
    if (tierNum > 3) {
      tierOpacity = Math.max(0.50, 1.0 - (tierNum - 3) * 0.10);
    }

    let color = `rgba(${baseRgb}, ${tierOpacity.toFixed(2)})`;
    let lineWidth = (w.grade === "GRADE_3_MACRO" || tierNum === 1) ? 1.2 : 1;
    let lineStyle = (w.grade === "GRADE_3_MACRO" || tierNum === 1)
      ? LightweightCharts.LineStyle.Solid
      : (w.grade === "GRADE_2_INTERMEDIATE" || tierNum <= 3 ? LightweightCharts.LineStyle.Dashed : LightweightCharts.LineStyle.Dotted);

    const gStr = w.grade === "GRADE_3_MACRO" ? "G3" : (w.grade === "GRADE_2_INTERMEDIATE" ? "G2" : "G1");
    const shortLabel = `${w.tier} [${gStr}] ${w.price.toFixed(data.digits || 5)}`;

    // Build confluences string for hover tooltip
    let confStr = "";
    if (w.confluences && typeof w.confluences === "string" && w.confluences.trim().length > 0) {
      confStr = w.confluences;
    } else if (w.sources && Array.isArray(w.sources) && w.sources.length > 0) {
      confStr = w.sources.slice(0, 4).map(s => typeof s === 'string' ? s : (s.type || s.id || s)).join(" • ");
    } else if (w.confluences && Array.isArray(w.confluences) && w.confluences.length > 0) {
      confStr = w.confluences.join(" • ");
    } else if (w.kinds && Array.isArray(w.kinds) && w.kinds.length > 0) {
      confStr = w.kinds.slice(0, 4).join(" • ");
    } else if (typeof w.confluence_types === "string" && w.confluence_types.trim().length > 0) {
      confStr = w.confluence_types;
    } else {
      confStr = "Structural S/R Anchor";
    }

    let tfsStr = "";
    if (w.timeframes && typeof w.timeframes === "string" && w.timeframes.trim().length > 0) {
      tfsStr = w.timeframes;
    } else if (w.timeframes && Array.isArray(w.timeframes) && w.timeframes.length > 0) {
      tfsStr = w.timeframes.join("+");
    } else if (w.tfs && Array.isArray(w.tfs) && w.tfs.length > 0) {
      tfsStr = w.tfs.join("+");
    } else {
      tfsStr = "H1";
    }

    let srcCount = 1;
    if (typeof w.num_sources === "number" && w.num_sources > 0) srcCount = w.num_sources;
    else if (typeof w.confluence === "number" && w.confluence > 0) srcCount = w.confluence;
    else if (w.sources && Array.isArray(w.sources) && w.sources.length > 0) srcCount = w.sources.length;
    else if (w.kinds && Array.isArray(w.kinds) && w.kinds.length > 0) srcCount = w.kinds.length;

    activeRenderedLevels.push({
      price: w.price,
      color: color,
      label: shortLabel,
      tier: w.tier,
      grade_str: `[${gStr}]`,
      score: (typeof w.score === "number") ? w.score : (w.total_score || 0),
      confluences: confStr,
      timeframes: tfsStr,
      sources_count: srcCount,
      fullLabel: w.label || shortLabel,
      wall: w
    });

    const line = candleSeries.createPriceLine({
      price: w.price,
      color: color,
      lineWidth: lineWidth,
      lineStyle: lineStyle,
      axisLabelVisible: false, // Tidak di-highlight di vertical axis (permintaan user)
      title: "" // Dikosongkan agar sisi kanan (candle live) tidak tertutup
    });
    priceLines.push(line);
  });

  // 1B. W1 Dual-Horizon Descending Slope Ceiling
  if (data.w1_slope_ceiling && data.w1_slope_ceiling > 0) {
    const slopeColor = "#f59e0b"; // Warm Amber
    const slopePrice = data.w1_slope_ceiling;
    const slopeLabel = `W1 SLOPE ${slopePrice.toFixed(data.digits || 5)}`;
    const slopeTouches = (data.w1_slope_touches && data.w1_slope_touches > 0) ? data.w1_slope_touches : 1;

    activeRenderedLevels.push({
      price: slopePrice,
      color: slopeColor,
      label: slopeLabel,
      tier: "W1 SLOPE",
      grade_str: "[MACRO]",
      score: 0,
      confluences: `W1 Major Descending Slope Barrier (Anchor Peak Law • ${slopeTouches} touches)`,
      timeframes: "W1",
      sources_count: slopeTouches,
      is_slope: true,
      fullLabel: `W1 Descending Slope Barrier @ ${slopePrice.toFixed(data.digits || 5)} (${slopeTouches} touches)`
    });

    const slopeLine = candleSeries.createPriceLine({
      price: slopePrice,
      color: slopeColor,
      lineWidth: 1.2,
      lineStyle: LightweightCharts.LineStyle.Dashed,
      axisLabelVisible: false, // Bersih dari sumbu harga kanan
      title: ""
    });
    priceLines.push(slopeLine);
  }

  // 1C. Predictive Matrix ("Where to Wait" Target Lines Snapped to Price Axis)
  if (filterShowRadar && data.predictive_matrix && data.predictive_matrix.stations) {
    data.predictive_matrix.stations.forEach(st => {
      let lineColor = "#06b6d4";
      let lineTitle = `WAIT M2/M3 (${st.direction})`;
      let targetP = st.target_price;

      if (st.type === "SWEEP") {
        lineColor = "#fb923c";
        lineTitle = `WAIT M1A SWEEP (${st.direction})`;
        targetP = st.target_price;
      } else if (st.type === "EXPANSION") {
        lineColor = "#fbbf24";
        lineTitle = `TARGET M4 EXPANSION (${st.direction})`;
        targetP = (st.expansion_target && st.expansion_target > 0) ? st.expansion_target : st.target_price;
      }

      if (targetP && targetP > 0) {
        const stLine = candleSeries.createPriceLine({
          price: targetP,
          color: lineColor,
          lineWidth: 1.5,
          lineStyle: LightweightCharts.LineStyle.Dashed,
          axisLabelVisible: true,
          title: lineTitle
        });
        priceLines.push(stLine);
      }
    });
  }

  // Ensure native series markers are clean (all historical strategy audit badges rendered in Section 6)
  if (candleSeries) {
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
    renderHeader(data.account, data.timestamp_wib, data.shadow_radar, data.confluence_timing);
    renderWatchlist(data.pairs);
    if (currentDrawerTab === "shadow") {
      renderDrawer();
    }
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
function renderHeader(acc, clock, shadowRadar, timing) {
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

  if (clock) {
    const clockEl = document.getElementById("live-clock");
    if (clockEl) {
      const parts = clock.split("•");
      clockEl.textContent = parts[0].trim();
      clockEl.title = clock;
    }
  }

  const tmEl = document.getElementById("timing-phase-val");
  if (tmEl && timing) {
    const phase = timing.timing_phase || "--";
    const mode = timing.target_mode || "--";
    let shortPhase = phase;
    if (phase.includes("DEAD")) shortPhase = "DEAD ZONE";
    else if (phase.includes("LULL")) shortPhase = "MIDDAY LULL";
    else if (phase.includes("EXPANSION")) shortPhase = "EXPANSION";
    tmEl.textContent = shortPhase;
    tmEl.title = `${phase} (${mode})`;
    if (phase.includes("LULL")) {
      tmEl.style.color = "var(--amber)";
    } else if (phase.includes("DEAD")) {
      tmEl.style.color = "var(--red)";
    } else {
      tmEl.style.color = "var(--green)";
    }
  }

  const shEl = document.getElementById("shadow-stat-val");
  if (shEl && shadowRadar) {
    const tot = shadowRadar.total_recorded || 0;
    const wr = shadowRadar.winrate_pct || 0;
    const netR = shadowRadar.cumulative_net_r || 0;
    const act = shadowRadar.active_count || 0;
    const pend = shadowRadar.pending_count || 0;
    shEl.textContent = `${tot} rec • WR ${wr.toFixed(0)}% (${netR >= 0 ? '+' : ''}${netR.toFixed(1)}R)`;
    shEl.title = `Virtual Shadow Tracker:\nTotal: ${tot} records\nActive: ${act} positions, Pending: ${pend}\nWinrate: ${wr.toFixed(1)}%\nCumulative Net R: ${netR >= 0 ? '+' : ''}${netR.toFixed(2)}R`;
    shEl.style.color = (netR >= 0) ? "var(--green)" : "var(--red)";
  }
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

    if (p.is_confluence) {
      setupPillClass = sName.includes("BEAR") ? "setup-pill-confl-bear" : "setup-pill-confl-bull";
    } else if (sName.includes("BEAR") || sName.includes("SELL") || (!sName.includes("BULL") && bName.includes("BEAR"))) {
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

    const biasTagClass = bName.includes("BULL") ? "htf-bull" : (bName.includes("BEAR") ? "htf-bear" : "htf-flat");
    const pipsVal = p.dist_pips !== undefined ? p.dist_pips.toFixed(1) : "0.0";
    const atrVal = p.dist_atr !== undefined ? p.dist_atr.toFixed(2) : "0.00";
    const trigText = p.dist_atr < 50 ? `Trig: ${pipsVal}p (${atrVal}x)` : "Trig: Idle";

    let cleanSetup = (p.active_setup || "WATCH");
    if (cleanSetup !== "WATCH") {
      cleanSetup = cleanSetup.replace(/\s+(BEAR|BULL|BUY|SELL)$/i, "").trim() || cleanSetup;
    }

    const c1Text = p.c1_text || (p.c1_pips !== undefined && p.c1_pips !== null ? `C1: ${p.c1_pips}p` : 'C1: —');
    const f1Text = p.f1_text || (p.f1_pips !== undefined && p.f1_pips !== null ? `F1: ${p.f1_pips}p` : 'F1: —');

    let m4RowClass = "";
    let m4Pill = "";
    if (p.m4_flow_state === "SHOCK" || p.m4_shock) {
      m4RowClass = "m4-shock-row";
      m4Pill = `<span class="m4-shock-pill" title="Systemic Flow Shock Active (|z| >= 2.00)"><span class="material-symbols-outlined" style="font-size:11px;line-height:1;">bolt</span> SFR SHOCK | z: ${p.m4_z > 0 ? '+' : ''}${p.m4_z}</span>`;
    } else if (p.m4_flow_state === "CONT") {
      m4RowClass = "m4-cont-row";
      m4Pill = `<span class="m4-cont-pill" title="Systemic Flow Continuation Phase (Decaying |z| >= 0.75)"><span class="material-symbols-outlined" style="font-size:11px;line-height:1;">trending_flat</span> FLOW CONT | z: ${p.m4_z > 0 ? '+' : ''}${p.m4_z}</span>`;
    }

    const boxPill = (p.basing_box && p.basing_box.is_compressing)
      ? `<span class="box-compress-pill" title="Dynamic Basing Box: ${p.basing_box.box_bars} bars, ${p.basing_box.range_atr.toFixed(2)}x ATR [${p.basing_box.box_floor.toFixed(p.digits || 5)} - ${p.basing_box.box_ceiling.toFixed(p.digits || 5)}]"><span class="material-symbols-outlined" style="font-size:10px;line-height:1;">view_in_ar</span> BOX ${p.basing_box.box_bars}b</span>`
      : ((p.basing_box && p.basing_box.is_broken && p.basing_box.broken_recency <= 4)
        ? `<span class="box-compress-pill" style="border-color:#f59e0b;color:#f59e0b;background:rgba(245,158,11,0.1);" title="Basing Box Retest: Broken ${p.basing_box.broken_recency}b ago [${p.basing_box.box_floor.toFixed(p.digits || 5)} - ${p.basing_box.box_ceiling.toFixed(p.digits || 5)}]"><span class="material-symbols-outlined" style="font-size:10px;line-height:1;">history</span> BRK ${p.basing_box.box_bars}b</span>`
        : '');

    const w1Pill = p.w1_horizon_conflict
      ? `<span class="w1-conflict-pill" title="W1 Slope Conflict: Price testing descending slope barrier @ ${p.w1_slope_ceiling ? p.w1_slope_ceiling.toFixed(p.digits || 5) : ''} (BUY Blocked)"><span class="material-symbols-outlined" style="font-size:10px;line-height:1;">trending_down</span> W1 SLOPE</span>`
      : '';

    html += `
      <div class="pair-row ${isSelected} ${m4RowClass}" onclick="selectSymbol('${p.symbol}')">
        <!-- Line 1: Symbol, CSM, Tier Badge -->
        <div class="pair-row-line">
          <div class="pair-col-left">
            <span class="pair-symbol">${cleanSym}</span>
            <span class="csm-text ${csmClass}">${csmText}</span>
          </div>
          <div class="pair-col-mid"></div>
          <div class="pair-col-right">
            <span class="tier-badge ${tierClass}">${p.perm_label}</span>
          </div>
        </div>
        <!-- Line 2: Setup Pill, C1 Wall (Top), HTF Bias -->
        <div class="pair-row-line">
          <div class="pair-col-left">
            <span class="pair-setup-pill ${setupPillClass}">${cleanSetup}</span>
            ${p.extra_count > 0 && !p.is_confluence ? `<span class="extra-setup-pill" title="${p.extra_count} additional standby setup(s)" style="margin-left:2px;">+${p.extra_count}</span>` : ''}
          </div>
          <div class="pair-col-mid">
            <span style="color:#fbbf24;font-size:8.5px;font-family:var(--font-mono);font-weight:600;" title="Ceiling Wall C1 Distance">${c1Text}</span>
          </div>
          <div class="pair-col-right">
            <span class="htf-bias-tag ${biasTagClass}">${p.bias}</span>
          </div>
        </div>
        <!-- Line 3: Trigger Distance, F1 Floor (Bottom), Basing Box, W1 Slope & M4 Shock Badge -->
        <div class="pair-row-line">
          <div class="pair-col-left">
            <span class="pair-dist-text">${trigText}</span>
          </div>
          <div class="pair-col-mid">
            <span style="color:#38bdf8;font-size:8.5px;font-family:var(--font-mono);font-weight:600;" title="Floor Wall F1 Distance">${f1Text}</span>
          </div>
          <div class="pair-col-right" style="gap:3px;">
            ${boxPill}
            ${w1Pill}
            ${m4Pill}
          </div>
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
  document.getElementById("strip-dr").textContent = d.runway_text || (d.dr_pos !== undefined ? `${d.dr_pos.toFixed(1)}% (${d.dr_label})` : '—');
  
  const csmEl = document.getElementById("strip-csm");
  csmEl.textContent = `${d.csm_delta >= 0 ? '+' : ''}${d.csm_delta.toFixed(2)}`;
  csmEl.className = `strip-val ${d.csm_delta >= 0 ? 'stat-pnl-pos' : 'stat-pnl-neg'}`;

  const dirLock = d.direction_lock ? (d.direction_lock.dir === 1 ? "BUY ONLY" : (d.direction_lock.dir === -1 ? "SELL ONLY" : "FREE")) : "FREE";
  document.getElementById("strip-tier").textContent = `${d.action_tier} (${d.perm_label}) • DIR: ${dirLock}`;

  // Render Multi-TF Compass & State HUD
  const symTagEl = document.getElementById("hud-sym-tag");
  if (symTagEl) {
    symTagEl.textContent = `${clean} ${currentTF}`;
    if (d.tactical_desc) symTagEl.title = `${clean} ${currentTF} • ${d.tactical_desc}`;
  }
  if (d.intel) {
    const it = d.intel;
    setCompassPill("pill-w1", "W1", it.w1_trend);
    setCompassPill("pill-d1", "D1", it.d1_trend);
    setCompassPill("pill-h4", "H4", it.h4_trend);
    setCompassPill("pill-h1", "H1", it.h1_trend);

    document.getElementById("hud-adx").textContent = `${it.adx}`;

    const stateEl = document.getElementById("hud-state");
    if (stateEl) {
      const fullState = it.operational_phase || it.mse_state || d.action_tier || "WATCH";
      let shortState = it.mse_state || d.action_tier || "WATCH";
      if (fullState.includes("RETEST")) shortState = "M3 RETEST";
      else if (fullState.includes("SWEEP")) shortState = "M1 SWEEP";
      else if (fullState.includes("PULLBACK")) shortState = "M2 PULLBACK";
      else if (fullState.includes("CONT")) shortState = "M4 CONT";
      stateEl.textContent = shortState;
      stateEl.title = fullState;
    }

    const sessEl = document.getElementById("hud-session");
    if (sessEl) {
      const fullSess = it.active_session || "ASIA";
      let shortSess = fullSess;
      if (fullSess.toLowerCase().includes("weekend") || fullSess.toLowerCase().includes("closed")) shortSess = "WEEKEND";
      else if (fullSess.toLowerCase().includes("london")) shortSess = "LONDON";
      else if (fullSess.toLowerCase().includes("new york") || fullSess.toLowerCase().includes("ny")) shortSess = "NEW YORK";
      else if (fullSess.toLowerCase().includes("asian") || fullSess.toLowerCase().includes("tokyo")) shortSess = "TOKYO";
      sessEl.textContent = shortSess;
      sessEl.title = fullSess;
    }

    const waveEl = document.getElementById("hud-wave-regime");
    if (waveEl) {
      const reg = it.wave_regime_summary || "YOUNG_OSCILLATION";
      const regLabel = reg.includes("SUPER") ? "SUPER SQUEEZE" : (reg.includes("MATURE") ? "MATURE SQUEEZE" : "YOUNG OSC");
      waveEl.textContent = `${regLabel} (${it.range_age_hours || 0}h)`;
      waveEl.style.color = reg.includes("SUPER") ? "#ec4899" : (reg.includes("MATURE") ? "#f59e0b" : "#38bdf8");
    }
    document.getElementById("hud-rollover").textContent = it.pre_rollover_countdown;

    // Macro H4 Pattern HUD Binding
    const envData = d.macro_envelope;
    const patNameEl = document.getElementById("hud-pattern-name");
    const upSlopeEl = document.getElementById("hud-upper-slope");
    const loSlopeEl = document.getElementById("hud-lower-slope");
    const patTauEl = document.getElementById("hud-pattern-tau");
    if (envData && patNameEl) {
      const ev = d.envelope_visual || {};
      const ss = ev.swing_structure || {};
      const dr = ev.dealing_range || envData.dealing_range || null;
      const oflow = ev.order_flow || envData.order_flow || null;
      const dol = ev.draw_on_liquidity || envData.draw_on_liquidity || null;
      const geom = ss.geometric_pattern || (envData && envData.geometric_pattern) || null;
      const mGeom = ss.macro_pattern || (envData && envData.macro_pattern) || null;

      if (dr && dr.range_high > 0 && oflow) {
        const ofRegime = (oflow.regime || "").replace("_ORDER_FLOW", "") || "CHOPPY";
        const ofSeq = oflow.sequence_summary || (oflow.last_peak_label && oflow.last_trough_label ? `${oflow.last_peak_label}/${oflow.last_trough_label}` : "");
        const ofLabel = ofSeq ? `${ofRegime} (${ofSeq})` : ofRegime;

        const dolTarget = (dol && dol.target_price > 0) ? `${dol.direction === 'SEEKING_BSL' ? 'BSL' : 'SSL'} @ ${dol.target_price.toFixed(cachedSymbolData.digits || 5)}` : "—";
        const drPct = dr.dr_position_pct !== undefined ? `${dr.dr_position_pct}%` : `${Math.round(d.dr_pos || 50)}%`;
        
        let drZoneLabel = dr.zone_status || d.dr_label || "EQ";
        if (drZoneLabel.includes("SHALLOW")) {
          drZoneLabel = "INDUCEMENT TRAP";
        } else if (drZoneLabel === "DEEP_DISCOUNT") {
          drZoneLabel = "DEEP DISCOUNT (OTE)";
        } else if (drZoneLabel === "DEEP_PREMIUM") {
          drZoneLabel = "DEEP PREMIUM (OTE)";
        }

        let combinedLabel = `OF: ${ofLabel} • DOL: ${dolTarget} • DR: ${drPct} [${drZoneLabel}]`;
        if (geom && geom.name !== "NONE" && geom.status === "CONFIRMED_BREAKOUT") {
          combinedLabel += ` • [${geom.name}]`;
        }

        const f382Val = dr.fib_382 ? dr.fib_382.toFixed(cachedSymbolData.digits || 5) : "—";
        const f618Val = dr.fib_618 ? dr.fib_618.toFixed(cachedSymbolData.digits || 5) : "—";
        const fullTitle = `HTF Dealing Range: [${dr.range_low.toFixed(cachedSymbolData.digits || 5)} .. ${dr.range_high.toFixed(cachedSymbolData.digits || 5)}]\n61.8% OTE: ${f618Val}\n50% EQ: ${dr.equilibrium_50.toFixed(cachedSymbolData.digits || 5)} [${dr.zone_status}]\n38.2% Inducement: ${f382Val}\nRange Valid: ${dr.is_valid_range ? 'YES (Confirmed)' : 'PROVISIONAL'}\nDraw on Liquidity: ${dol ? dol.pool_type : '—'} (${dol ? dol.distance_pips : 0}p away)\nOrder Flow: ${oflow.regime || 'CHOPPY'}`;

        patNameEl.textContent = combinedLabel;
        patNameEl.title = fullTitle;
        patNameEl.style.color = drZoneLabel.includes("INDUCEMENT") ? "#f59e0b" : (ofRegime.includes("BULL") ? "#10b981" : (ofRegime.includes("BEAR") ? "#f43f5e" : "#fbbf24"));
      } else {
        let pDisplay = envData.pattern_display_label || (geom && geom.name !== "NONE" ? geom.name : (envData.structural_trend || "RANGING"));
        let mDisplay = mGeom && mGeom.name !== "NONE" ? mGeom.name : "";

        let tooltipTgt = "";
        if (geom && geom.target_geom_price > 0 && geom.target_pips) {
          tooltipTgt = `Target: ${geom.target_geom_price.toFixed(cachedSymbolData.digits || 5)} (${geom.target_pips > 0 ? '+' : ''}${geom.target_pips}p)`;
        }
        let fullTitle = tooltipTgt ? `${pDisplay} • ${tooltipTgt}` : (geom && geom.status ? `${pDisplay} [${geom.status}]` : pDisplay);
        if (mDisplay && mDisplay !== geom?.name) {
          fullTitle += ` • Macro: ${mDisplay}`;
        }

        let combinedLabel = pDisplay;
        if (mDisplay && mDisplay !== geom?.name && mDisplay !== "RANGING") {
          combinedLabel = `${pDisplay} • [M: ${mDisplay}]`;
        }
        patNameEl.textContent = combinedLabel;
        patNameEl.title = fullTitle;
        patNameEl.style.color = (geom && geom.bias === "BULLISH") || pDisplay.includes("BULL") ? "#10b981" : ((geom && geom.bias === "BEARISH") || pDisplay.includes("BEAR") ? "#f43f5e" : (pDisplay.includes("COMPRESSION") || pDisplay.includes("TRIANGLE") || pDisplay.includes("WEDGE") ? "#ec4899" : "#fbbf24"));
      }

      const uSl = (envData.upper_slope !== undefined) ? envData.upper_slope : (ss.upper_slope || 0.0);
      const lSl = (envData.lower_slope !== undefined) ? envData.lower_slope : (ss.lower_slope || 0.0);
      const mUSl = (envData.macro_upper_slope !== undefined) ? envData.macro_upper_slope : (ss.macro_upper_slope || 0.0);
      const mLSl = (envData.macro_lower_slope !== undefined) ? envData.macro_lower_slope : (ss.macro_lower_slope || 0.0);

      if (upSlopeEl) {
        upSlopeEl.textContent = `${uSl > 0 ? '+' : ''}${uSl.toFixed(1)} p/b`;
        upSlopeEl.title = `Tactical: ${uSl > 0 ? '+' : ''}${uSl.toFixed(1)} p/b | Macro: ${mUSl > 0 ? '+' : ''}${mUSl.toFixed(1)} p/b`;
        upSlopeEl.style.color = uSl > 0 ? "#10b981" : (uSl < 0 ? "#f43f5e" : "var(--text-secondary)");
      }
      if (loSlopeEl) {
        loSlopeEl.textContent = `${lSl > 0 ? '+' : ''}${lSl.toFixed(1)} p/b`;
        loSlopeEl.title = `Tactical: ${lSl > 0 ? '+' : ''}${lSl.toFixed(1)} p/b | Macro: ${mLSl > 0 ? '+' : ''}${mLSl.toFixed(1)} p/b`;
        loSlopeEl.style.color = lSl > 0 ? "#10b981" : (lSl < 0 ? "#f43f5e" : "var(--text-secondary)");
      }
      if (patTauEl) {
        const tauVal = Math.round((envData.channel_position_tau || 0.5) * 100);
        patTauEl.textContent = `${tauVal}%`;
      }
    }
  }

  // Render M4 Systemic Flow Shock Alert Chip
  const m4Chip = document.getElementById("chip-m4-shock");
  if (m4Chip) {
    if (d.m4_flow_state === "SHOCK" || d.m4_shock) {
      m4Chip.style.display = "inline-flex";
      m4Chip.title = `SYSTEMIC FLOW SHOCK (SFR) ACTIVE\nDominant Currency z: ${d.m4_z > 0 ? '+' : ''}${d.m4_z.toFixed(2)} (${d.m4_dir || 'BULL'})\nDirection Locked • Watching Basing / Structure`;
      const lbl = document.getElementById("m4-chip-label");
      if (lbl) lbl.textContent = `SFR SHOCK ${d.m4_z > 0 ? '+' : ''}${d.m4_z.toFixed(1)}z (${d.m4_dir || 'BULL'})`;
    } else if (d.m4_flow_state === "CONT") {
      m4Chip.style.display = "inline-flex";
      m4Chip.title = `SYSTEMIC FLOW CONTINUATION\nDominant Currency z: ${d.m4_z > 0 ? '+' : ''}${d.m4_z.toFixed(2)} (${d.m4_dir || 'BULL'})\nEpisode Active • Watching Retest / Basing`;
      const lbl = document.getElementById("m4-chip-label");
      if (lbl) lbl.textContent = `SFR CONT ${d.m4_z > 0 ? '+' : ''}${d.m4_z.toFixed(1)}z`;
    } else {
      m4Chip.style.display = "none";
    }
  }

  // Render W1 Dual-Horizon Slope Alert Chip
  const w1Chip = document.getElementById("chip-w1-slope");
  if (w1Chip) {
    if (d.w1_horizon_conflict && d.w1_slope_ceiling) {
      w1Chip.style.display = "inline-flex";
      w1Chip.title = `W1 DUAL-HORIZON SLOPE CEILING DETECTED\nUpper Tangent Slope @ ${d.w1_slope_ceiling.toFixed(d.digits || 5)}\nIntermediate: ${d.w1_intermediate_regime || 'BEARISH'} (Secular: ${d.w1_secular_regime || 'BULLISH'})\nBUY ORDERS BLOCKED`;
      const lbl = document.getElementById("w1-chip-label");
      if (lbl) lbl.textContent = `W1 SLOPE @ ${d.w1_slope_ceiling.toFixed(d.digits || 5)} [BUY LOCKED]`;
    } else {
      w1Chip.style.display = "none";
    }
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

  if (ema20Data.length > 0) ema20Series.setData(ema20Data);
  if (ema50Data.length > 0) ema50Series.setData(ema50Data);
  if (ema200Data.length > 0) ema200Series.setData(ema200Data);

  ema20Series.applyOptions({ visible: filterShowEMA });
  ema50Series.applyOptions({ visible: filterShowEMA });
  ema200Series.applyOptions({ visible: filterShowEMA });

  // Toggle HUD EMA Legend visibility
  const emaLegEl = document.getElementById("chart-ema-legend");
  const emaSepEl = document.getElementById("chart-mini-legend-sep");
  if (emaLegEl) emaLegEl.style.display = filterShowEMA ? "inline-flex" : "none";
  if (emaSepEl) emaSepEl.style.display = filterShowEMA ? "inline" : "none";

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
    else if (g.status === "OBSERVE") { statusClass = "status-observe"; boxClass = "observe"; }
    else if (g.status === "PAPER") { statusClass = "status-paper"; boxClass = "paper"; }

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
      <th>Ticket</th><th>Type</th><th>Volume</th><th>Open Price</th><th>Current SL</th><th>Current TP</th><th>Profit</th><th>Management Stage</th><th>Pre-Rollover Dist</th><th>CSM Shift</th>
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
        <td style="font-family:var(--font-mono);font-size:11px;">${p.csm_shift || '—'}</td>
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
        <td>—</td>
      </tr>`;
    });

    html += `</tbody></table>`;
    container.innerHTML = html;

  } else if (currentDrawerTab === "cbss") {
    const cbss = cachedOverview?.cbss_matrix;
    if (!cbss || !cbss.baskets) {
      container.innerHTML = `<div style="padding:10px;color:var(--text-dim);">Memuat data Currency Basket Structural Synchronization (CBSS)...</div>`;
      return;
    }

    let html = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <div style="font-weight:800;font-size:11px;color:var(--cyan);text-transform:uppercase;letter-spacing:0.5px;">
          CBSS CURRENCY BASKET SYNCHRONIZATION (CAP: MAX ${cbss.max_concurrency_cap} POSISI SEARAH | G3 VETO: &le;${cbss.g3_threshold_atr}x ATR)
        </div>
        <span style="font-family:var(--font-mono);font-size:10px;color:var(--text-dim);">Status: <span style="color:var(--green);font-weight:700;">ACTIVE</span></span>
      </div>
      
      <!-- 8 Currency Cards Grid -->
      <div style="display:grid;grid-template-columns:repeat(4, 1fr);gap:8px;margin-bottom:12px;">
    `;

    cbss.baskets.forEach(b => {
      const isSat = b.is_long_saturated || b.is_short_saturated;
      const cardBorder = isSat ? "var(--red)" : "var(--border)";
      const longPill = b.is_long_saturated 
        ? `<span style="color:var(--red);font-weight:700;">${b.exposure_long}/${b.max_cap} LONG [CAP]</span>` 
        : `<span style="color:var(--green);">${b.exposure_long}/${b.max_cap} LONG</span>`;
      const shortPill = b.is_short_saturated 
        ? `<span style="color:var(--red);font-weight:700;">${b.exposure_short}/${b.max_cap} SHORT [CAP]</span>` 
        : `<span style="color:var(--cyan);">${b.exposure_short}/${b.max_cap} SHORT</span>`;
      
      const topList = b.top_candidates || (b.top_candidate ? [b.top_candidate] : []);
      const top1 = topList[0];
      const top2 = topList[1];
      const top1Text = top1 ? `${top1.pair} (${top1.direction} &rarr; ${top1.runway_atr.toFixed(1)}x ATR)` : '—';
      const top2Text = top2 ? `${top2.pair} (${top2.direction} &rarr; ${top2.runway_atr.toFixed(1)}x ATR)` : '—';

      html += `
        <div class="telemetry-card" style="border-top: 2px solid ${cardBorder};">
          <div class="tele-title" style="display:flex;justify-content:space-between;">
            <span>BASKET ${b.currency}</span>
            <span style="font-size:9px;color:${isSat ? 'var(--red)' : 'var(--text-dim)'};">${isSat ? 'SATURATED' : 'SAFE'}</span>
          </div>
          <div class="tele-row"><span class="tele-lbl">Directional Cap:</span><span class="tele-val">${longPill} &bull; ${shortPill}</span></div>
          <div class="tele-row"><span class="tele-lbl">BSSI Wall Sat:</span><span class="tele-val" style="font-size:9.5px;font-weight:700;color:${(b.bssi_long >= 0.70 || b.bssi_short >= 0.70) ? 'var(--red)' : 'var(--green)'};">L: ${((b.bssi_long || 0)*100).toFixed(0)}% &bull; S: ${((b.bssi_short || 0)*100).toFixed(0)}%</span></div>
          <div class="tele-row"><span class="tele-lbl">Active Longs:</span><span class="tele-val" style="font-size:9.5px;">${b.pairs_long.length ? b.pairs_long.join(', ') : 'None'}</span></div>
          <div class="tele-row"><span class="tele-lbl">Active Shorts:</span><span class="tele-val" style="font-size:9.5px;">${b.pairs_short.length ? b.pairs_short.join(', ') : 'None'}</span></div>
          <div class="tele-row"><span class="tele-lbl">Top #1:</span><span class="tele-val" style="color:var(--amber);font-weight:700;font-size:9.5px;">${top1Text}</span></div>
          <div class="tele-row"><span class="tele-lbl">Top #2:</span><span class="tele-val" style="color:#a78bfa;font-weight:600;font-size:9.5px;">${top2Text}</span></div>
        </div>
      `;
    });

    html += `</div>`;

    // Leaderboard Tabel Juara Keranjang (Top 2 Candidates per Currency)
    html += `
      <div style="font-weight:700;font-size:11px;color:var(--amber);margin-bottom:4px;text-transform:uppercase;">
        Top 2 Runway Leaderboard (Session-Aware Juara &amp; Runner-up ZCE Runway serta G3 Wall Veto Radar):
      </div>
      <table class="data-table"><thead><tr>
        <th>Mata Uang</th><th>Rank</th><th>Candidate Pair</th><th>Arah</th><th>Session Status</th><th>ZCE Target Wall</th><th>Wall Grade</th><th>Runway ATR</th><th>G3 Wall Veto</th><th>Catatan CBSS</th>
      </tr></thead><tbody>
    `;

    cbss.baskets.forEach(b => {
      const topList = b.top_candidates || (b.top_candidate ? [b.top_candidate] : []);
      topList.forEach((cand, idx) => {
        const isBlocked = cand.is_g3_blocked;
        const vetoBadge = isBlocked 
          ? `<span class="badge" style="background:rgba(239,68,68,0.18);color:var(--red);border:1px solid rgba(239,68,68,0.4);font-weight:700;">G3 VETO</span>`
          : `<span class="badge" style="background:rgba(0,230,118,0.14);color:var(--green);border:1px solid rgba(0,230,118,0.3);font-weight:700;">CLEAR</span>`;
        
        const isSessOk = cand.is_session_allowed !== false;
        const sessBadge = isSessOk
          ? `<span class="badge" style="background:rgba(0,230,118,0.14);color:var(--green);border:1px solid rgba(0,230,118,0.3);font-weight:700;">PERMITTED</span>`
          : `<span class="badge" style="background:rgba(245,158,11,0.15);color:var(--amber);border:1px solid rgba(245,158,11,0.35);font-weight:700;">LOCKED</span>`;

        const dirCol = cand.direction === "BUY" ? "var(--green)" : "var(--red)";
        const rankLabel = idx === 0 ? `<span style="color:var(--amber);font-weight:800;">#1 JUARA</span>` : `<span style="color:#a78bfa;font-weight:700;">#2 RUNNER-UP</span>`;

        html += `<tr>
          <td style="font-weight:800;color:var(--cyan);">${idx === 0 ? b.currency : ''}</td>
          <td>${rankLabel}</td>
          <td style="font-weight:700;cursor:pointer;" onclick="selectSymbol('${cand.pair}')">${cand.pair}</td>
          <td style="color:${dirCol};font-weight:700;">${cand.direction}</td>
          <td>${sessBadge}</td>
          <td>${cand.target_wall.toFixed(5)}</td>
          <td>${cand.target_grade}</td>
          <td style="color:var(--amber);font-weight:700;">${cand.runway_atr.toFixed(2)}x ATR</td>
          <td>${vetoBadge}</td>
          <td style="font-size:9.5px;color:var(--text-muted);">${!isSessOk ? 'Sesi saat ini membatasi pair ini' : (cand.veto_reason || 'Runway terbuka leluasa')}</td>
        </tr>`;
      });
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
        <div class="telemetry-card" style="border-top: 2px solid #fb923c;">
          <div class="tele-title" style="color:#fb923c;">M1A: Macro Boundary Sweep</div>
          <div class="tele-row"><span class="tele-lbl">Target Sweep:</span><span class="tele-val">${t.m1_target || '—'}</span></div>
          <div class="tele-row"><span class="tele-lbl">Penetration:</span><span class="tele-val">${t.m1_penetration || 'No (>0.04 ATR)'}</span></div>
          <div class="tele-row"><span class="tele-lbl">Reclaim Status:</span><span class="tele-val">${t.m1_reclaim || 'Unconfirmed'}</span></div>
          <div class="tele-row"><span class="tele-lbl">Rejection Wick:</span><span class="tele-val">${t.m1_wick || '0.0% (Req >=33%)'}</span></div>
        </div>
        <div class="telemetry-card" style="border-top: 2px solid #ec4899;">
          <div class="tele-title" style="color:#ec4899;">M1B: Trend Induced Sweep</div>
          <div class="tele-row"><span class="tele-lbl">Anchor Level:</span><span class="tele-val" style="color:#ec4899;font-weight:700;">${t.m1b_target || '—'}</span></div>
          <div class="tele-row"><span class="tele-lbl">Liquidity Pool:</span><span class="tele-val" style="color:#ec4899;">${t.m1b_eqh || 'Single Anchor'}</span></div>
          <div class="tele-row"><span class="tele-lbl">ZCE Confluence:</span><span class="tele-val">${t.m1b_zce || '—'}</span></div>
          <div class="tele-row"><span class="tele-lbl">Sweep Status:</span><span class="tele-val">${t.m1b_status || 'Unconfirmed'}</span></div>
          <div class="tele-row"><span class="tele-lbl">Rejection Wick:</span><span class="tele-val">${t.m1b_wick || '0.0% (Req >=30%)'}</span></div>
        </div>
        <div class="telemetry-card" style="border-top: 2px solid #818cf8;">
          <div class="tele-title" style="color:#818cf8;">M2: Trend Pullback Retest</div>
          <div class="tele-row"><span class="tele-lbl">ADX Trend Strength:</span><span class="tele-val">${t.m2_adx || '—'}</span></div>
          <div class="tele-row"><span class="tele-lbl">Fib 50% Level:</span><span class="tele-val">${t.m2_fib50 || '—'}</span></div>
          <div class="tele-row"><span class="tele-lbl">Fib 61.8% Pocket:</span><span class="tele-val">${t.m2_fib618 || '—'}</span></div>
          <div class="tele-row"><span class="tele-lbl">Discount Status:</span><span class="tele-val">${t.m2_zone || 'EQUILIBRIUM'}</span></div>
        </div>
        <div class="telemetry-card" style="border-top: 2px solid #c084fc;">
          <div class="tele-title" style="color:#c084fc;">M3: Breakout Retest Guard</div>
          <div class="tele-row"><span class="tele-lbl">Broken SBR/RBS:</span><span class="tele-val">${t.m3_level || '—'}</span></div>
          <div class="tele-row"><span class="tele-lbl">15-Bar Recency:</span><span class="tele-val">${t.m3_recency || 'PASS'}</span></div>
          <div class="tele-row"><span class="tele-lbl">Basing Box:</span><span class="tele-val" style="color:#818cf8;">${t.m3_basing || '—'}</span></div>
          <div class="tele-row"><span class="tele-lbl">Target Runway:</span><span class="tele-val">${t.m3_runway || '1.40x ATR (Req >=0.8x)'}</span></div>
        </div>
        <div class="telemetry-card" style="border-top: 2px solid #34d399;">
          <div class="tele-title" style="color:#34d399;">M4: Systemic Flow Continuation</div>
          <div class="tele-row"><span class="tele-lbl">Currency Z-Score:</span><span class="tele-val">${t.m4_z || '—'} (Req >=2.0)</span></div>
          <div class="tele-row"><span class="tele-lbl">120-Bar Breakdown:</span><span class="tele-val">${t.m4_breakdown || '—'}</span></div>
          <div class="tele-row"><span class="tele-lbl">Structural SL/TP:</span><span class="tele-val">SL 0.45x ATR | TP 1.1R</span></div>
          <div class="tele-row"><span class="tele-lbl">Standby Order:</span><span class="tele-val">${t.m4_pending || 'None'}</span></div>
        </div>
      </div>
    `;
  } else if (currentDrawerTab === "predictive") {
    if (!d || !d.predictive_matrix || !d.predictive_matrix.stations) {
      container.innerHTML = `<div style="padding:10px;color:var(--text-dim);">Memuat data predictive matrix Where to Wait...</div>`;
      return;
    }
    const pm = d.predictive_matrix;
    const regimeColor = pm.market_regime.includes("BULL") ? "var(--green)" : (pm.market_regime.includes("BEAR") ? "var(--red)" : "var(--cyan)");
    
    let html = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid var(--border);">
        <div style="display:flex;align-items:center;gap:8px;">
          <span style="font-weight:800;font-size:11px;color:var(--cyan);text-transform:uppercase;letter-spacing:0.5px;">
            WHERE TO WAIT MATRIX (NEXT STATIONS: PULLBACK • SWEEP • EXPANSION)
          </span>
          <span class="badge" style="background:rgba(56,189,248,0.12);color:${regimeColor};border:1px solid ${regimeColor};font-weight:700;">
            ${pm.market_regime}
          </span>
        </div>
        <span style="font-family:var(--font-mono);font-size:10px;color:var(--text-dim);">
          Dealing Range Position: <strong style="color:var(--amber);">${(pm.dr_position_pct || 50).toFixed(1)}%</strong> &bull; Live Mid: <strong style="color:#fff;">${((d.bid + d.ask)/2).toFixed(d.digits || 5)}</strong>
        </span>
      </div>

      <div style="display:grid;grid-template-columns:repeat(3, 1fr);gap:10px;margin-bottom:10px;">
    `;

    pm.stations.forEach(st => {
      let cardBorder = "#38bdf8";
      let dirColor = (st.direction === "BUY") ? "var(--green)" : "var(--red)";
      let tagBg = (st.direction === "BUY") ? "rgba(16,185,129,0.15)" : "rgba(244,63,94,0.15)";
      if (st.type === "PULLBACK") cardBorder = "#06b6d4";
      else if (st.type === "SWEEP") cardBorder = "#fb923c";
      else if (st.type === "EXPANSION") cardBorder = "#fbbf24";

      html += `
        <div class="telemetry-card" style="border-top: 3px solid ${cardBorder};background:rgba(15,23,42,0.6);">
          <div class="tele-title" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
            <span style="color:${cardBorder};font-weight:800;font-size:11px;">${st.setup_name}</span>
            <span style="background:${tagBg};color:${dirColor};font-weight:800;padding:1px 6px;border-radius:2px;font-size:9.5px;font-family:var(--font-mono);">${st.direction}</span>
          </div>

          <div style="background:rgba(0,0,0,0.25);padding:6px 8px;border-radius:3px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:baseline;">
            <span style="font-family:var(--font-mono);font-size:10px;color:var(--text-dim);">TARGET LEVEL:</span>
            <span style="font-family:var(--font-mono);font-size:14px;font-weight:800;color:#fff;">${st.target_price.toFixed(d.digits || 5)}</span>
          </div>

          <div class="tele-row"><span class="tele-lbl">Jarak dari Live:</span><span class="tele-val" style="color:var(--amber);font-weight:700;">${st.distance_pips > 0 ? '+' : ''}${st.distance_pips} pips (${st.distance_atr}x ATR)</span></div>
          <div class="tele-row"><span class="tele-lbl">Proteksi SL:</span><span class="tele-val" style="color:var(--red);font-family:var(--font-mono);">${st.sl.toFixed(d.digits || 5)}</span></div>
          <div class="tele-row"><span class="tele-lbl">Target TP:</span><span class="tele-val" style="color:var(--green);font-family:var(--font-mono);">${st.tp.toFixed(d.digits || 5)} (RR 1:${st.rr})</span></div>
          <div class="tele-row"><span class="tele-lbl">Status Stasiun:</span><span class="tele-val" style="color:var(--cyan);font-weight:700;">${st.status}</span></div>

          <div style="margin-top:6px;padding-top:6px;border-top:1px dashed rgba(255,255,255,0.08);font-size:9.5px;line-height:1.4;color:var(--text-muted);">
            <strong style="color:var(--text-main);">Trigger Rule:</strong> ${st.trigger_condition}
          </div>
        </div>
      `;
    });

    html += `</div>`;
    container.innerHTML = html;
  }
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
      const drawer = document.getElementById("bottom-drawer");
      if (drawer && drawer.classList.contains("bottom-collapsed")) {
        toggleBottomDrawer();
      }
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


  // Granular ZCE Chip toggles
  const chipRadar = document.getElementById("chip-radar");
  if (chipRadar) {
    chipRadar.addEventListener("click", () => {
      filterShowRadar = !filterShowRadar;
      chipRadar.classList.toggle("active-purple", filterShowRadar);
      try {
        localStorage.setItem("zce_radar", filterShowRadar ? "1" : "0");
      } catch(e) {}
      if (cachedSymbolData) renderChartLevels(cachedSymbolData);
    });
  }

  const chipF1C1 = document.getElementById("chip-f1c1");
  if (chipF1C1) {
    chipF1C1.addEventListener("click", () => {
      filterChipF1C1 = !filterChipF1C1;
      chipF1C1.classList.toggle("active", filterChipF1C1);
      try { localStorage.setItem("zce_f1c1", filterChipF1C1 ? "1" : "0"); } catch(e) {}
      if (cachedSymbolData) renderChartLevels(cachedSymbolData);
    });
  }

  const chipF2C2 = document.getElementById("chip-f2c2");
  if (chipF2C2) {
    chipF2C2.addEventListener("click", () => {
      filterChipF2C2 = !filterChipF2C2;
      chipF2C2.classList.toggle("active", filterChipF2C2);
      try { localStorage.setItem("zce_f2c2", filterChipF2C2 ? "1" : "0"); } catch(e) {}
      if (cachedSymbolData) renderChartLevels(cachedSymbolData);
    });
  }

  const chipEXT = document.getElementById("chip-ext");
  if (chipEXT) {
    chipEXT.addEventListener("click", () => {
      filterChipEXT = !filterChipEXT;
      chipEXT.classList.toggle("active", filterChipEXT);
      try { localStorage.setItem("zce_ext", filterChipEXT ? "1" : "0"); } catch(e) {}
      if (cachedSymbolData) renderChartLevels(cachedSymbolData);
    });
  }

  const chipPattern = document.getElementById("chip-pattern");
  if (chipPattern) {
    chipPattern.addEventListener("click", () => {
      filterShowPatterns = !filterShowPatterns;
      chipPattern.classList.toggle("active-amber", filterShowPatterns);
      try { localStorage.setItem("zce_patterns", filterShowPatterns ? "1" : "0"); } catch(e) {}
      renderVerticalShading();
    });
  }

  const chipEMA = document.getElementById("chip-ema");
  if (chipEMA) {
    chipEMA.addEventListener("click", () => {
      filterShowEMA = !filterShowEMA;
      chipEMA.classList.toggle("active-cyan", filterShowEMA);
      try { localStorage.setItem("zce_ema", filterShowEMA ? "1" : "0"); } catch(e) {}
      if (ema20Series) ema20Series.applyOptions({ visible: filterShowEMA });
      if (ema50Series) ema50Series.applyOptions({ visible: filterShowEMA });
      if (ema200Series) ema200Series.applyOptions({ visible: filterShowEMA });
      const emaLegEl = document.getElementById("chart-ema-legend");
      const emaSepEl = document.getElementById("chart-mini-legend-sep");
      if (emaLegEl) emaLegEl.style.display = filterShowEMA ? "inline-flex" : "none";
      if (emaSepEl) emaSepEl.style.display = filterShowEMA ? "inline" : "none";
    });
  }

  // Search input
  document.getElementById("pair-search").addEventListener("input", () => {
    if (cachedOverview) renderWatchlist(cachedOverview.pairs);
  });
}

// Synchronize granular chips with preset
function syncChipsWithPreset(preset) {
  activeZcePreset = preset;
  if (preset === "primary") {
    filterChipF1C1 = true;
    filterChipF2C2 = false;
    filterChipEXT = false;
  } else if (preset === "macro") {
    filterChipF1C1 = true;
    filterChipF2C2 = true;
    filterChipEXT = false;
  } else if (preset === "all") {
    filterChipF1C1 = true;
    filterChipF2C2 = true;
    filterChipEXT = true;
  } else if (preset === "off") {
    filterChipF1C1 = false;
    filterChipF2C2 = false;
    filterChipEXT = false;
  }

  const chipRadar = document.getElementById("chip-radar");
  if (chipRadar) chipRadar.classList.toggle("active-purple", filterShowRadar);

  const chipF1C1 = document.getElementById("chip-f1c1");
  if (chipF1C1) chipF1C1.classList.toggle("active", filterChipF1C1);

  const chipF2C2 = document.getElementById("chip-f2c2");
  if (chipF2C2) chipF2C2.classList.toggle("active", filterChipF2C2);

  const chipEXT = document.getElementById("chip-ext");
  if (chipEXT) chipEXT.classList.toggle("active", filterChipEXT);

  try {
    localStorage.setItem("zce_preset", preset);
  } catch(e) {}

  if (cachedSymbolData) renderChartLevels(cachedSymbolData);
}

// Toggle Left Panel (Watchlist Drawer)
function toggleLeftPanel() {
  const ws = document.querySelector(".workspace");
  if (!ws) return;
  ws.classList.toggle("left-collapsed");
  const isCollapsed = ws.classList.contains("left-collapsed");
  try {
    localStorage.setItem("left_collapsed", isCollapsed ? "1" : "0");
  } catch(e) {}

  const btn = document.getElementById("btn-toggle-left");
  if (btn) {
    btn.innerHTML = isCollapsed 
      ? '<span class="material-symbols-outlined" style="font-size:11px;vertical-align:-1px;">chevron_right</span>' 
      : '<span class="material-symbols-outlined" style="font-size:11px;vertical-align:-1px;">chevron_left</span>';
  }

  setTimeout(() => {
    const container = document.getElementById("tv-chart");
    if (chart && container) {
      chart.resize(container.clientWidth, container.clientHeight);
    }
    if (typeof resizeOverlayCanvas === "function") {
      resizeOverlayCanvas();
    }
  }, 220);
}

// Toggle Bottom Drawer (Collapse / Normal)
function toggleBottomDrawer() {
  const drawer = document.getElementById("bottom-drawer");
  if (!drawer) return;
  drawer.classList.remove("bottom-maximized");
  drawer.classList.toggle("bottom-collapsed");
  const isCollapsed = drawer.classList.contains("bottom-collapsed");
  try {
    localStorage.setItem("bottom_collapsed", isCollapsed ? "1" : "0");
  } catch(e) {}

  const btn = document.getElementById("btn-toggle-bottom");
  if (btn) {
    btn.innerHTML = isCollapsed 
      ? '<span class="material-symbols-outlined" style="font-size:12px;vertical-align:-1px;">expand_less</span>' 
      : '<span class="material-symbols-outlined" style="font-size:12px;vertical-align:-1px;">expand_more</span>';
  }

  const maxBtn = document.getElementById("btn-maximize-bottom");
  if (maxBtn) {
    maxBtn.innerHTML = '<span class="material-symbols-outlined" style="font-size:12px;vertical-align:-1px;">open_in_full</span>';
  }

  setTimeout(() => {
    const container = document.getElementById("tv-chart");
    if (chart && container) {
      chart.resize(container.clientWidth, container.clientHeight);
    }
    if (typeof resizeOverlayCanvas === "function") {
      resizeOverlayCanvas();
    }
  }, 220);
}

// Toggle Bottom Drawer Maximize / Fullscreen
function toggleMaximizeDrawer() {
  const drawer = document.getElementById("bottom-drawer");
  if (!drawer) return;
  drawer.classList.remove("bottom-collapsed");
  drawer.classList.toggle("bottom-maximized");
  const isMaximized = drawer.classList.contains("bottom-maximized");

  const maxBtn = document.getElementById("btn-maximize-bottom");
  if (maxBtn) {
    maxBtn.innerHTML = isMaximized
      ? '<span class="material-symbols-outlined" style="font-size:12px;vertical-align:-1px;">close_fullscreen</span>'
      : '<span class="material-symbols-outlined" style="font-size:12px;vertical-align:-1px;">open_in_full</span>';
    maxBtn.title = isMaximized ? "Kecilkan (Normal View)" : "Perbesar Maksimal (Fullscreen View)";
  }

  const btn = document.getElementById("btn-toggle-bottom");
  if (btn) {
    btn.innerHTML = '<span class="material-symbols-outlined" style="font-size:12px;vertical-align:-1px;">expand_more</span>';
  }

  setTimeout(() => {
    const container = document.getElementById("tv-chart");
    if (chart && container) {
      chart.resize(container.clientWidth, container.clientHeight);
    }
    if (typeof resizeOverlayCanvas === "function") {
      resizeOverlayCanvas();
    }
  }, 220);
}

// Toggle Right Panel X-Ray Audit
function toggleXrayPanel() {
  const ws = document.querySelector(".workspace");
  if (!ws) return;
  ws.classList.toggle("xray-collapsed");
  const isCollapsed = ws.classList.contains("xray-collapsed");
  try {
    localStorage.setItem("xray_collapsed", isCollapsed ? "1" : "0");
  } catch(e) {}

  const btn = document.getElementById("btn-toggle-xray");
  if (btn) btn.innerHTML = isCollapsed 
    ? '<span class="material-symbols-outlined" style="font-size:11px;vertical-align:-1px;">chevron_left</span>' 
    : '<span class="material-symbols-outlined" style="font-size:11px;vertical-align:-1px;">chevron_right</span>';

  setTimeout(() => {
    const container = document.getElementById("tv-chart");
    if (chart && container) {
      chart.resize(container.clientWidth, container.clientHeight);
    }
    if (typeof resizeOverlayCanvas === "function") {
      resizeOverlayCanvas();
    }
  }, 220);
}

// Bootstrap
window.addEventListener("DOMContentLoaded", () => {
  initChart();
  setupEvents();
  fetchOverview();
  fetchSymbolData();

  // Restore Panel collapse states & Filter preferences (Default is Clean Docked Focus Mode)
  try {
    if (localStorage.getItem("left_collapsed") === "0") {
      toggleLeftPanel(); // Open if user previously expanded it
    }
    if (localStorage.getItem("bottom_collapsed") === "0") {
      toggleBottomDrawer(); // Open if user previously expanded it
    }
    if (localStorage.getItem("xray_collapsed") === "0") {
      toggleXrayPanel(); // Open if user previously expanded it
    }
    if (localStorage.getItem("zce_radar") === "0") {
      filterShowRadar = false;
      const cr = document.getElementById("chip-radar");
      if (cr) cr.classList.remove("active-purple");
    }
    if (localStorage.getItem("zce_f1c1") === "0") {
      filterChipF1C1 = false;
      const c = document.getElementById("chip-f1c1");
      if (c) c.classList.remove("active");
    }
    if (localStorage.getItem("zce_f2c2") === "1") {
      filterChipF2C2 = true;
      const c = document.getElementById("chip-f2c2");
      if (c) c.classList.add("active");
    } else {
      filterChipF2C2 = false;
      const c = document.getElementById("chip-f2c2");
      if (c) c.classList.remove("active");
    }
    if (localStorage.getItem("zce_ext") === "1") {
      filterChipEXT = true;
      const c = document.getElementById("chip-ext");
      if (c) c.classList.add("active");
    } else {
      filterChipEXT = false;
      const c = document.getElementById("chip-ext");
      if (c) c.classList.remove("active");
    }
    if (localStorage.getItem("zce_patterns") === "0") {
      filterShowPatterns = false;
      const cp = document.getElementById("chip-pattern");
      if (cp) cp.classList.remove("active-amber");
    }
    if (localStorage.getItem("zce_ema") === "0") {
      filterShowEMA = false;
      const ce = document.getElementById("chip-ema");
      if (ce) ce.classList.remove("active-cyan");
    }
  } catch(e) {}

  // Fast Polling loop: 2.5s
  setInterval(fetchOverview, 2500);
  setInterval(fetchSymbolData, 3000);
});
</script>
</body>
</html>
"""
