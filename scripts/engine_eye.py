"""
engine_eye.py — "Mata" X-ray: render apa yang engine lihat saat ini ke satu file HTML mandiri.

Prinsip:
- TIDAK re-implementasi apa pun. Skrip ini meng-instantiate MarketScanner yang SAMA
  dengan produksi (main.py), memanggil _refresh_zce_rotation() + update_macro_context(),
  lalu men-serialisasi macro_cache + _zce_maps ke HTML statis (zero CDN, zero JS chart lib).
- Output: docs/engine_eye.html (default). Bisa di-refresh kapan saja dengan menjalankan ulang.

Cara pakai:
    python scripts/engine_eye.py
    python scripts/engine_eye.py --pairs EURUSD,GBPUSD,USDJPY,AUDUSD
    python scripts/engine_eye.py --out docs/engine_eye.html --bars 120

Catatan:
- Membutuhkan MT5 terminal aktif (sama seperti bot). Read-only: tidak ada order dikirim.
- Simbol akan di-resolve via connector.get_valid_trade_symbol() (suffix -ECNc otomatis).
"""

import argparse
import json
import sys
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

WIB = ZoneInfo("Asia/Jakarta")

# ── bootstrap: pastikan root proyek ada di sys.path ──────────────────────────
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

import config
from src.core import mt5_connector as connector
from src.analytics.market_scanner import MarketScanner

DEFAULT_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "EURJPY", "GBPJPY"]

# mapping aksi tier → permission (sama dgn arsitektur / market_scanner)
TIER2PERM = {
    "FULL_ALLOW": "GO",
    "REDUCED_CONFIDENCE": "ARM",
    "TP1_ONLY_SCALP": "ARM",
    "WATCH_ONLY": "WATCH",
    "HARD_BLOCK": "LOCK",
}
TIER2LABEL = {
    "FULL_ALLOW": "🟢 FULL ALLOW — setup searah makro, risk 100%",
    "REDUCED_CONFIDENCE": "🟡 REDUCED — makro netral/moderat, risk 0.75x",
    "TP1_ONLY_SCALP": "🟠 TP1 ONLY — counter-trend berkualitas, TP1 tunggal",
    "WATCH_ONLY": "🔵 WATCH ONLY — di reload zone, trigger belum konfirm",
    "HARD_BLOCK": "🔴 HARD BLOCK — hard trap / invalidasi makro (0 token)",
}
PERM_COLOR = {"GO": "#00e676", "ARM": "#ffd740", "WATCH": "#40c4ff", "LOCK": "#ff5252"}


def pick(d: dict, *keys, default=None):
    """Ambil nilai pertama yang ada (defensif thd beda nama key)."""
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None:
            return d[k]
    return default


def fmt_price(v, digits=5):
    if v is None:
        return "—"
    try:
        return f"{float(v):.{int(digits)}f}"
    except Exception:
        return str(v)


def to_jsonable(obj, depth=0):
    """Konversi objek engine (dict/dataclass/objek) menjadi struktur JSON murni."""
    if depth > 6:
        return str(obj)
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(x, depth + 1) for x in obj]
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v, depth + 1) for k, v in obj.items()}
    if hasattr(obj, "__dict__"):
        return {k: to_jsonable(v, depth + 1) for k, v in vars(obj).items()}
    try:
        return str(obj)
    except Exception:
        return "<unserializable>"


def zce_source_of(macro: dict, zce_map, side: str):
    """Tentukan sumber dinding F1/C1: 'ZCE' bila macro == wall_override ZCE, else 'MSE'."""
    try:
        macro_price = pick(macro, f"immediate_floor_{side}", f"immediate_ceiling_{side}") \
            if side in ("f1",) else pick(macro, "immediate_ceiling_c1")
    except Exception:
        macro_price = None
    if side == "f1":
        macro_price = pick(macro, "immediate_floor_f1")
        zce_price = None
        try:
            wo = getattr(zce_map, "wall_override", None) or {}
            zce_price = wo.get("imm_floor_f1")
        except Exception:
            zce_price = None
    else:
        macro_price = pick(macro, "immediate_ceiling_c1")
        zce_price = None
        try:
            wo = getattr(zce_map, "wall_override", None) or {}
            zce_price = wo.get("imm_ceiling_c1")
        except Exception:
            zce_price = None
    if zce_price is None:
        return "MSE"
    try:
        return "ZCE" if abs(float(macro_price or 0) - float(zce_price)) < 1e-9 else "MSE"
    except Exception:
        return "MSE"


def build_svg_chart(bars, levels, digits=5, width=940, height=420):
    """Candlestick H1 sederhana + garis level, murni SVG string."""
    if not bars:
        return "<div class='muted'>Data H1 tidak tersedia (MT5 belum feed).</div>"

    closes = [b["close"] for b in bars]
    lo = min(b["low"] for b in bars)
    hi = max(b["high"] for b in bars)

    # perluas range supaya level di luar candle tetap terlihat (kalau wajar)
    all_lv = [lv["price"] for lv in levels if lv.get("price") is not None]
    if all_lv:
        lo = min(lo, min(all_lv))
        hi = max(hi, max(all_lv))
    pad = (hi - lo) * 0.06 or 0.0005
    lo -= pad
    hi += pad

    def y_of(p):
        return 8 + (hi - float(p)) / (hi - lo) * (height - 16)

    n = len(bars)
    cw = width / n
    body_w = max(1.0, cw * 0.62)
    up = "#26a69a"
    down = "#ef5350"

    parts = []
    for i, b in enumerate(bars):
        x = i * cw + cw / 2
        o, c, h, l = b["open"], b["close"], b["high"], b["low"]
        color = up if c >= o else down
        yc, yo = y_of(c), y_of(o)
        # wick
        parts.append(
            f'<line x1="{x:.1f}" y1="{y_of(h):.1f}" x2="{x:.1f}" y2="{y_of(l):.1f}" '
            f'stroke="{color}" stroke-width="1"/>'
        )
        # body
        y_top, h_body = min(yc, yo), abs(yc - yo) or 1.0
        parts.append(
            f'<rect x="{x - body_w / 2:.1f}" y="{y_top:.1f}" width="{body_w:.1f}" '
            f'height="{h_body:.1f}" fill="{color}" rx="0.5"/>'
        )

    # garis level (di atas candle)
    for lv in levels:
        price = lv.get("price")
        if price is None:
            continue
        y = y_of(price)
        label = lv.get("label", "")
        color = lv.get("color", "#9e9e9e")
        dash = lv.get("dash", "")
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(
            f'<line x1="0" y1="{y:.1f}" x2="{width}" y2="{y:.1f}" '
            f'stroke="{color}" stroke-width="1.1" opacity="0.9"{dash_attr}/>'
        )
        # kotak label di kanan
        txt = f"{label} {fmt_price(price, digits)}"
        parts.append(
            f'<rect x="{width - 8 - len(txt) * 6.1:.0f}" y="{y - 9:.1f}" width="{len(txt) * 6.1 + 8:.0f}" '
            f'height="13" rx="2" fill="rgba(13,17,23,0.85)" stroke="{color}" stroke-width="0.6"/>'
        )
        parts.append(
            f'<text x="{width - 4}" y="{y + 2.5:.1f}" font-size="9" fill="{color}" '
            f'text-anchor="end" font-family="Consolas,monospace">{txt}</text>'
        )

    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'preserveAspectRatio="xMidYMid meet" style="background:#0d1117;border-radius:6px">'
        + "".join(parts)
        + "</svg>"
    )


def collect_levels(macro: dict, digits: int, zce_map=None):
    """Level yang digambar di chart — dinding aktual + konteks makro."""
    levels = []
    c1 = pick(macro, "immediate_ceiling_c1")
    f1 = pick(macro, "immediate_floor_f1")
    c2 = pick(macro, "ceiling_c2", "ceiling2", "deep_ceiling")
    f2 = pick(macro, "floor_f2", "floor2", "deep_floor")
    drh = pick(macro, "dealing_range_high", "dr_high")
    drl = pick(macro, "dealing_range_low", "dr_low")
    pwh = pick(macro, "pwh", "macro_pwh")
    pwl = pick(macro, "pwl", "macro_pwl")
    rbs = pick(macro, "macro_rbs_d1", "macro_rbs_h4", "rbs_d1")
    sbr = pick(macro, "macro_sbr_d1", "macro_sbr_h4", "sbr_d1")
    sub_c = pick(macro, "sub_ceiling", "sub_c1")
    sub_f = pick(macro, "sub_floor", "sub_f1")

    if c1 is not None:
        src = "ZCE" if zce_map is not None and zce_source_of(macro, zce_map, "c1") == "ZCE" else "MSE"
        levels.append({"price": c1, "label": f"C1 ▲ [{src}]", "color": "#ff5252"})
    if f1 is not None:
        src = "ZCE" if zce_map is not None and zce_source_of(macro, zce_map, "f1") == "ZCE" else "MSE"
        levels.append({"price": f1, "label": f"F1 ▼ [{src}]", "color": "#00e676"})
    if c2 is not None:
        levels.append({"price": c2, "label": "C2", "color": "#ff8a80", "dash": "5 4"})
    if f2 is not None:
        levels.append({"price": f2, "label": "F2", "color": "#69f0ae", "dash": "5 4"})
    if drh is not None:
        levels.append({"price": drh, "label": "DR High", "color": "#ffb300", "dash": "2 3"})
    if drl is not None:
        levels.append({"price": drl, "label": "DR Low", "color": "#ffb300", "dash": "2 3"})
    if pwh is not None:
        levels.append({"price": pwh, "label": "PWH", "color": "#b39ddb", "dash": "8 3"})
    if pwl is not None:
        levels.append({"price": pwl, "label": "PWL", "color": "#b39ddb", "dash": "8 3"})
    if sbr is not None:
        levels.append({"price": sbr, "label": "SBR(D1/H4)", "color": "#40c4ff", "dash": "3 3"})
    if rbs is not None:
        levels.append({"price": rbs, "label": "RBS(D1/H4)", "color": "#ff4081", "dash": "3 3"})
    if sub_c is not None:
        levels.append({"price": sub_c, "label": "Sub C", "color": "#90a4ae", "dash": "2 5"})
    if sub_f is not None:
        levels.append({"price": sub_f, "label": "Sub F", "color": "#90a4ae", "dash": "2 5"})
    return levels


def render_pair_card(valid_sym, macro, zce_map, bars, digits, gen_time):
    price = pick(macro, "current_price", "last_price", "price")
    perm = pick(macro, "permission_state", "permission_v3", "permission")
    action = pick(macro, "action_tier", "mse_action_tier")
    if perm is None and action:
        perm = TIER2PERM.get(str(action).upper(), "WATCH")

    tier_label = TIER2LABEL.get(str(action).upper(), str(action or "—"))
    perm_color = PERM_COLOR.get(str(perm).upper(), "#9e9e9e")
    bias = pick(macro, "macro_bias_score", "bias_score")
    csm = pick(macro, "csm_delta", "csm_delta_val", "net_delta")
    atr = pick(macro, "current_atr", "atr", "atr_h1")
    atr_pts = pick(macro, "atr_pts", "atr_points")
    trend_d1 = pick(macro, "trend_label", "d1_trend", "daily_trend")
    trend_h4 = pick(macro, "h4_trend", "trend_h4")
    directive = pick(macro, "primary_execution_directive", "directive")
    traps = pick(macro, "forbidden_traps", "hard_traps")
    regime = pick(macro, "wave_regime_name", "regime", "wave_state")
    dr_pos = pick(macro, "dealing_range_pos", "dr_pos", "range_pos")
    h4_pos = pick(macro, "h4_dr_pos", "h4_range_pos")
    spread = pick(macro, "spread", "spread_pts")

    # attribusi ZCE
    zce_cls = "MSE_BASE"
    f1_src = zce_source_of(macro, zce_map, "f1") if zce_map is not None else "MSE"
    c1_src = zce_source_of(macro, zce_map, "c1") if zce_map is not None else "MSE"
    if f1_src == "ZCE" and c1_src == "ZCE":
        zce_cls = "ZCE_FULL"
    elif f1_src == "ZCE" or c1_src == "ZCE":
        zce_cls = "ZCE_MIXED"

    # info ZCE map
    zm_readiness = getattr(zce_map, "readiness_score", None) if zce_map else None
    zm_method = getattr(zce_map, "suggested_method", None) if zce_map else None
    zm_reason = getattr(zce_map, "method_reason", None) if zce_map else None
    zm_nf = len(getattr(zce_map, "floors", []) or []) if zce_map else 0
    zm_nc = len(getattr(zce_map, "ceilings", []) or []) if zce_map else 0
    zm_ladder = getattr(zce_map, "scale_ladder", None) if zce_map else None
    if zm_ladder is None:
        zm_ladder = getattr(zce_map, "ladder", None) if zce_map else None
    zm_atr = getattr(zce_map, "atr_h1", None) if zce_map else None

    def kv(k, v, unit=""):
        return f"<tr><td>{k}</td><td class='v'>{v}{unit}</td></tr>"

    perm_badge = f"<span class='badge' style='color:{perm_color};border-color:{perm_color}'>{perm}</span>"

    def pct(v):
        if v is None:
            return "—"
        try:
            return f"{float(v) * 100:.1f}%"
        except Exception:
            return str(v)

    rows_state = "".join([
        kv("Permission State", perm_badge),
        kv("Action Tier (MSE)", str(action or "—")),
        kv("Macro Bias Score", "—" if bias is None else f"{float(bias):+.2f}"),
        kv("CSM Delta", "—" if csm is None else f"{float(csm):+.1f}"),
        kv("Trend D1 / H4", f"{trend_d1 or '—'} / {trend_h4 or '—'}"),
        kv("Direktif Eksekusi", str(directive or "—")),
        kv("Wave Regime", str(regime or "—")),
        kv("Harga Live", "—" if price is None else fmt_price(price, digits), f" ({digits}-digit)"),
        kv("ATR H1", "—" if atr is None else fmt_price(atr, digits), "" if atr_pts is None else f"  ({atr_pts} pts)"),
        kv("Spread", "—" if spread is None else str(spread), " pts"),
        kv("Dealing Range Pos", "—" if dr_pos is None else pct(dr_pos)),
        kv("H4 DR Pos", "—" if h4_pos is None else pct(h4_pos)),
        kv("Forbidden Traps", str(traps or "—")),
    ])

    rows_zce = "".join([
        kv("Klasifikasi", f"<b style='color:#ffd740'>{zce_cls}</b> (F1:{f1_src} / C1:{c1_src})"),
        kv("Floors / Ceilings ZCE", f"{zm_nf} / {zm_nc}"),
        kv("Readiness Score", "—" if zm_readiness is None else f"{zm_readiness}"),
        kv("Suggested Method", str(zm_method or "—")),
        kv("Method Reason", str(zm_reason or "—")[:160] or "—"),
        kv("Scale Ladder", str(zm_ladder or "—")[:120] or "—"),
        kv("ATR (dari map)", "—" if zm_atr is None else fmt_price(zm_atr, digits)),
    ])

    levels = collect_levels(macro, digits, zce_map)
    chart = build_svg_chart(bars, levels, digits)

    # versi JSON mentah (untuk audit) — objek engine di-sanitasi
    raw_macro = to_jsonable(macro)
    raw_zce = to_jsonable(zce_map) if zce_map is not None else {}
    raw_json = json.dumps(
        {"macro_context": raw_macro, "zce_map": raw_zce},
        indent=1, default=str,
    )

    verdict = ""
    if perm == "GO":
        verdict = "<div class='verdict go'>➤ Engine di posisi ini akan mengizinkan eksekusi (Stage-1 <b>GO</b>).</div>"
    elif perm == "ARM":
        verdict = "<div class='verdict arm'>➤ Engine <b>ARMED</b>: setup valid tapi butuh konfirmasi reclaim/trigger sebelum GO.</div>"
    elif perm == "WATCH":
        verdict = "<div class='verdict watch'>➤ Engine <b>WATCH ONLY</b>: di reload zone, 0 order sampai trigger terkonfirmasi.</div>"
    elif perm == "LOCK":
        verdict = "<div class='verdict lock'>➤ Engine <b>HARD BLOCK</b>: tabrak hard trap / invalidasi makro (0 token LLM).</div>"

    return f"""
<details class="pair" open>
  <summary>
    <span class="sym">{valid_sym}</span>
    <span class="price">{fmt_price(price, digits)}</span>
    {perm_badge}
    <span class="cls">{zce_cls}</span>
    <span class="meta">F1 <i style="color:#00e676">{f1_src}</i> · C1 <i style="color:#ff5252">{c1_src}</i> · bias {("—" if bias is None else f"{float(bias):+.2f}")} · CSM {("—" if csm is None else f"{float(csm):+.1f}")}</span>
  </summary>
  {verdict}
  <div class="grid">
    <div class="chart-box">{chart}
      <div class="legend">
        <span><i style="background:#00e676"></i>F1 support</span>
        <span><i style="background:#ff5252"></i>C1 resist</span>
        <span><i style="background:#ffb300"></i>Dealing Range</span>
        <span><i style="background:#b39ddb"></i>PWH/PWL</span>
        <span><i style="background:#40c4ff"></i>SBR</span>
        <span><i style="background:#ff4081"></i>RBS</span>
        <span><i style="background:#9e9e9e"></i>Sub/Deep</span>
      </div>
    </div>
    <div class="tables">
      <div class="card"><h4>STATE ENGINE (macro_cache)</h4><table>{rows_state}</table></div>
      <div class="card"><h4>ZONE CONFLUENCE ENGINE</h4><table>{rows_zce}</table></div>
    </div>
  </div>
  <details class="raw">
    <summary>Raw JSON (audit)</summary>
    <pre>{raw_json}</pre>
  </details>
</details>
"""


def main():
    ap = argparse.ArgumentParser(description="Generate engine-eye HTML snapshot")
    ap.add_argument("--pairs", default=",".join(DEFAULT_PAIRS),
                    help="Daftar pair dipisah koma (default: EURUSD,GBPUSD,USDJPY,AUDUSD,EURJPY,GBPJPY)")
    ap.add_argument("--out", default=str(ROOT / "docs" / "engine_eye.html"))
    ap.add_argument("--bars", type=int, default=110, help="Jumlah candle H1 di chart (default 110)")
    args = ap.parse_args()

    requested = [p.strip().upper() for p in args.pairs.split(",") if p.strip()]
    out_path = Path(args.out)

    print(f"[engine_eye] Menghubungkan MT5 terminal...")
    if not connector.initialize_mt5():
        print("[engine_eye] GAGAL konek MT5. Pastikan terminal aktif & .env benar.")
        sys.exit(1)

    try:
        # resolve ke simbol valid broker
        valid_syms = []
        for s in requested:
            try:
                vs = connector.get_valid_trade_symbol(s)
            except Exception:
                vs = s
            valid_syms.append(vs)
            print(f"  - {s} → {vs}")

        # instance scanner SAMA seperti produksi, hanya subset simbol
        scanner = MarketScanner(symbols=valid_syms)

        # 1) isi peta ZCE (rotasi), sampai semua simbol subset ter-cover
        for _ in range(3):
            scanner._refresh_zce_rotation(mt5_connector=connector)
            missing = [v for v in valid_syms if v not in getattr(scanner, "_zce_maps", {})]
            if not missing:
                break

        # 2) bangun macro context (state engine penuh)
        scanner.update_macro_context(connector, force=True)

        gen_time = datetime.now(WIB).strftime("%d %b %Y %H:%M:%S WIB")
        cards = []
        ok = 0
        for vs in valid_syms:
            macro = (scanner.macro_cache or {}).get(vs) or {}
            zce_map = (getattr(scanner, "_zce_maps", {}) or {}).get(vs)
            if not macro:
                print(f"  ! {vs}: macro_context kosong (skip)")
                continue

            # digits utk format harga
            digits = macro.get("digits")
            if digits is None:
                try:
                    digits = config.mt5.symbol_info(vs).digits
                except Exception:
                    digits = 5
            digits = int(digits or 5)

            # candle H1 untuk chart
            bars = []
            try:
                rates = config.mt5.copy_rates_from_pos(vs, config.mt5.TIMEFRAME_H1, 0, args.bars)
                if rates is not None and len(rates):
                    bars = [{"time": int(r["time"]), "open": float(r["open"]),
                             "high": float(r["high"]), "low": float(r["low"]),
                             "close": float(r["close"])} for r in rates]
            except Exception as e:
                print(f"  ! {vs}: candle gagal ({e})")

            cards.append(render_pair_card(vs, macro, zce_map, bars, digits, gen_time))
            ok += 1
            print(f"  ✓ {vs} state engine siap")

        if not ok:
            print("[engine_eye] Tidak ada simbol yang berhasil. Cek koneksi/feed MT5.")
            sys.exit(2)

        html = HTML_TEMPLATE.replace("@@CARDS@@", "\n".join(cards)).replace("@@GEN@@", gen_time)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
        print(f"\n[engine_eye] OK — {ok} pair → {out_path}")
        print("           Buka file tsb di browser. Jalankan ulang kapan saja utk refresh.")
    finally:
        try:
            config.mt5.shutdown()
        except Exception:
            pass


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Engine Eye — X-Ray State Engine</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin:0; background:#0b0e14; color:#d8dee9; font-family:Consolas,'Courier New',monospace; }
  header { padding:14px 20px; border-bottom:1px solid #1f2630; background:#0d1117; position:sticky; top:0; z-index:5; }
  header h1 { margin:0; font-size:16px; letter-spacing:1px; }
  header .sub { font-size:11px; color:#6b7684; margin-top:4px; }
  main { padding:14px 20px; max-width:1280px; margin:0 auto; }
  details.pair { border:1px solid #1f2630; border-radius:8px; margin-bottom:14px; background:#0d1117; overflow:hidden; }
  details.pair > summary { display:flex; flex-wrap:wrap; gap:10px; align-items:center; padding:10px 14px;
      cursor:pointer; background:#11161d; list-style:none; }
  details.pair > summary::-webkit-details-marker { display:none; }
  .sym { font-size:15px; font-weight:bold; color:#e6edf3; min-width:130px; }
  .price { font-size:15px; color:#ffd740; }
  .badge { border:1px solid; border-radius:4px; padding:1px 8px; font-size:12px; font-weight:bold; }
  .cls { font-size:11px; background:#1c2333; color:#ffd740; padding:2px 7px; border-radius:4px; }
  .meta { font-size:11px; color:#8b949e; }
  .verdict { padding:8px 14px; font-size:12px; border-top:1px solid #1f2630; }
  .verdict.go { color:#00e676; background:#0b1f16; }
  .verdict.arm { color:#ffd740; background:#1f1a0b; }
  .verdict.watch { color:#40c4ff; background:#0b1a22; }
  .verdict.lock { color:#ff5252; background:#220b0b; }
  .grid { display:grid; grid-template-columns: 1fr 360px; gap:12px; padding:12px 14px; }
  @media (max-width:980px){ .grid{ grid-template-columns:1fr; } }
  .card { border:1px solid #1f2630; border-radius:6px; padding:8px 10px; margin-bottom:10px; background:#0b0e14; }
  .card h4 { margin:2px 0 8px; font-size:11px; color:#58a6ff; letter-spacing:0.5px; }
  table { width:100%; border-collapse:collapse; font-size:11.5px; }
  td { padding:3px 6px; border-bottom:1px solid #161b22; vertical-align:top; }
  td.v { text-align:right; color:#e6edf3; word-break:break-word; }
  tr:last-child td { border-bottom:none; }
  .legend { display:flex; flex-wrap:wrap; gap:12px; font-size:10.5px; color:#8b949e; margin-top:6px; }
  .legend span i { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:4px; }
  .muted { color:#6b7684; font-size:12px; padding:8px; }
  details.raw { border-top:1px solid #1f2630; }
  details.raw summary { padding:6px 14px; font-size:11px; color:#6b7684; cursor:pointer; }
  pre { margin:0; padding:10px 14px; font-size:10px; background:#080a0f; color:#9aa4b2; overflow:auto; max-height:340px; }
</style>
</head>
<body>
<header>
  <h1>👁 ENGINE EYE — X-Ray State Engine (ZCE FULL · MSE · Radar)</h1>
  <div class="sub">Snapshot @@GEN@@ · Read-only dari fungsi produksi MarketScanner/_refresh_zce_rotation/update_macro_context · Data: macro_cache + peta zona ZCE</div>
</header>
<main>
@@CARDS@@
</main>
</body>
</html>
"""

if __name__ == "__main__":
    main()
