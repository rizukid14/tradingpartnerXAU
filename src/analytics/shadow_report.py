"""
shadow_report.py — Standalone HTML Report Generator for Virtual Shadow Quant Radar.
Renders real-time telemetry, KPI cards, mechanism breakdown, risk gate disposition, and interactive order history.
"""

import os
import sys
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Any, List, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config
from src.analytics.shadow_tracker import shadow_tracker

WIB = ZoneInfo("Asia/Jakarta")


def render_shadow_report_html() -> str:
    """Generates a complete, responsive, terminal-grade HTML report of the Virtual Shadow Radar."""
    now_dt = datetime.now(WIB)
    now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S WIB")

    shadow_tracker.reload_state_if_modified()
    summary = shadow_tracker.get_performance_summary()
    resolved_trades = shadow_tracker.get_all_resolved_trades(limit=500)
    active_trades = shadow_tracker.get_active_trades_enriched()

    total_rec = summary.get("total_recorded", 0)
    act_cnt = summary.get("active_count", len(active_trades))
    pend_cnt = summary.get("pending_count", 0)
    tot_res = summary.get("total_resolved", len(resolved_trades))
    tp_hits = summary.get("tp_hits", 0)
    sl_hits = summary.get("sl_hits", 0)
    exp_cnt = summary.get("expired_count", 0)
    decisive = summary.get("decisive_trades", tp_hits + sl_hits)
    winrate = summary.get("winrate_pct", 0.0)
    cum_net_r = summary.get("cumulative_net_r", 0.0)
    ev_r = summary.get("expected_value_r", 0.0)

    # Disposition Stats
    disp_stats = summary.get("disposition_breakdown", {
        "EXECUTED_MT5": 0,
        "SKIPPED_RISK_BASKET": 0,
        "SKIPPED_RISK_BLOCK": 0,
        "SKIPPED_LLM_VETO": 0,
        "OTHER": 0
    })

    # Mechanisms Stats
    mechs = summary.get("mechanisms", {})
    m1 = mechs.get("M1", {"total": 0, "tp": 0, "sl": 0, "net_r": 0.0})
    m2 = mechs.get("M2", {"total": 0, "tp": 0, "sl": 0, "net_r": 0.0})
    m3 = mechs.get("M3", {"total": 0, "tp": 0, "sl": 0, "net_r": 0.0})
    m4 = mechs.get("M4", {"total": 0, "tp": 0, "sl": 0, "net_r": 0.0})

    # Combine active + resolved for data table
    all_combined = active_trades + resolved_trades
    trades_json = json.dumps(all_combined)

    net_r_color = "#00e676" if cum_net_r >= 0 else "#ff5252"
    ev_color = "#00e676" if ev_r >= 0 else "#ff5252"

    html = f"""<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Virtual Shadow Quant Radar — Performance Report</title>
  <style>
    :root {{
      --bg: #090d14;
      --card-bg: #111823;
      --border: #1e293b;
      --border-accent: #334155;
      --text: #f1f5f9;
      --text-dim: #94a3b8;
      --text-muted: #64748b;
      --green: #00e676;
      --green-glow: rgba(0, 230, 118, 0.18);
      --red: #ff5252;
      --red-glow: rgba(255, 82, 82, 0.18);
      --cyan: #38bdf8;
      --amber: #fbbf24;
      --purple: #c084fc;
      --blue: #60a5fa;
      --font-mono: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
      --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: var(--font-sans);
      font-size: 13px;
      line-height: 1.5;
      padding: 20px 24px;
    }}
    a {{ color: var(--cyan); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    
    /* Header Bar */
    .report-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 20px;
    }}
    .header-title-box h1 {{
      font-size: 20px;
      font-weight: 800;
      letter-spacing: -0.5px;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .header-subtitle {{
      color: var(--text-dim);
      font-size: 12px;
      margin-top: 4px;
    }}
    .header-actions {{
      display: flex;
      gap: 10px;
      align-items: center;
    }}
    .btn {{
      padding: 6px 14px;
      border-radius: 6px;
      font-size: 11.5px;
      font-weight: 700;
      cursor: pointer;
      border: 1px solid var(--border);
      background: var(--card-bg);
      color: var(--text);
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease;
    }}
    .btn:hover {{
      background: var(--border);
      border-color: var(--border-accent);
    }}
    .btn-primary {{
      background: rgba(192, 132, 252, 0.18);
      border-color: var(--purple);
      color: var(--purple);
    }}
    .btn-primary:hover {{
      background: rgba(192, 132, 252, 0.32);
    }}
    .badge {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 10.5px;
      font-weight: 700;
      font-family: var(--font-mono);
    }}
    .badge-live {{ background: var(--green-glow); color: var(--green); border: 1px solid rgba(0,230,118,0.4); }}
    .badge-purple {{ background: rgba(192, 132, 252, 0.15); color: var(--purple); border: 1px solid rgba(192,132,252,0.4); }}
    
    /* KPI Grid */
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
      margin-bottom: 24px;
    }}
    .kpi-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 14px 16px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }}
    .kpi-title {{
      font-size: 11px;
      text-transform: uppercase;
      font-weight: 700;
      letter-spacing: 0.5px;
      color: var(--text-dim);
    }}
    .kpi-value {{
      font-size: 24px;
      font-weight: 800;
      font-family: var(--font-mono);
      line-height: 1.2;
    }}
    .kpi-subtext {{
      font-size: 11px;
      color: var(--text-muted);
      margin-top: 4px;
    }}

    /* Section Boxes */
    .section-title {{
      font-size: 13px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--cyan);
      margin-bottom: 10px;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .dual-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-bottom: 24px;
    }}
    @media (max-width: 900px) {{
      .dual-grid {{ grid-template-columns: 1fr; }}
    }}

    /* Data Tables */
    .table-container {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      overflow-x: auto;
      margin-bottom: 24px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      text-align: left;
    }}
    th {{
      background: rgba(255, 255, 255, 0.02);
      color: var(--text-dim);
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      padding: 10px 14px;
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }}
    td {{
      padding: 10px 14px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      white-space: nowrap;
    }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover td {{ background: rgba(255, 255, 255, 0.02); }}

    /* Filters Bar */
    .filter-bar {{
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
      margin-bottom: 12px;
    }}
    .search-input {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      color: #fff;
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-family: var(--font-sans);
      outline: none;
      min-width: 200px;
    }}
    .search-input:focus {{ border-color: var(--cyan); }}
    .filter-pill {{
      padding: 4px 10px;
      border-radius: 4px;
      border: 1px solid var(--border);
      background: var(--card-bg);
      color: var(--text-dim);
      cursor: pointer;
      font-size: 11px;
      font-weight: 600;
    }}
    .filter-pill.active {{
      background: rgba(56, 189, 248, 0.15);
      border-color: var(--cyan);
      color: var(--cyan);
    }}
    @keyframes pulse {{
      0% {{ opacity: 0.4; }}
      50% {{ opacity: 1; }}
      100% {{ opacity: 0.4; }}
    }}
  </style>
</head>
<body>

  <!-- HEADER -->
  <div class="report-header">
    <div class="header-title-box">
      <h1>⚡ Virtual Shadow Quant Radar <span class="badge badge-purple">UNCONSTRAINED PAPER TRADE</span></h1>
      <div class="header-subtitle">
        Perekaman & Evaluasi Otomatis Sinyal Stage 1 Multi-Pair (Termasuk Sinyal Terkena Risk Gate / Cap MT5) | 
        Update: <span style="font-family:var(--font-mono);color:#fff;">{now_str}</span>
        <span id="live-indicator" style="margin-left:8px;font-family:var(--font-mono);font-size:11px;color:var(--text-dim);"><span style="color:var(--green);">&#9679;</span> LIVE &mdash; 30s Polling</span>
      </div>
    </div>
    <div class="header-actions">
      <button class="btn" onclick="location.reload();">🔄 Refresh Data</button>
      <a href="/dashboard" class="btn btn-primary">📈 Ke Cockpit Dashboard</a>
      <button class="btn" onclick="window.print();">🖨️ Print PDF</button>
    </div>
  </div>

  <!-- KPI SUMMARY -->
  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-title">Total Sinyal Radar</div>
      <div class="kpi-value" id="kpi-total" style="color:var(--purple);">{total_rec}</div>
      <div class="kpi-subtext">Aktif: <b id="kpi-active" style="color:var(--cyan);">{act_cnt}</b> │ Pending: <b id="kpi-pending" style="color:var(--amber);">{pend_cnt}</b></div>
    </div>
    <div class="kpi-card">
      <div class="kpi-title">Winrate Realized</div>
      <div class="kpi-value" id="kpi-winrate" style="color:var(--green);">{winrate:.1f}%</div>
      <div class="kpi-subtext">TP: <b id="kpi-tp" style="color:var(--green);">{tp_hits}</b> │ SL: <b id="kpi-sl" style="color:var(--red);">{sl_hits}</b> (Sample: {decisive})</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-title">Cumulative Net R</div>
      <div class="kpi-value" id="kpi-cumr" style="color:{net_r_color};">{'+' if cum_net_r >= 0 else ''}{cum_net_r:.2f}R</div>
      <div class="kpi-subtext">Expected Value: <b id="kpi-ev" style="color:{ev_color};">{'+' if ev_r >= 0 else ''}{ev_r:.2f}R / trade</b></div>
    </div>
    <div class="kpi-card">
      <div class="kpi-title">Eksekusi MT5 vs Skipped</div>
      <div class="kpi-value" id="kpi-exec" style="color:var(--cyan);">{disp_stats.get('EXECUTED_MT5', 0)} / {total_rec}</div>
      <div class="kpi-subtext">Risk Block: <b id="kpi-risk" style="color:var(--amber);">{disp_stats.get('SKIPPED_RISK_BASKET', 0) + disp_stats.get('SKIPPED_RISK_BLOCK', 0)}</b> │ Veto: <b id="kpi-veto" style="color:var(--red);">{disp_stats.get('SKIPPED_LLM_VETO', 0)}</b></div>
    </div>
  </div>

  <!-- DUAL GRID: MECHANISMS & DISPOSITION -->
  <div class="dual-grid">
    
    <!-- Left: Mechanism Breakdown -->
    <div>
      <div class="section-title">📊 Breakdown Performa Berdasarkan Mekanisme Radar</div>
      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th>Mekanisme</th>
              <th>Total</th>
              <th>TP</th>
              <th>SL</th>
              <th>Winrate</th>
              <th>Net R</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style="color:#fb923c;font-weight:700;">M1: Universal Liquidity Sweep</td>
              <td>{m1.get('total', 0)}</td>
              <td>{m1.get('tp', 0)}</td>
              <td>{m1.get('sl', 0)}</td>
              <td>{(m1.get('tp', 0) / (m1.get('tp', 0) + m1.get('sl', 0) or 1) * 100):.1f}%</td>
              <td style="font-weight:700;color:{'var(--green)' if m1.get('net_r', 0) >= 0 else 'var(--red)'};">{'+' if m1.get('net_r', 0) >= 0 else ''}{m1.get('net_r', 0):.2f}R</td>
            </tr>
            <tr>
              <td style="color:#38bdf8;font-weight:700;">M2: Trend-Aligned Pullback</td>
              <td>{m2.get('total', 0)}</td>
              <td>{m2.get('tp', 0)}</td>
              <td>{m2.get('sl', 0)}</td>
              <td>{(m2.get('tp', 0) / (m2.get('tp', 0) + m2.get('sl', 0) or 1) * 100):.1f}%</td>
              <td style="font-weight:700;color:{'var(--green)' if m2.get('net_r', 0) >= 0 else 'var(--red)'};">{'+' if m2.get('net_r', 0) >= 0 else ''}{m2.get('net_r', 0):.2f}R</td>
            </tr>
            <tr>
              <td style="color:#c084fc;font-weight:700;">M3: Breakout Retest Guard</td>
              <td>{m3.get('total', 0)}</td>
              <td>{m3.get('tp', 0)}</td>
              <td>{m3.get('sl', 0)}</td>
              <td>{(m3.get('tp', 0) / (m3.get('tp', 0) + m3.get('sl', 0) or 1) * 100):.1f}%</td>
              <td style="font-weight:700;color:{'var(--green)' if m3.get('net_r', 0) >= 0 else 'var(--red)'};">{'+' if m3.get('net_r', 0) >= 0 else ''}{m3.get('net_r', 0):.2f}R</td>
            </tr>
            <tr>
              <td style="color:#facc15;font-weight:700;">M4: Systemic Flow Continuation</td>
              <td>{m4.get('total', 0)}</td>
              <td>{m4.get('tp', 0)}</td>
              <td>{m4.get('sl', 0)}</td>
              <td>{(m4.get('tp', 0) / (m4.get('tp', 0) + m4.get('sl', 0) or 1) * 100):.1f}%</td>
              <td style="font-weight:700;color:{'var(--green)' if m4.get('net_r', 0) >= 0 else 'var(--red)'};">{'+' if m4.get('net_r', 0) >= 0 else ''}{m4.get('net_r', 0):.2f}R</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Right: MT5 Dispositions -->
    <div>
      <div class="section-title">🛡️ Status Disposisi Eksekusi MT5 (Risk Gate & Filter)</div>
      <div class="table-container">
        <table>
          <thead>
            <tr>
              <th>Status Disposisi MT5</th>
              <th>Jumlah Setup</th>
              <th>Keterangan Sistem</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><span class="badge" style="background:rgba(0,230,118,0.15);color:var(--green);border:1px solid rgba(0,230,118,0.3);">EXECUTED_MT5</span></td>
              <td style="font-weight:700;font-family:var(--font-mono);">{disp_stats.get('EXECUTED_MT5', 0)}</td>
              <td style="color:var(--text-dim);">Lolos seluruh filter & order riil berhasil dikirim ke MT5.</td>
            </tr>
            <tr>
              <td><span class="badge" style="background:rgba(192,132,252,0.15);color:#c084fc;border:1px solid rgba(192,132,252,0.3);">SKIPPED_MAX_POSITIONS</span></td>
              <td style="font-weight:700;font-family:var(--font-mono);">{disp_stats.get('SKIPPED_MAX_POSITIONS', 0)}</td>
              <td style="color:var(--text-dim);">Ditolak eksekusi karena slot MT5 penuh (6/6). Berjalan 100% sebagai Paper Trade murni.</td>
            </tr>
            <tr>
              <td><span class="badge" style="background:rgba(251,191,36,0.15);color:var(--amber);border:1px solid rgba(251,191,36,0.3);">SKIPPED_RISK_BASKET</span></td>
              <td style="font-weight:700;font-family:var(--font-mono);">{disp_stats.get('SKIPPED_RISK_BASKET', 0)}</td>
              <td style="color:var(--text-dim);">Ditolak karena batas konsentrasi mata uang (Max 3 posisi).</td>
            </tr>
            <tr>
              <td><span class="badge" style="background:rgba(251,146,60,0.15);color:#fb923c;border:1px solid rgba(251,146,60,0.3);">SKIPPED_RISK_BLOCK</span></td>
              <td style="font-weight:700;font-family:var(--font-mono);">{disp_stats.get('SKIPPED_RISK_BLOCK', 0)}</td>
              <td style="color:var(--text-dim);">Ditolak karena margin buffer, dead zone, atau pause loss.</td>
            </tr>
            <tr>
              <td><span class="badge" style="background:rgba(255,82,82,0.15);color:var(--red);border:1px solid rgba(255,82,82,0.3);">SKIPPED_LLM_VETO</span></td>
              <td style="font-weight:700;font-family:var(--font-mono);">{disp_stats.get('SKIPPED_LLM_VETO', 0)}</td>
              <td style="color:var(--text-dim);">Ditolak / diveto oleh sidang konsensus 3-LLM Jury.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

  </div>

  <!-- ORDER BOOK TABLE SECTION -->
  <div class="section-title">📋 Buku Order Virtual & Riwayat Telemetri Trade ({len(all_combined)} Total)</div>
  
  <div class="filter-bar">
    <input type="text" id="searchInput" class="search-input" placeholder="🔍 Cari simbol, setup, outcome, ID..." oninput="filterTable();">
    <button class="filter-pill active" onclick="setFilter('ALL', this);">Semua ({len(all_combined)})</button>
    <button class="filter-pill" onclick="setFilter('REAL_MT5', this);" style="border-color:rgba(0,230,118,0.4);color:var(--green);font-weight:700;">🟢 Real MT5 ({disp_stats.get('EXECUTED_MT5', 0)})</button>
    <button class="filter-pill" onclick="setFilter('PAPER_SHADOW', this);" style="border-color:rgba(192,132,252,0.4);color:#c084fc;font-weight:700;">🟣 Paper Shadow ({len(all_combined) - disp_stats.get('EXECUTED_MT5', 0)})</button>
    <button class="filter-pill" onclick="setFilter('ACTIVE', this);">Aktif ({act_cnt})</button>
    <button class="filter-pill" onclick="setFilter('PENDING', this);">Pending ({pend_cnt})</button>
    <button class="filter-pill" onclick="setFilter('TP_HIT', this);">TP Hit ({tp_hits})</button>
    <button class="filter-pill" onclick="setFilter('SL_HIT', this);">SL Hit ({sl_hits})</button>
    <button class="filter-pill" onclick="setFilter('RISK', this);">Risk Blocked</button>
  </div>

  <div class="table-container">
    <table id="tradesTable">
      <thead>
        <tr>
          <th>ID Shadow</th>
          <th>Waktu (WIB)</th>
          <th>Simbol</th>
          <th>Setup</th>
          <th>Arah</th>
          <th>Tipe</th>
          <th>Entry</th>
          <th>Harga Live</th>
          <th>SL</th>
          <th>TP</th>
          <th>R:R</th>
          <th>Status / Outcome</th>
          <th>Floating / Net R</th>
          <th>Peak MFE</th>
          <th>Max MAE</th>
          <th>Disposisi MT5</th>
        </tr>
      </thead>
      <tbody id="tableBody">
        <!-- Rendered by JS -->
      </tbody>
    </table>
  </div>

  <script>
    // ── LIVE POLLING ENGINE ─────────────────────────────────────────────
    const POLL_INTERVAL_MS = 30000; // 30 detik
    let allTrades = {trades_json};  // Initial data dari server render
    let currentFilter = 'ALL';
    let pollTimer = null;

    // ── RENDER TABLE ────────────────────────────────────────────────────
    function renderTableRows(trades) {{
      const tbody = document.getElementById('tableBody');
      if (!trades || trades.length === 0) {{
        tbody.innerHTML = `<tr><td colspan="16" style="text-align:center;padding:24px;color:var(--text-dim);">Tidak ada data order virtual yang cocok dengan filter.</td></tr>`;
        return;
      }}

      let html = '';
      trades.forEach(tr => {{
        const isBuy = (tr.direction === "BUY");
        const dirCol = isBuy ? "var(--green)" : "var(--red)";

        let outCol = "var(--text-dim)";
        if (tr.outcome === "TP_HIT" || tr.outcome === "TRAILING_SL_HIT") outCol = "var(--green)";
        else if (tr.outcome === "BEP_HIT") outCol = "var(--cyan)";
        else if (tr.outcome === "SL_HIT") outCol = "var(--red)";
        else if (tr.status === "ACTIVE") outCol = "var(--cyan)";
        else if (tr.status === "PENDING") outCol = "var(--amber)";

        // 1. Live Price calculation
        let livePriceStr = '—';
        let livePriceStyle = 'font-family:var(--font-mono);';
        if (tr.current_price !== undefined && tr.current_price !== null) {{
          livePriceStr = `${{tr.current_price}}`;
          if (tr.status === 'ACTIVE') {{
            livePriceStyle += 'font-weight:700;color:#fff;';
          }} else if (tr.status === 'PENDING') {{
            livePriceStyle += 'color:var(--amber);';
          }}
        }} else if (tr.exit_price !== undefined && tr.exit_price !== null) {{
          livePriceStr = `${{tr.exit_price}}`;
          livePriceStyle += 'color:var(--text-dim);';
        }}

        // 2. Floating / Net R calculation
        let pnlText = '—';
        let pnlCol = 'var(--text-dim)';
        if (tr.status === "ACTIVE") {{
          const flR = (tr.floating_r !== undefined && tr.floating_r !== null) ? Number(tr.floating_r) : null;
          const flPts = (tr.floating_points !== undefined && tr.floating_points !== null) ? Number(tr.floating_points) : null;
          if (flR !== null) {{
            pnlCol = flR >= 0 ? "var(--green)" : "var(--red)";
            const sign = flR >= 0 ? '+' : '';
            const ptsSign = (flPts !== null && flPts >= 0) ? '+' : '';
            const ptsPart = (flPts !== null) ? ` (${{ptsSign}}${{flPts}}p)` : '';
            pnlText = `${{sign}}${{flR.toFixed(2)}}R${{ptsPart}}`;
          }}
        }} else if (tr.status === "PENDING") {{
          const pts = (tr.floating_points !== undefined && tr.floating_points !== null) ? Math.abs(Number(tr.floating_points)) : null;
          pnlCol = "var(--amber)";
          pnlText = (pts !== null) ? `⏳ ${{pts}}p ke limit` : `⏳ Pending`;
        }} else if (tr.status === "RESOLVED") {{
          if (tr.net_r !== null && tr.net_r !== undefined) {{
            const rVal = Number(tr.net_r);
            pnlCol = rVal >= 0 ? "var(--green)" : "var(--red)";
            const sign = rVal >= 0 ? '+' : '';
            pnlText = `${{sign}}${{rVal.toFixed(2)}}R (${{tr.outcome || 'RESOLVED'}})`;
          }} else {{
            pnlText = tr.outcome || 'RESOLVED';
          }}
        }}

        const mfeText = (tr.peak_mfe_r !== undefined && tr.peak_mfe_r !== null) ? `+${{Number(tr.peak_mfe_r).toFixed(2)}}R` : '—';
        const maeText = (tr.max_mae_r !== undefined && tr.max_mae_r !== null) ? `${{Number(tr.max_mae_r).toFixed(2)}}R` : '—';

        const isMt5Real = String(tr.mt5_disposition || '').includes("EXECUTED");
        const ticketStr = tr.mt5_ticket ? `#${{tr.mt5_ticket}}` : '';
        const disp = tr.mt5_disposition || 'PENDING';

        let dispBadge = '';
        if (isMt5Real) {{
          dispBadge = `<span class="badge" style="background:var(--green-glow);color:var(--green);border:1px solid rgba(0,230,118,0.4);font-weight:700;">🟢 REAL MT5 ${{ticketStr}}</span>`;
        }} else if (disp.includes("MAX_POSITIONS") || disp.includes("SLOT")) {{
          dispBadge = `<span class="badge" style="background:rgba(192,132,252,0.18);color:#c084fc;border:1px solid rgba(192,132,252,0.4);font-weight:700;">🟣 PAPER (Slot 6/6 Full)</span>`;
        }} else if (disp.includes("BASKET")) {{
          dispBadge = `<span class="badge" style="background:rgba(251,191,36,0.18);color:var(--amber);border:1px solid rgba(251,191,36,0.35);font-weight:700;">🟣 PAPER (Basket Limit)</span>`;
        }} else if (disp.includes("RISK")) {{
          dispBadge = `<span class="badge" style="background:rgba(251,146,60,0.18);color:#fb923c;border:1px solid rgba(251,146,60,0.35);font-weight:700;">🟣 PAPER (Risk Blocked)</span>`;
        }} else if (disp.includes("VETO")) {{
          dispBadge = `<span class="badge" style="background:var(--red-glow);color:var(--red);border:1px solid rgba(255,82,82,0.35);font-weight:700;">🟣 PAPER (LLM Veto)</span>`;
        }} else {{
          dispBadge = `<span class="badge" style="background:rgba(148,163,184,0.15);color:var(--text-dim);border:1px solid rgba(148,163,184,0.3);font-weight:700;">🟣 PAPER SHADOW</span>`;
        }}

        let bepTrailBadge = '';
        if (tr.trailing_activated) {{
          bepTrailBadge = ` <span class="badge" style="background:rgba(56,189,248,0.2);color:var(--cyan);border:1px solid rgba(56,189,248,0.4);font-size:9.5px;padding:1px 5px;">TRAIL</span>`;
        }} else if (tr.bep_activated) {{
          bepTrailBadge = ` <span class="badge" style="background:rgba(0,230,118,0.2);color:var(--green);border:1px solid rgba(0,230,118,0.4);font-size:9.5px;padding:1px 5px;">BEP</span>`;
        }}

        const rowStyle = isMt5Real 
          ? `background:rgba(0, 230, 118, 0.035); border-left:3px solid var(--green);` 
          : `border-left:3px solid rgba(192, 132, 252, 0.35);`;

        const timeStr = tr.created_at ? tr.created_at.split('T')[1]?.split('.')[0] || tr.created_at : '-';

        html += `<tr style="${{rowStyle}}">
          <td style="font-family:var(--font-mono);font-size:10.5px;color:var(--text-dim);">${{tr.shadow_id}}</td>
          <td style="font-family:var(--font-mono);font-size:11px;">${{timeStr}}</td>
          <td style="font-weight:700;font-family:var(--font-mono);">${{tr.symbol}}</td>
          <td style="font-size:11px;color:var(--text-dim);">${{tr.setup_type}}</td>
          <td style="font-weight:700;color:${{dirCol}};">${{tr.direction}}</td>
          <td style="font-size:11px;color:var(--text-muted);">${{tr.entry_type || 'market'}}</td>
          <td style="font-family:var(--font-mono);">${{tr.entry_price}}</td>
          <td style="${{livePriceStyle}}">${{livePriceStr}}</td>
          <td style="font-family:var(--font-mono);color:var(--red);">${{tr.sl_price}}</td>
          <td style="font-family:var(--font-mono);color:var(--green);">${{tr.tp_price}}</td>
          <td style="font-family:var(--font-mono);font-weight:700;">${{tr.risk_reward || '—'}}R</td>
          <td style="font-weight:700;color:${{outCol}};font-family:var(--font-mono);">${{tr.outcome || tr.status}}${{bepTrailBadge}}</td>
          <td style="font-weight:800;color:${{pnlCol}};font-family:var(--font-mono);">${{pnlText}}</td>
          <td style="color:var(--green);font-family:var(--font-mono);">${{mfeText}}</td>
          <td style="color:var(--red);font-family:var(--font-mono);">${{maeText}}</td>
          <td>${{dispBadge}}</td>
        </tr>`;
      }});
      tbody.innerHTML = html;
    }}

    // ── FILTER ──────────────────────────────────────────────────────────
    function setFilter(filt, btn) {{
      currentFilter = filt;
      document.querySelectorAll('.filter-pill').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');
      filterTable();
    }}

    function filterTable() {{
      const q = (document.getElementById('searchInput').value || '').toLowerCase();
      const filtered = allTrades.filter(tr => {{
        if (currentFilter === 'REAL_MT5' && !String(tr.mt5_disposition || '').includes('EXECUTED')) return false;
        if (currentFilter === 'PAPER_SHADOW' && String(tr.mt5_disposition || '').includes('EXECUTED')) return false;
        if (currentFilter === 'ACTIVE' && tr.status !== 'ACTIVE') return false;
        if (currentFilter === 'PENDING' && tr.status !== 'PENDING') return false;
        if (currentFilter === 'TP_HIT' && tr.outcome !== 'TP_HIT') return false;
        if (currentFilter === 'SL_HIT' && tr.outcome !== 'SL_HIT') return false;
        if (currentFilter === 'RISK' && !String(tr.mt5_disposition || '').includes('RISK') && !String(tr.mt5_disposition || '').includes('BASKET') && !String(tr.mt5_disposition || '').includes('MAX_POSITIONS')) return false;
        if (q) {{
          const hay = `${{tr.shadow_id}} ${{tr.symbol}} ${{tr.setup_type}} ${{tr.direction}} ${{tr.outcome || tr.status}} ${{tr.mt5_disposition}} ${{tr.mt5_ticket || ''}}`.toLowerCase();
          if (!hay.includes(q)) return false;
        }}
        return true;
      }});
      renderTableRows(filtered);
    }}

    // ── KPI UPDATE ──────────────────────────────────────────────────────
    function updateKpiEl(id, val) {{
      const el = document.getElementById(id);
      if (el) el.textContent = val;
    }}

    function applyLiveData(data) {{
      if (!data || data.error) return;

      // Update trades array
      if (data.all_trades_combined && data.all_trades_combined.length >= 0) {{
        allTrades = data.all_trades_combined;
      }}

      // Update KPI cards
      const cumR = Number(data.cumulative_net_r || 0);
      const wr   = Number(data.winrate_pct || 0);
      const ev   = Number(data.expected_value_r || 0);
      updateKpiEl('kpi-total',   data.total_recorded || 0);
      updateKpiEl('kpi-active',  data.active_count || 0);
      updateKpiEl('kpi-resolved',data.total_resolved || 0);
      updateKpiEl('kpi-tp',      data.tp_hits || 0);
      updateKpiEl('kpi-sl',      data.sl_hits || 0);
      updateKpiEl('kpi-winrate', wr.toFixed(1) + '%');
      updateKpiEl('kpi-cumr',    (cumR >= 0 ? '+' : '') + cumR.toFixed(2) + 'R');
      updateKpiEl('kpi-ev',      (ev >= 0 ? '+' : '') + ev.toFixed(3) + 'R');

      // Update filter bar counters
      const totCnt   = allTrades.length;
      const realCnt  = allTrades.filter(t => String(t.mt5_disposition || '').includes('EXECUTED')).length;
      const paperCnt = totCnt - realCnt;
      const actCnt   = data.active_count || 0;
      const pendCnt  = data.pending_count || 0;
      const tpCnt    = data.tp_hits || 0;
      const slCnt    = data.sl_hits || 0;
      const pills = document.querySelectorAll('.filter-pill');
      if (pills[0]) pills[0].textContent = `Semua (${{totCnt}})`;
      if (pills[1]) pills[1].textContent = `🟢 Real MT5 (${{realCnt}})`;
      if (pills[2]) pills[2].textContent = `🟣 Paper Shadow (${{paperCnt}})`;
      if (pills[3]) pills[3].textContent = `Aktif (${{actCnt}})`;
      if (pills[4]) pills[4].textContent = `Pending (${{pendCnt}})`;
      if (pills[5]) pills[5].textContent = `TP Hit (${{tpCnt}})`;
      if (pills[6]) pills[6].textContent = `SL Hit (${{slCnt}})`;

      // Refresh tabel dengan filter aktif saat ini
      filterTable();

      // Update live indicator
      const ts = new Date().toLocaleTimeString('id-ID', {{hour:'2-digit', minute:'2-digit', second:'2-digit'}});
      const indEl = document.getElementById('live-indicator');
      if (indEl) indEl.innerHTML = `<span style="color:var(--green);animation:pulse 1s ease;">&#9679;</span> LIVE &mdash; Update: ${{ts}} WIB`;
    }}

    // ── POLLING LOOP ────────────────────────────────────────────────────
    function pollShadowData() {{
      fetch('/api/shadow', {{cache: 'no-store'}})
        .then(r => r.json())
        .then(data => applyLiveData(data))
        .catch(err => {{
          const indEl = document.getElementById('live-indicator');
          if (indEl) indEl.innerHTML = `<span style="color:var(--amber);">&#9679;</span> Reconnecting...`;
        }});
    }}

    // Initial render + start polling
    renderTableRows(allTrades);
    pollTimer = setInterval(pollShadowData, POLL_INTERVAL_MS);

    // Immediate first poll untuk sync data terkini
    setTimeout(pollShadowData, 2000);
  </script>
</body>
</html>
"""
    return html



def generate_and_save_shadow_report(out_file: Optional[str] = None) -> str:
    """Generates HTML report and saves to docs/quant_shadow_report.html."""
    if out_file is None:
        root_dir = getattr(config, "ROOT_DIR", os.path.dirname(config.DATA_DIR))
        out_file = os.path.join(root_dir, "docs", "quant_shadow_report.html")
    html_content = render_shadow_report_html()
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    return out_file


if __name__ == "__main__":
    saved_path = generate_and_save_shadow_report()
    print(f"[OK] Quant Shadow HTML Report saved to: {saved_path}")
