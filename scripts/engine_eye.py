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
    """Candlestick H1 + SEMUA level (tier ZCE ber-band area), murni SVG string.

    Setiap level boleh membawa atribut opsional:
      band_low/band_high → area zona digambar sebagai rect transparan (di belakang candle)
      line_width/opacity → ketebalan & transparansi garis
      title               → tooltip
    Label box hanya digambar bila tidak bertabrakan vertikal dgn label lain.
    """
    if not bars:
        return "<div class='muted'>Data H1 tidak tersedia (MT5 belum feed).</div>"

    candle_lo = min(b["low"] for b in bars)
    candle_hi = max(b["high"] for b in bars)
    candle_span = max(candle_hi - candle_lo, 0.0005)

    # Batasi agar level tidak mengepengkan candle:
    # Hanya level yang berada di dalam / sangat dekat candle (maks pad 18%) yang boleh memperluas viewport
    max_pad = 0.18 * candle_span
    ext = [candle_lo, candle_hi]
    for lv in levels:
        v = lv.get("price")
        if v is not None:
            try:
                vf = float(v)
                if candle_lo - max_pad <= vf <= candle_hi + max_pad:
                    ext.append(vf)
            except Exception:
                pass
    lo, hi = min(ext), max(ext)
    pad = (hi - lo) * 0.04 or 0.0005
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
    # 1) band area zona (paling belakang) — lebar zona asli multi-TF
    for lv in levels:
        b_lo, b_hi = lv.get("band_low"), lv.get("band_high")
        if b_lo is None or b_hi is None:
            continue
        y1, y2 = y_of(float(b_lo)), y_of(float(b_hi))
        ya, yb = min(y1, y2), max(y1, y2)
        if yb - ya < 0.8:
            continue
        parts.append(
            f'<rect x="0" y="{ya:.1f}" width="{width}" height="{yb - ya:.1f}" '
            f'fill="{lv.get("band_color", lv.get("color", "#888888"))}" '
            f'opacity="{lv.get("band_alpha", 0.05)}"/>'
        )

    # 2) candle
    for i, b in enumerate(bars):
        x = i * cw + cw / 2
        o, c, h, l = b["open"], b["close"], b["high"], b["low"]
        color = up if c >= o else down
        yc, yo = y_of(c), y_of(o)
        parts.append(
            f'<line x1="{x:.1f}" y1="{y_of(h):.1f}" x2="{x:.1f}" y2="{y_of(l):.1f}" '
            f'stroke="{color}" stroke-width="1"/>'
        )
        y_top, h_body = min(yc, yo), abs(yc - yo) or 1.0
        parts.append(
            f'<rect x="{x - body_w / 2:.1f}" y="{y_top:.1f}" width="{body_w:.1f}" '
            f'height="{h_body:.1f}" fill="{color}" rx="0.5"/>'
        )

    # 3) garis + label level (di atas candle), anti-tabrakan label
    occupied = []  # rentang y label yg sudah dipakai
    for lv in levels:
        price = lv.get("price")
        if price is None:
            continue
        y = y_of(float(price))
        label = lv.get("label", "")
        color = lv.get("color", "#9e9e9e")
        dash = lv.get("dash", "")
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        line_w = lv.get("line_width", 1.1)
        opacity = lv.get("opacity", 0.9)
        tip = lv.get("title", "")
        if tip:
            parts.append(
                f'<line x1="0" y1="{y:.1f}" x2="{width}" y2="{y:.1f}" '
                f'stroke="{color}" stroke-width="{line_w}" opacity="{opacity}"{dash_attr}>'
                f'<title>{tip}</title></line>'
            )
        else:
            parts.append(
                f'<line x1="0" y1="{y:.1f}" x2="{width}" y2="{y:.1f}" '
                f'stroke="{color}" stroke-width="{line_w}" opacity="{opacity}"{dash_attr}/>'
            )
        # label: hanya bila ada ruang vertikal bebas
        free = all(abs(y - oy) >= 13 for oy in occupied)
        if label and free:
            occupied.append(y)
            txt = f"{label} {fmt_price(price, digits)}"
            box_w = len(txt) * 6.1 + 8
            parts.append(
                f'<rect x="{width - 8 - len(txt) * 6.1:.0f}" y="{y - 9:.1f}" width="{box_w:.0f}" '
                f'height="13" rx="2" fill="rgba(13,17,23,0.88)" stroke="{color}" stroke-width="0.6"/>'
            )
            parts.append(
                f'<text x="{width - 4}" y="{y + 2.5:.1f}" font-size="9" fill="{color}" '
                f'text-anchor="end" font-family="Consolas,monospace">{txt}</text>'
            )
        else:
            # penanda kecil di kanan utk level tanpa label (tak muat)
            parts.append(
                f'<circle cx="{width - 5}" cy="{y:.1f}" r="2" fill="{color}" opacity="0.8"/>'
            )

    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'preserveAspectRatio="xMidYMid meet" style="background:#0d1117;border-radius:6px">'
        + "".join(parts)
        + "</svg>"
    )


def collect_levels(macro: dict, digits: int, zce_map=None, bars=None):
    """Level yang digambar di chart — dinding aktual + SEMUA tier ZCE (F1..Fn/C1..Cm)
    lengkap dgn band area (lebar zona asli), konteks makro, dan level psikologis.

    Aturan anti-duplikat: F1/C1 hasil elekt ZCE == macro immediate (sama persis),
    sehingga tier ke-1 dilewati saat sudah diwakili garis macro ber-label sumber.
    """
    cur = pick(macro, "current_price", "last_price", "price")
    atr = pick(macro, "current_atr", "atr", "atr_h1")
    levels = []

    # Bounding rentang tampak: berbasis candle H1 aktual agar level di dalam
    # pandangan chart ter-render penuh tanpa merusak/mengepengkan skala lilin
    if bars and len(bars):
        c_lo = min(b["low"] for b in bars)
        c_hi = max(b["high"] for b in bars)
        atr_f = float(atr) if atr else 0.001
        v_lo = c_lo - 0.20 * atr_f
        v_hi = c_hi + 0.20 * atr_f
    elif cur is not None and atr is not None:
        atr_f = float(atr)
        cur_f = float(cur)
        v_lo = cur_f - 4.5 * atr_f
        v_hi = cur_f + 4.5 * atr_f
    else:
        v_lo, v_hi = None, None

    def near(p):
        """Tier yang relevan utk chart: masuk ke dalam rentang lilin tampak."""
        if p is None or v_lo is None or v_hi is None:
            return True
        try:
            return v_lo <= float(p) <= v_hi
        except Exception:
            return True

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
        bl, bh = _match_zce_band(zce_map, "ceilings", c1)
        levels.append({"price": c1, "label": f"C1 ▲ [{src}]", "color": "#ff5252",
                       "line_width": 1.6, "band_low": bl, "band_high": bh,
                       "band_color": "#ff5252", "band_alpha": 0.06,
                       "title": f"C1 aktif sumber {src}"})
    if f1 is not None:
        src = "ZCE" if zce_map is not None and zce_source_of(macro, zce_map, "f1") == "ZCE" else "MSE"
        bl, bh = _match_zce_band(zce_map, "floors", f1)
        levels.append({"price": f1, "label": f"F1 ▼ [{src}]", "color": "#00e676",
                       "line_width": 1.6, "band_low": bl, "band_high": bh,
                       "band_color": "#00e676", "band_alpha": 0.06,
                       "title": f"F1 aktif sumber {src}"})

    # ── SEMUA tier ZCE (F1..Fn & C1..Cm, anti-duplikat wall aktif) ──
    if zce_map is not None:
        for lyr in (getattr(zce_map, "floors", None) or []):
            price = lyr.get("price")
            if price is None or not near(price):
                continue
            if f1 is not None and abs(float(price) - float(f1)) < 1e-9:
                continue  # sudah digambar sbg wall aktif ber-band
            levels.append(zce_tier_level(lyr, "F", "#00e676"))
        for lyr in (getattr(zce_map, "ceilings", None) or []):
            price = lyr.get("price")
            if price is None or not near(price):
                continue
            if c1 is not None and abs(float(price) - float(c1)) < 1e-9:
                continue  # sudah digambar sbg wall aktif ber-band
            levels.append(zce_tier_level(lyr, "C", "#ff5252"))

    if c2 is not None and near(c2):
        levels.append({"price": c2, "label": "C2", "color": "#ff8a80", "dash": "5 4", "line_width": 1.2})
    if f2 is not None and near(f2):
        levels.append({"price": f2, "label": "F2", "color": "#69f0ae", "dash": "5 4", "line_width": 1.2})
    if drh is not None and near(drh):
        levels.append({"price": drh, "label": "DR High", "color": "#ffb300", "dash": "2 3"})
    if drl is not None and near(drl):
        levels.append({"price": drl, "label": "DR Low", "color": "#ffb300", "dash": "2 3"})
    if pwh is not None and near(pwh):
        levels.append({"price": pwh, "label": "PWH", "color": "#b39ddb", "dash": "8 3"})
    if pwl is not None and near(pwl):
        levels.append({"price": pwl, "label": "PWL", "color": "#b39ddb", "dash": "8 3"})
    if sbr is not None and near(sbr):
        levels.append({"price": sbr, "label": "SBR(D1/H4)", "color": "#40c4ff", "dash": "3 3"})
    if rbs is not None and near(rbs):
        levels.append({"price": rbs, "label": "RBS(D1/H4)", "color": "#ff4081", "dash": "3 3"})
    if sub_c is not None and near(sub_c):
        levels.append({"price": sub_c, "label": "Sub C", "color": "#90a4ae", "dash": "2 5"})
    if sub_f is not None and near(sub_f):
        levels.append({"price": sub_f, "label": "Sub F", "color": "#90a4ae", "dash": "2 5"})
    return levels


def _match_zce_band(zce_map, kind: str, price):
    """Cari band_low/band_high layer ZCE yg harganya == wall aktif (utk area wall)."""
    try:
        if zce_map is None or price is None:
            return None, None
        layers = getattr(zce_map, kind, None) or []
        for lyr in layers:
            if abs(float(lyr.get("price") or 0) - float(price)) < 1e-9:
                return lyr.get("band_low"), lyr.get("band_high")
    except Exception:
        pass
    return None, None


def zce_tier_level(lyr: dict, prefix: str, color: str):
    """Konversi satu layer dict ZCE (F2..Fn/C2..Cm) → level chart ber-band area."""
    grade = lyr.get("grade", "GRADE_1_MICRO")
    g = {"GRADE_3_MACRO": 3, "GRADE_2_INTERMEDIATE": 2}.get(grade, 1)
    # tebal/alpha garis + alpha band mengikuti grade (G3 terkuat)
    line_w = {3: 1.6, 2: 1.3, 1: 1.0}[g]
    opacity = {3: 1.0, 2: 0.85, 1: 0.65}[g]
    band_alpha = {3: 0.14, 2: 0.09, 1: 0.055}[g]
    dash = {3: "", 2: "2 2", 1: "1 3"}[g]
    score = lyr.get("density_score")
    tag = lyr.get("tag") or ""
    tier = lyr.get("tier") or f"{prefix}{lyr.get('index', '')}"
    glyph = "▲" if tier.startswith("C") else "▼"
    sc_txt = "" if score is None else f" ·{score:.1f}"
    g_txt = {"GRADE_3_MACRO": "G3", "GRADE_2_INTERMEDIATE": "G2"}.get(grade, "G1")
    title = f"{tier} grade={grade} score={score} tag={tag}"
    if lyr.get("is_cold"):
        title += " [COLD]"
    if lyr.get("is_vacuum"):
        title += " [VACUUM]"
    tip = f"{lyr.get('band_low')}–{lyr.get('band_high')} · {title}"
    lv = {
        "price": lyr.get("price"), "label": f"{tier}{glyph}{g_txt}{sc_txt}",
        "color": color, "line_width": line_w, "opacity": opacity,
        "dash": dash, "band_low": lyr.get("band_low"), "band_high": lyr.get("band_high"),
        "band_color": color, "band_alpha": band_alpha, "title": tip,
    }
    return lv


def zone_ladder_svg(zce_map, digits=5, bars=None, width=940, height=430):
    """LADDER ZONA — sumbu Y = harga; setiap KLASTER multi-TF digambar sebagai
    batang transparan selebar rentang zona aslinya + LINE CHART pergerakan harga H1.
    Panjang pita solid kiri ∝ score_final. Tumpukan zona terlihat menebal → skor.
    """
    if zce_map is None:
        return "<div class='muted'>Peta ZCE kosong untuk pair ini.</div>"
    clusters = [c for c in (getattr(zce_map, "clusters", None) or [])]
    cur = getattr(zce_map, "cur_price", None)
    atr = getattr(zce_map, "atr_h1", None)
    if not clusters:
        return "<div class='muted'>Tidak ada klaster zona terdeteksi.</div>"

    # Seleksi klaster taktis seimbang di atas dan di bawah harga live
    # Mengeliminasi outlier multi-tahun (>16 ATR) agar tidak mengecilkan skala ladder
    shown = clusters
    if cur is not None and atr:
        try:
            cur_f, atr_f = float(cur), float(atr)
            tactical = [c for c in clusters if abs(c.mid - cur_f) <= 16.0 * atr_f]

            above = sorted([c for c in tactical if c.mid > cur_f], key=lambda c: c.mid - cur_f)
            below = sorted([c for c in tactical if c.mid < cur_f], key=lambda c: cur_f - c.mid)
            spanning = [c for c in tactical if c.band_low <= cur_f <= c.band_high]

            selected_ids = {c.cluster_id for c in spanning}
            picked = list(spanning)
            for c in above[:6]:
                if c.cluster_id not in selected_ids:
                    picked.append(c)
                    selected_ids.add(c.cluster_id)
            for c in below[:6]:
                if c.cluster_id not in selected_ids:
                    picked.append(c)
                    selected_ids.add(c.cluster_id)

            # Jika klaster taktis masih sedikit (< 4), ambil klaster terdekat
            if len(picked) < 4:
                for c in sorted(clusters, key=lambda c: abs(c.mid - cur_f))[:8]:
                    if c.cluster_id not in selected_ids and abs(c.mid - cur_f) <= 25.0 * atr_f:
                        picked.append(c)
                        selected_ids.add(c.cluster_id)

            if picked:
                shown = picked
        except Exception:
            shown = clusters

    lo = min(min(c.band_low, c.band_high) for c in shown)
    hi = max(max(c.band_low, c.band_high) for c in shown)
    if cur is not None:
        lo, hi = min(lo, float(cur)), max(hi, float(cur))
    span = (hi - lo) or 1e-9
    pad = span * 0.05
    lo -= pad
    hi += pad
    maxscore = max(c.score_final or 0 for c in shown) or 1.0

    def y_of(p):
        return 12 + (hi - float(p)) / (hi - lo) * (height - 40)

    def side_color(c):
        if cur is None:
            return "#ffd740"
        mid = (c.band_low + c.band_high) / 2.0
        if mid > float(cur) * 1.0000001:
            return "#ff5252"  # resistance (di atas harga)
        if mid < float(cur) * 0.9999999:
            return "#00e676"  # support (di bawah harga)
        return "#ffd740"

    parts = []
    X0 = 74  # sumbu skor dimulai di kanan label harga kiri
    bar_max = width - X0 - 220  # ruang tersisa utk pita skor + label
    # setiap klaster: area transparan penuh (lebar zona) + pita solid ∝ skor
    for c in sorted(shown, key=lambda c: c.band_low):
        y_hi = y_of(c.band_high)
        y_lo = y_of(c.band_low)
        y_top, y_bot = min(y_hi, y_lo), max(y_hi, y_lo)
        zone_h = max(y_bot - y_top, 2.0)
        color = side_color(c)
        score = c.score_final or 0.0
        rel = max(0.0, min(1.0, score / maxscore))
        alpha = 0.06 + 0.24 * rel
        score_w = max(bar_max * rel, 14.0)
        bar_h = max(zone_h * 0.70, 7.5)
        y_bar = (y_top + y_bot) / 2.0 - bar_h / 2.0

        # tooltip detail
        tfs = ",".join(c.tfs_present or [])
        kinds = ",".join((c.kinds_present or [])[:5])
        g_txt = {"GRADE_3_MACRO": "G3", "GRADE_2_INTERMEDIATE": "G2"}.get(c.grade, "G1")
        tip = (f"Klaster #{c.cluster_id} · skor {score:.2f} (raw {c.score_raw:.1f}) · {c.grade}"
               f" · TF: {tfs} · jenis: {kinds} · horizon max {c.horizon_max}"
               f" · lebar {c.width_atr:.2f} ATR" + (" · COLD" if c.is_cold else "")
               + (" · VACUUM" if c.is_vacuum else ""))

        # 1) Area zona transparan penuh (lebar zona asli)
        parts.append(
            f'<rect x="0" y="{y_top:.1f}" width="{width}" height="{zone_h:.1f}" '
            f'fill="{color}" opacity="{alpha * 0.45:.3f}"><title>{tip}</title></rect>'
        )
        # 2) Pita skor solid proporsional score_final
        parts.append(
            f'<rect x="{X0}" y="{y_bar:.1f}" width="{score_w:.1f}" '
            f'height="{bar_h:.1f}" fill="{color}" rx="2" opacity="{0.35 + 0.65 * rel:.2f}"/>'
        )
        # 3) Label skor & grade di samping pita
        lbl = f"{score:.1f} · {g_txt} [{c.fortress_tag}]"
        parts.append(
            f'<text x="{X0 + score_w + 6:.1f}" y="{y_bar + bar_h / 2.0 + 3.2:.1f}" font-size="9" '
            f'fill="{color}" text-anchor="start" font-family="Consolas,monospace">'
            f'{lbl}</text>'
        )
        # 4) Label rentang harga band di tepi kanan
        band_str = f"{fmt_price(c.band_low, digits)}–{fmt_price(c.band_high, digits)}"
        parts.append(
            f'<text x="{width - 10}" y="{y_bar + bar_h / 2.0 + 3.2:.1f}" font-size="8.5" '
            f'fill="#8b949e" text-anchor="end" font-family="Consolas,monospace">'
            f'{band_str}</text>'
        )

    # 3) Line Chart pergerakan harga H1 melintasi tangga zona ZCE
    if bars and len(bars) >= 2:
        n_b = len(bars)
        x_start = X0 + 6
        x_end = width - 110
        x_span = max(x_end - x_start, 50)
        pts = []
        for i, b in enumerate(bars):
            xi = x_start + (i / max(n_b - 1, 1)) * x_span
            cp = float(b["close"])
            yi = max(10.0, min(float(height - 15), y_of(cp)))
            pts.append((xi, yi))

        path_d = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        # Glow lembut di belakang
        parts.append(
            f'<path d="{path_d}" fill="none" stroke="#64b5f6" stroke-width="2.8" '
            f'opacity="0.22" stroke-linejoin="round"/>'
        )
        # Garis utama linechart
        parts.append(
            f'<path d="{path_d}" fill="none" stroke="#64b5f6" stroke-width="1.4" '
            f'opacity="0.85" stroke-linejoin="round"/>'
        )
        # Titik dot harga live terakhir
        lx, ly = pts[-1]
        parts.append(
            f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.2" fill="#ffffff" '
            f'stroke="#64b5f6" stroke-width="1.6"/>'
        )

    # garis harga live
    if cur is not None:
        yc = y_of(float(cur))
        parts.append(
            f'<line x1="0" y1="{yc:.1f}" x2="{width}" y2="{yc:.1f}" '
            f'stroke="#e6edf3" stroke-width="1.1" stroke-dasharray="6 3" opacity="0.9"/>'
        )
        parts.append(
            f'<text x="{width - 60}" y="{yc - 4:.1f}" font-size="10" fill="#ffffff" '
            f'text-anchor="end" font-family="Consolas,monospace">◄ {fmt_price(cur, digits)}</text>'
        )
    # skala harga kiri (4 tick)
    for i in range(5):
        p = hi - (hi - lo) * (i / 4)
        y = y_of(p)
        parts.append(
            f'<text x="8" y="{y + 3:.1f}" font-size="9" fill="#6b7684" '
            f'text-anchor="start" font-family="Consolas,monospace">{fmt_price(p, digits)}</text>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'preserveAspectRatio="xMidYMid meet" style="background:#0d1117;border-radius:6px;margin-top:8px">'
        + "".join(parts)
        + "</svg>"
    )


def zone_stack_table(zce_map, digits=5):
    """Tabel detail SEMUA klaster ZCE: band harga, skor, grade, TF & jenis penyusun,
    horizon, cold/vacuum, lebar ATR — bukti 'banyak level bertumpuk jadi skor'."""
    if zce_map is None:
        return "<div class='muted'>Peta ZCE kosong.</div>"
    clusters = sorted(
        [c for c in (getattr(zce_map, "clusters", None) or [])],
        key=lambda c: -(c.score_final or 0.0),
    )
    if not clusters:
        return "<div class='muted'>Tidak ada klaster zona.</div>"
    rows = []
    for c in clusters:
        g = {"GRADE_3_MACRO": "#ff5252", "GRADE_2_INTERMEDIATE": "#ffb300"}.get(
            c.grade, "#40c4ff")
        g_txt = {"GRADE_3_MACRO": "G3", "GRADE_2_INTERMEDIATE": "G2"}.get(c.grade, "G1")
        flag = ""
        if c.is_cold:
            flag += " ❄COLD"
        if c.is_vacuum:
            flag += " 🕳VAC"
        if c.touch_count:
            flag += f" ×{c.touch_count}sentuh"
        tfs = "".join(f"<span class='chip'>{t}</span>" for t in (c.tfs_present or []))
        kinds = "".join(f"<span class='chip k'>{k}</span>" for k in (c.kinds_present or [])[:5])
        members = getattr(c, "members", None) or []
        m_txt = ""
        if members:
            seen = {}
            for m in members[:40]:
                key = (m.kind, m.tf, m.horizon)
                seen[key] = seen.get(key, 0) + 1
            m_txt = "<br><span class='muted'>" + ", ".join(
                f"{k}@{tf}" + (f"[h{h}]" if h else "[psych]") + (f"×{n}" if n > 1 else "")
                for (k, tf, h), n in list(seen.items())[:10]
            ) + "</span>"
        rows.append(
            f"<tr>"
            f"<td class='v'>{fmt_price(c.band_low, digits)}<br><span class='muted'>s/d</span><br>{fmt_price(c.band_high, digits)}</td>"
            f"<td class='v'><b style='color:{g}'>{c.score_final:.2f}</b><br><span class='muted'>raw {c.score_raw:.1f}</span></td>"
            f"<td><span class='gchip' style='color:{g};border-color:{g}'>{g_txt}</span></td>"
            f"<td>{tfs}</td>"
            f"<td>{kinds}</td>"
            f"<td class='v'>{c.horizon_max or '—'}</td>"
            f"<td class='v'>{c.width_atr:.2f}</td>"
            f"<td class='v'>{flag or '—'}</td>"
            f"<td class='v'>{c.cluster_id}</td>"
            f"</tr>"
            f"<tr class='msub'><td colspan='9'>{m_txt}</td></tr>"
        )
    head = (
        "<tr><th>Band zona (harga)</th><th>Skor J1</th><th>Grade</th><th>TF penyusun</th>"
        "<th>Jenis</th><th>Horizon</th><th>Lebar (ATR)</th><th>Status</th><th>ID</th></tr>"
    )
    return (
        "<div class='ztbl-wrap'><table class='ztbl'>" + head + "".join(rows) + "</table></div>"
    )


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
    # label trend D1/H4/W1 terpisah (macro_cache: d1_trend_label, h4_trend_label,
    # w1_trend_label, trend_label = "D1 | H4" gabungan) — fallback parse manual
    trend_d1 = pick(macro, "d1_trend_label", "d1_trend", "daily_trend")
    trend_h4 = pick(macro, "h4_trend_label", "h4_trend", "trend_h4")
    trend_w1 = pick(macro, "w1_trend_label", "w1_trend", "weekly_trend")
    trend_combo = pick(macro, "trend_label", "")
    if trend_combo and "|" in str(trend_combo):
        left, right = str(trend_combo).split("|", 1)
        trend_d1 = trend_d1 or left.strip()
        trend_h4 = trend_h4 or right.strip()
    directive = pick(macro, "primary_execution_directive", "directive")
    traps = None
    try:
        sd = macro.get("strat_dir")
        if sd is not None and getattr(sd, "forbidden_traps", None):
            traps = sd.forbidden_traps
    except Exception:
        traps = None
    if not traps:
        traps = pick(macro, "forbidden_traps", "hard_traps")
    regime = pick(macro, "wave_regime_name", "regime", "wave_state")
    dr_pos = pick(macro, "dealing_range_pos", "dr_pos", "range_pos")
    h4_pos = pick(macro, "h4_dr_pos", "h4_range_pos")
    mse_state = pick(macro, "wave_state", "mse_state", "market_state")
    struct_stage = pick(macro, "structural_stage", "structure_stage")
    loc = pick(macro, "macro_corridor", "corridor", "location")
    spread = None
    try:
        t_info = config.mt5.symbol_info_tick(valid_sym)
        if t_info is not None and getattr(t_info, "spread", None) is not None:
            spread = int(round(float(getattr(t_info, "spread"))))
    except Exception:
        spread = None
    if spread is None:
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

    def _trend_html(v):
        if v is None:
            return "—"
        s = str(v)
        if "BEARISH" in s or "BEAR" in s.split("|")[0] or "SELL" in s.upper():
            c = "#ff5252"
        elif "BULLISH" in s or "BULL" in s.split("|")[0] or "BUY" in s.upper():
            c = "#00e676"
        elif "RANGE" in s or "SIDEWAYS" in s:
            c = "#ffb300"
        else:
            c = "#8b949e"
        return f"<span style='color:{c}'>{s}</span>"

    rows_state = "".join([
        kv("Permission State", perm_badge),
        kv("Action Tier (MSE)", str(action or "—")),
        kv("Macro Bias Score", "—" if bias is None else f"{float(bias):+.2f}"),
        kv("CSM Delta", "—" if csm is None else f"{float(csm):+.1f}"),
        kv("Trend D1", _trend_html(trend_d1)),
        kv("Trend H4", _trend_html(trend_h4)),
        kv("Trend W1", _trend_html(trend_w1)),
        kv("Wave State (MSE)", str(mse_state or "—")),
        kv("Structural Stage", str(struct_stage or "—")),
        kv("Macro Corridor", str(loc or "—")),
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
        kv("Wall / Deep ZCE", f"F1–F{zm_nf} ({zm_nf} lantai) · C1–C{zm_nc} ({zm_nc} atap)"),
        kv("Readiness Score", "—" if zm_readiness is None else f"{zm_readiness}"),
        kv("Suggested Method", str(zm_method or "—")),
        kv("Method Reason", str(zm_reason or "—")[:160] or "—"),
        kv("Scale Ladder", str(zm_ladder or "—")[:120] or "—"),
        kv("ATR (dari map)", "—" if zm_atr is None else fmt_price(zm_atr, digits)),
    ])

    levels = collect_levels(macro, digits, zce_map, bars=bars)
    chart = build_svg_chart(bars, levels, digits)

    # Ladder multi-TF (semua klaster zona bertumpuk → skor + linechart H1)
    ladder = zone_ladder_svg(zce_map, digits, bars=bars)
    ztable = zone_stack_table(zce_map, digits)
    n_clusters = len(getattr(zce_map, "clusters", None) or []) if zce_map else 0
    n_layers = (zm_nf or 0) + (zm_nc or 0)

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
        <span><i style="background:#00e676"></i>F1 support (ZCE/MSE)</span>
        <span><i style="background:#ff5252"></i>C1 resist (ZCE/MSE)</span>
        <span><i style="background:#69f0ae"></i>F2–Fn lantai ZCE</span>
        <span><i style="background:#ff8a80"></i>C2–Cm atap ZCE</span>
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
  <div class="zone-block">
    <div class="zone-cap">🧱 <b>ZONE LADDER & PRICE ACTION</b> — {n_layers} lapisan F/C multi-TF bertumpuk · pita <span style="color:#00e676">hijau = support</span> / <span style="color:#ff5252">merah = resist</span> / <span style="color:#ffd740">emas = melintasi harga</span> · kurva <span style="color:#64b5f6">cyan = close H1</span> · panjang pita = skor J1</div>
    {ladder}
    <div class="zone-cap" style="margin-top:12px">📋 <b>ZONE STACK</b> — detail {n_clusters} klaster zona (skor = bobot tumpukan multi-TF/horizon) — klik judul utk expand</div>
    <details class="zstack">
      <summary>ZONE STACK — {n_clusters} klaster · {n_layers} lapisan wall</summary>
      {ztable}
    </details>
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
  .zone-block { padding:2px 14px 12px; }
  .zone-cap { font-size:11px; color:#8b949e; padding:6px 2px 4px; }
  details.zstack { border:1px solid #1f2630; border-radius:6px; background:#0b0e14; margin-top:4px; }
  details.zstack summary { padding:6px 10px; font-size:11px; color:#58a6ff; cursor:pointer; }
  .ztbl-wrap { overflow-x:auto; max-height:420px; overflow-y:auto; }
  table.ztbl { width:100%; border-collapse:collapse; font-size:10px; }
  .ztbl th { color:#6b7684; text-align:left; padding:4px 6px; border-bottom:1px solid #1f2630;
      position:sticky; top:0; background:#0d1117; }
  .ztbl td { padding:4px 6px; border-bottom:1px solid #161b22; vertical-align:top; }
  .ztbl tr.msub td { font-size:9.5px; color:#6b7684; background:#0a0d13; }
  .chip { display:inline-block; border:1px solid #2a3441; border-radius:3px; padding:0 4px; margin:1px 2px 1px 0;
      font-size:9px; color:#9aa4b2; background:#11161d; }
  .chip.k { color:#4dd0e1; border-color:#1e3a47; }
  .gchip { border:1px solid; border-radius:3px; padding:0 5px; font-size:9.5px; font-weight:bold; }
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
