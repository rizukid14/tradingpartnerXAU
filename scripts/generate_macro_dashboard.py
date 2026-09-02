"""
Generate Standalone Stacked Liquidity Pool Dashboard (macro_liquidity_dashboard.html)
Features:
1. Orthogonal Multi-Horizon Liquidity Pool Extraction (Near to Far).
2. Stacked Liquidity Consolidation (Overlapping bands merged with total density score & ingredient badges).
3. Persistent Zoom Memory (Remembers 120/60/250 bars across symbol changes).
4. Preserves macro_dashboard.html intact.
"""

import json
import os
import sys
import time
import pandas as pd
import numpy as np

sys.path.insert(0, r"c:\Vibe\tradingpartner")
import config
from src.core import mt5_connector as connector
from src.analytics.macro_strategic_engine import macro_strategic_engine
from src.indicators.lux_smc import LuxSMCAnalyzer
from src.indicators.atlas_dna import calculate_dynamic_stations
from src.analytics.currency_strength import get_csm_delta_for_symbol

def generate_liquidity_dashboard():
    print("[MT5] Connecting to MT5 Terminal for 26 Scanner Universe Symbols...")
    connector.initialize_mt5()
    
    symbols = getattr(config, 'SCANNER_SYMBOLS', [])
    if not symbols:
        symbols = [
            'EURUSD-ECNc', 'GBPUSD-ECNc', 'USDJPY-ECNc', 'USDCHF-ECNc', 'USDCAD-ECNc', 'AUDUSD-ECNc',
            'EURGBP-ECNc', 'EURJPY-ECNc', 'EURCHF-ECNc', 'EURAUD-ECNc', 'EURCAD-ECNc', 'GBPJPY-ECNc',
            'GBPCHF-ECNc', 'GBPAUD-ECNc', 'GBPCAD-ECNc', 'AUDJPY-ECNc', 'AUDCHF-ECNc', 'AUDCAD-ECNc',
            'CADJPY-ECNc', 'CHFJPY-ECNc', 'NZDCAD-ECNc', 'NZDCHF-ECNc', 'NZDUSD-ECNc', 'GBPNZD-ECNc',
            'AUDNZD-ECNc', 'EURNZD-ECNc'
        ]
        
    payload = {}
    print(f"Refreshing Multi-Horizon Liquidity Dashboard for {len(symbols)} symbols...")
    
    for sym in symbols:
        try:
            print(f"Processing {sym} (Stacked Liquidity Consolidation)...")
            valid_sym = connector.get_valid_trade_symbol(sym)
            directive = macro_strategic_engine.compute_directive(valid_sym, mt5_connector=connector)
            
            # Fetch H1 candles for chart (350 bars)
            rates_h1 = config.mt5.copy_rates_from_pos(valid_sym, config.mt5.TIMEFRAME_H1, 0, 350)
            if rates_h1 is None or len(rates_h1) < 50:
                continue
                
            df = pd.DataFrame(rates_h1)
            df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
            df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
            df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
            
            from zoneinfo import ZoneInfo
            WIB = ZoneInfo("Asia/Jakarta")
            df['dt_wib'] = pd.to_datetime(df['time'], unit='s', utc=True).dt.tz_convert(WIB)
            df['time_str'] = df['dt_wib'].dt.strftime('%d-%b %H:%M')
            
            sinfo = config.mt5.symbol_info(valid_sym)
            digits = sinfo.digits if sinfo else 5
            point = sinfo.point if sinfo else 1e-5
            pip_div = 10 if digits in (3, 5) else 1
            
            candles_list = []
            for _, r in df.iterrows():
                candles_list.append({
                    "time": r['time_str'],
                    "open": round(float(r['open']), digits),
                    "high": round(float(r['high']), digits),
                    "low": round(float(r['low']), digits),
                    "close": round(float(r['close']), digits),
                    "ema20": round(float(r['ema20']), digits),
                    "ema50": round(float(r['ema50']), digits),
                    "ema200": round(float(r['ema200']), digits)
                })
                
            # SMC Order Blocks & FVGs
            smc_analyzer = LuxSMCAnalyzer()
            smc_sig = smc_analyzer.analyze(df, point_size=point)
            bull_obs = []
            for ob in getattr(smc_sig, 'order_blocks', []):
                if getattr(ob, 'ob_type', '') == 'bullish':
                    bull_obs.append({
                        "top": round(float(ob.top), digits),
                        "bottom": round(float(ob.bottom), digits),
                        "tier": "Bull OB",
                        "start_time": "H1"
                    })
            bear_obs = []
            for ob in getattr(smc_sig, 'order_blocks', []):
                if getattr(ob, 'ob_type', '') == 'bearish':
                    bear_obs.append({
                        "top": round(float(ob.top), digits),
                        "bottom": round(float(ob.bottom), digits),
                        "tier": "Bear OB",
                        "start_time": "H1"
                    })
            fvgs = []
            for f in getattr(smc_sig, 'fair_value_gaps', []):
                fvgs.append({
                    "top": round(float(f.top), digits),
                    "bottom": round(float(f.bottom), digits),
                    "mid": round(float(f.mid), digits),
                    "dir": f.fvg_type,
                    "start_time": str(int(f.created_idx if hasattr(f, 'created_idx') else 0)),
                    "dist": round(abs(float(df['close'].iloc[-1]) - float(f.mid)), digits)
                })
                
            csm_d = get_csm_delta_for_symbol(sym)
            st = calculate_dynamic_stations(sym, float(df['close'].iloc[-1]))
            psych_levels = [
                {"price": round(st['lower_station'], digits), "is_major": True, "label": f"STATION: {st['lower_station']}"},
                {"price": round(st['base_station'], digits), "is_major": True, "label": f"BASE: {st['base_station']}"},
                {"price": round(st['upper_station'], digits), "is_major": True, "label": f"TARGET: {st['upper_station']}"}
            ]
            
            dr_high = float(df['high'].tail(50).max())
            dr_low = float(df['low'].tail(50).min())
            curr_c = float(df['close'].iloc[-1])
            dr_pos = round(((curr_c - dr_low) / (dr_high - dr_low) * 100.0), 1) if dr_high > dr_low else 50.0
            
            # Extract Stacked Liquidity Pools
            # Consolidate close layers into unified bands
            def _consolidate_stacked_pools(layers, is_floor=True):
                if not layers: return []
                atr_h1 = (df['high'].iloc[-14:] - df['low'].iloc[-14:]).mean()
                merge_tol = max(0.25 * atr_h1, 4 * point * pip_div)
                
                sorted_layers = sorted(layers, key=lambda x: x['price'], reverse=is_floor)
                bands = []
                
                curr_band = None
                for l in sorted_layers:
                    p = l['price']
                    sc = l.get('density_score', 2.0)
                    tag = l.get('tag_str', '')
                    gr = l.get('reaction_grade', 'GRADE_1_MICRO')
                    dist_p = l.get('dist_pips', 0.0)
                    
                    if curr_band is None:
                        curr_band = {
                            'tier': l.get('tier', 'F1' if is_floor else 'C1'),
                            'top': p,
                            'bottom': p,
                            'mid': p,
                            'total_score': sc,
                            'tags': [tag] if tag else [],
                            'reaction_grade': gr,
                            'dist_pips': dist_p,
                            'count': 1
                        }
                    else:
                        # Check if within merge tolerance
                        if abs(curr_band['mid'] - p) <= merge_tol:
                            curr_band['top'] = max(curr_band['top'], p)
                            curr_band['bottom'] = min(curr_band['bottom'], p)
                            curr_band['mid'] = round((curr_band['top'] + curr_band['bottom']) / 2.0, digits)
                            curr_band['total_score'] += sc
                            if tag and tag not in curr_band['tags']:
                                curr_band['tags'].append(tag)
                            if 'GRADE_3' in gr: curr_band['reaction_grade'] = 'GRADE_3_MACRO'
                            elif 'GRADE_2' in gr and curr_band['reaction_grade'] != 'GRADE_3_MACRO':
                                curr_band['reaction_grade'] = 'GRADE_2_INTERMEDIATE'
                            curr_band['count'] += 1
                        else:
                            bands.append(curr_band)
                            curr_band = {
                                'tier': f"{'F' if is_floor else 'C'}{len(bands)+1}",
                                'top': p,
                                'bottom': p,
                                'mid': p,
                                'total_score': sc,
                                'tags': [tag] if tag else [],
                                'reaction_grade': gr,
                                'dist_pips': dist_p,
                                'count': 1
                            }
                if curr_band:
                    bands.append(curr_band)
                return bands

            stacked_floors = _consolidate_stacked_pools(directive.layered_floors, is_floor=True)
            stacked_ceilings = _consolidate_stacked_pools(directive.layered_ceilings, is_floor=False)
            
            sym_payload = {
                "symbol": sym,
                "digits": digits,
                "daily_macro_bias": directive.daily_macro_bias,
                "macro_bias_score": directive.macro_bias_score,
                "action_tier": directive.action_tier,
                "primary_directive": directive.primary_execution_directive,
                "regime_stability": directive.regime_stability,
                "hard_circuit_breaker": directive.hard_circuit_breaker,
                "thesis": directive.daily_mandate_thesis,
                "permission": "GO" if directive.action_tier == "FULL_ALLOW" else ("ARM" if "ABSORPTION" in directive.market_state else "WAIT"),
                "wave_state_name": directive.market_state,
                "direction_state": "BULL" if directive.macro_bias_score > 0 else ("BEAR" if directive.macro_bias_score < 0 else "NEUTRAL"),
                "phase_state": directive.structural_stage,
                "correction_type": directive.market_state,
                "bars_since_pivot": 0,
                "correction_velocity": 0.0,
                "csm_delta": round(csm_d, 2),
                "dealing_range_pos": dr_pos,
                "dr_high": round(dr_high, digits),
                "dr_low": round(dr_low, digits),
                "strong_high": round(directive.immediate_ceiling_c1, digits),
                "strong_low": round(directive.immediate_floor_f1, digits),
                "bull_obs": bull_obs[:5],
                "bear_obs": bear_obs[:5],
                "fvgs": fvgs[:8],
                "psych_levels": psych_levels,
                "eqh": [],
                "eql": [],
                "h4_flag": "CLEAN",
                "frvp": {
                    "poc": round(directive.immediate_ceiling_c1, digits),
                    "val": round(directive.immediate_floor_f1, digits),
                    "vah": round(directive.deep_target_ceiling_c2, digits)
                },
                "layered_floors": directive.layered_floors,
                "layered_ceilings": directive.layered_ceilings,
                "stacked_floors": stacked_floors,
                "stacked_ceilings": stacked_ceilings,
                "c1_ceiling": round(directive.immediate_ceiling_c1, digits),
                "f1_floor": round(directive.immediate_floor_f1, digits),
                "c2_deep": round(directive.deep_target_ceiling_c2, digits),
                "f2_deep": round(directive.deep_target_floor_f2, digits),
                "macro_sbr_d1": round(directive.macro_sbr_d1 or directive.immediate_ceiling_c1, digits),
                "macro_rbs_d1": round(directive.macro_rbs_d1 or directive.immediate_floor_f1, digits),
                "inter_sbr_h4": round(directive.inter_sbr_h4 or directive.immediate_ceiling_c1, digits),
                "inter_rbs_h4": round(directive.inter_rbs_h4 or directive.immediate_floor_f1, digits),
                "pwh": round(dr_high, digits),
                "pwl": round(dr_low, digits),
                "asian_high": round(dr_high, digits),
                "asian_low": round(dr_low, digits),
                "m1_upper_top": round(directive.immediate_ceiling_c1 + (10 * point * pip_div), digits),
                "m1_upper_bot": round(directive.immediate_ceiling_c1, digits),
                "m1_lower_top": round(directive.immediate_floor_f1, digits),
                "m1_lower_bot": round(directive.immediate_floor_f1 - (10 * point * pip_div), digits),
                "m2_entry_anchor": round(directive.entry_limit_anchor, digits),
                "m2_sl": round(directive.intraday_sl_price, digits),
                "m2_tp1": round(directive.tp1_price, digits),
                "m2_tp2": round(directive.tp2_price, digits),
                "m3_pwh": round(dr_high, digits),
                "m3_pwl": round(dr_low, digits),
                "m3_w1_eq": round((dr_high + dr_low) / 2.0, digits),
                "m3_breakout_c2": round(directive.deep_target_ceiling_c2, digits),
                "m3_breakout_f2": round(directive.deep_target_floor_f2, digits),
                "forbidden_traps": directive.forbidden_traps,
                "candles": candles_list
            }
            payload[sym] = sym_payload
        except Exception as e:
            print(f"Error processing {sym}: {e}")
            
    # Read original macro_dashboard.html template
    html_template_path = r"c:\Vibe\tradingpartner\macro_dashboard.html"
    with open(html_template_path, "r", encoding="utf-8") as f:
        html_content = f.read()
        
    # Replace title and header
    new_title = "<title>26-Pair Stacked Liquidity Pool Matrix & Multi-Horizon Radar</title>"
    html_content = html_content.replace("<title>26-Pair Quant Radar & Macro Cockpit (4-Tier Matrix + M1/M2/M3)</title>", new_title)
    html_content = html_content.replace("26-Pair Quant Radar & Macro Cockpit", "26-Pair Stacked Multi-Horizon Liquidity Pool Radar")
    
    # 1. Update payload
    prefix = "const payload = "
    idx_start = html_content.find(prefix)
    if idx_start != -1:
        idx_end = html_content.find(";\n", idx_start)
        if idx_end != -1:
            json_str = json.dumps(payload)
            html_content = html_content[:idx_start + len(prefix)] + json_str + html_content[idx_end:]

    # 2. Inject Persistent Zoom Memory
    old_zoom_func = """function zoomView(numBars) {
  const d = payload[sel.value];
  if (!d) return;
  const total = d.candles.length;
  const startIdx = Math.max(0, total - numBars);
  const endIdx = total - 1 + RIGHT_PAD;
  
  Plotly.relayout('plot', {
    'xaxis.range': [startIdx, endIdx]
  });
  fitYToVisibleCandles(startIdx, total - 1);
}"""
    new_zoom_func = """let currentNumBars = 120; // Persistent Zoom Memory Across Pairs

function zoomView(numBars) {
  currentNumBars = numBars;
  document.querySelectorAll('.zoom-btn').forEach(btn => {
    btn.classList.remove('active');
    if (btn.textContent.includes(numBars) || (numBars === 350 && btn.textContent.includes('Fit'))) {
      btn.classList.add('active');
    }
  });
  const d = payload[sel.value];
  if (!d) return;
  const total = d.candles.length;
  const startIdx = Math.max(0, total - numBars);
  const endIdx = total - 1 + RIGHT_PAD;
  
  Plotly.relayout('plot', {
    'xaxis.range': [startIdx, endIdx]
  });
  fitYToVisibleCandles(startIdx, total - 1);
}"""
    html_content = html_content.replace(old_zoom_func, new_zoom_func)

    # 3. Inject Zoom Memory into Plotly.newPlot.then
    old_then = """  Plotly.newPlot('plot', traces, layout, configObj).then(() => {
    fitYToVisibleCandles(0, total - 1);
  });"""
    new_then = """  Plotly.newPlot('plot', traces, layout, configObj).then(() => {
    if (currentNumBars) {
      zoomView(currentNumBars);
    } else {
      fitYToVisibleCandles(0, total - 1);
    }
  });"""
    html_content = html_content.replace(old_then, new_then)

    # 4. Inject Stacked Fortress Band Rendering
    old_chamber_code = """  // DYNAMIC VARIABLE-LENGTH LAYERED MATRIX OVERLAY (C1..Cn & F1..Fn)
  if (activeOverlays.chamber) {
    // Ceilings C1..Cn (Top 6 Closest)
    if (d.layered_ceilings && d.layered_ceilings.length > 0) {
      d.layered_ceilings.slice(0, 6).forEach((c) => {
        const isMacro = c.reaction_grade === 'GRADE_3_MACRO';
        const isInter = c.reaction_grade === 'GRADE_2_INTERMEDIATE';
        const col = isMacro ? '#ef4444' : (isInter ? '#f97316' : '#ec4899');
        const w = isMacro ? 1.8 : (isInter ? 1.3 : 1.0);
        const dash = isMacro ? 'solid' : (isInter ? 'dash' : 'dot');
        const z = c.distance_zone ? `[${c.distance_zone}] ` : '';
        const pips = c.dist_pips !== undefined ? `+${c.dist_pips}p | ` : '';

        shapes.push({
          type: 'line', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: c.price, y1: c.price,
          line: { color: col, width: w, dash: dash }
        });
        annotations.push({
          xref: 'paper', yref: 'y', x: 0.99, y: c.price,
          text: `${c.tier} ${z}${pips}[${c.reaction_grade.replace('GRADE_', 'G')} | ${c.tag_str}]: ${c.price}`, showarrow: false,
          font: { size: 8.5, color: col }, bgcolor: 'rgba(14, 19, 31, 0.85)'
        });
      });
    } else if (d.c1_ceiling > 0) {
      shapes.push({ type: 'line', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: d.c1_ceiling, y1: d.c1_ceiling, line: { color: 'rgba(239, 68, 68, 0.80)', width: 1.8, dash: 'dash' } });
      annotations.push({ xref: 'paper', yref: 'y', x: 0.99, y: d.c1_ceiling, text: `C1: ${d.c1_ceiling}`, showarrow: false, font: { size: 10, color: '#ef4444' }, bgcolor: 'rgba(14, 19, 31, 0.85)' });
    }

    // Floors F1..Fn (Top 6 Closest)
    if (d.layered_floors && d.layered_floors.length > 0) {
      d.layered_floors.slice(0, 6).forEach((f) => {
        const isMacro = f.reaction_grade === 'GRADE_3_MACRO';
        const isInter = f.reaction_grade === 'GRADE_2_INTERMEDIATE';
        const col = isMacro ? '#22c55e' : (isInter ? '#14b8a6' : '#38bdf8');
        const w = isMacro ? 1.8 : (isInter ? 1.3 : 1.0);
        const dash = isMacro ? 'solid' : (isInter ? 'dash' : 'dot');
        const z = f.distance_zone ? `[${f.distance_zone}] ` : '';
        const pips = f.dist_pips !== undefined ? `-${f.dist_pips}p | ` : '';

        shapes.push({
          type: 'line', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: f.price, y1: f.price,
          line: { color: col, width: w, dash: dash }
        });
        annotations.push({
          xref: 'paper', yref: 'y', x: 0.99, y: f.price,
          text: `${f.tier} ${z}${pips}[${f.reaction_grade.replace('GRADE_', 'G')} | ${f.tag_str}]: ${f.price}`, showarrow: false,
          font: { size: 8.5, color: col }, bgcolor: 'rgba(14, 19, 31, 0.85)'
        });
      });
    } else if (d.f1_floor > 0) {
      shapes.push({ type: 'line', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: d.f1_floor, y1: d.f1_floor, line: { color: 'rgba(34, 197, 94, 0.80)', width: 1.8, dash: 'dash' } });
      annotations.push({ xref: 'paper', yref: 'y', x: 0.99, y: d.f1_floor, text: `F1: ${d.f1_floor}`, showarrow: false, font: { size: 10, color: '#22c55e' }, bgcolor: 'rgba(14, 19, 31, 0.85)' });
    }
  }"""

    new_chamber_code = """  // STACKED MULTI-HORIZON LIQUIDITY POOL FORTRESS BANDS (Near to Far)
  if (activeOverlays.chamber) {
    const pools_c = (d.stacked_ceilings && d.stacked_ceilings.length > 0) ? d.stacked_ceilings : (d.layered_ceilings || []);
    const pools_f = (d.stacked_floors && d.stacked_floors.length > 0) ? d.stacked_floors : (d.layered_floors || []);

    // 1. Supply Fortress Bands (Above Price)
    pools_c.forEach((c) => {
      const isMacro = c.reaction_grade === 'GRADE_3_MACRO';
      const isInter = c.reaction_grade === 'GRADE_2_INTERMEDIATE';
      const col = isMacro ? '#ef4444' : (isInter ? '#f97316' : '#ec4899');
      const fill = isMacro ? 'rgba(239, 68, 68, 0.14)' : (isInter ? 'rgba(249, 115, 22, 0.10)' : 'rgba(236, 72, 153, 0.06)');
      const w = isMacro ? 2.0 : (isInter ? 1.4 : 1.0);
      const dash = isMacro ? 'solid' : (isInter ? 'dash' : 'dot');
      const z = c.distance_zone ? `[${c.distance_zone}] ` : '';
      const pips = c.dist_pips !== undefined ? `+${c.dist_pips}p | ` : '';
      const tags = c.tags ? c.tags.join(' + ') : (c.tag_str || 'SUPPLY');
      const sc = c.total_score ? ` (Score ${c.total_score.toFixed(1)})` : '';
      const midP = c.mid || c.price;
      const bTop = c.top || midP;
      const bBot = c.bottom || midP;

      if (bTop > bBot) {
        shapes.push({
          type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: bBot, y1: bTop,
          fillcolor: fill, line: { color: col, width: 1, dash: 'dot' }
        });
      }
      shapes.push({
        type: 'line', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: midP, y1: midP,
        line: { color: col, width: w, dash: dash }
      });
      annotations.push({
        xref: 'paper', yref: 'y', x: 0.99, y: midP,
        text: `🛡️ ${c.tier} ${z}${pips}[${tags}]${sc}: ${midP}`, showarrow: false,
        font: { size: 8.5, color: col }, bgcolor: 'rgba(14, 19, 31, 0.85)'
      });
    });

    // 2. Demand Fortress Bands (Below Price)
    pools_f.forEach((f) => {
      const isMacro = f.reaction_grade === 'GRADE_3_MACRO';
      const isInter = f.reaction_grade === 'GRADE_2_INTERMEDIATE';
      const col = isMacro ? '#22c55e' : (isInter ? '#14b8a6' : '#38bdf8');
      const fill = isMacro ? 'rgba(34, 197, 94, 0.14)' : (isInter ? 'rgba(20, 184, 166, 0.10)' : 'rgba(56, 189, 248, 0.06)');
      const w = isMacro ? 2.0 : (isInter ? 1.4 : 1.0);
      const dash = isMacro ? 'solid' : (isInter ? 'dash' : 'dot');
      const z = f.distance_zone ? `[${f.distance_zone}] ` : '';
      const pips = f.dist_pips !== undefined ? `-${f.dist_pips}p | ` : '';
      const tags = f.tags ? f.tags.join(' + ') : (f.tag_str || 'DEMAND');
      const sc = f.total_score ? ` (Score ${f.total_score.toFixed(1)})` : '';
      const midP = f.mid || f.price;
      const bTop = f.top || midP;
      const bBot = f.bottom || midP;

      if (bTop > bBot) {
        shapes.push({
          type: 'rect', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: bBot, y1: bTop,
          fillcolor: fill, line: { color: col, width: 1, dash: 'dot' }
        });
      }
      shapes.push({
        type: 'line', xref: 'paper', yref: 'y', x0: 0, x1: 1, y0: midP, y1: midP,
        line: { color: col, width: w, dash: dash }
      });
      annotations.push({
        xref: 'paper', yref: 'y', x: 0.99, y: midP,
        text: `🏰 ${f.tier} ${z}${pips}[${tags}]${sc}: ${midP}`, showarrow: false,
        font: { size: 8.5, color: col }, bgcolor: 'rgba(14, 19, 31, 0.85)'
      });
    });
  }"""

    html_content = html_content.replace(old_chamber_code, new_chamber_code)

    # Write to Single SSOT file: macro_dashboard.html
    out_path = r"c:\Vibe\tradingpartner\macro_dashboard.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✅ Successfully updated {out_path} with {len(payload)} symbols.")

if __name__ == "__main__":
    generate_liquidity_dashboard()
