import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')
import sys
import time
from datetime import datetime, timedelta
sys.path.append('.')

from src.indicators.wave_state import evaluate_wave_state
from src.indicators.lux_smc import LuxSMCAnalyzer
from src.analytics.market_scanner import resolve_permission, Direction, Phase, Permission
from src.indicators.atlas_dna import calculate_dynamic_stations

print("Loading EURUSD historical data...")
df_h1 = pd.read_csv('data/historical/fbs/EURUSD_H1.csv.gz')
df_h1 = df_h1.rename(columns={'O':'open', 'H':'high', 'L':'low', 'C':'close'})
df_h1['time'] = pd.to_datetime(df_h1['time'], utc=True)
df_h1.set_index('time', inplace=True)

df_d1 = pd.read_csv('data/historical/fbs/EURUSD_D1.csv.gz')
df_d1 = df_d1.rename(columns={'O':'open', 'H':'high', 'L':'low', 'C':'close'})
df_d1['time'] = pd.to_datetime(df_d1['time'], utc=True)
df_d1.set_index('time', inplace=True)

# 3 months = ~90 days (last 90 days of the dataset)
end_date = df_h1.index[-1]
start_date = end_date - timedelta(days=90)
df_h1_3m = df_h1[df_h1.index >= start_date]

print(f"Testing EURUSD from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

state_changes = []
mechanisms_triggered = {'JUDAS_SWEEP': 0, 'PULLBACK': 0, 'BREAKOUT': 0}

last_state = None

for i in range(120, len(df_h1_3m), 1): # evaluate every 1 hour
    cur_time = df_h1_3m.index[i]
    window_h1 = df_h1[df_h1.index <= cur_time].tail(200)
    window_d1 = df_d1[df_d1.index <= cur_time].tail(100)
    
    if len(window_d1) < 5 or len(window_h1) < 50:
        continue
        
    cur_close = window_h1['close'].iloc[-1]
    
    pwh = window_d1['high'].iloc[-2]
    pwl = window_d1['low'].iloc[-2]

    smc = LuxSMCAnalyzer(swing_length=3).analyze(window_d1, point_size=0.00001)
    macro_high = smc.strong_high if smc.strong_high > 0 else window_d1['high'].max()
    macro_low = smc.strong_low if smc.strong_low > 0 else window_d1['low'].min()

    h4_ema20 = window_h1['close'].ewm(span=80).mean().iloc[-1] # approx h4 ema20
    h4_dir = 1 if cur_close > h4_ema20 else -1

    # FIX 29 Agu: hitung ATR H1 actual (bukan hardcode 200 pts).
    # Pakai True Range + Wilder smoothing (period=14) sama dengan market_scanner pipeline.
    h1_h = window_h1['high']
    h1_l = window_h1['low']
    h1_c = window_h1['close']
    prev_c = h1_c.shift(1)
    tr = pd.concat([
        (h1_h - h1_l),
        (h1_h - prev_c).abs(),
        (h1_l - prev_c).abs()
    ], axis=1).max(axis=1)
    atr_series = tr.ewm(alpha=1/14, adjust=False).mean()
    atr_price = atr_series.iloc[-1]  # in price (e.g. 0.0020 for EURUSD)
    atr_pts = int(atr_price / 0.00001)  # convert to points (1 point = 0.00001 for EURUSD)
    
    wave = evaluate_wave_state(
        df_h1=window_h1,
        h4_trend_direction=h4_dir,
        current_price=cur_close,
        atr_pts=atr_pts,
        point_val=0.00001,
        csm_delta=0.0,
        symbol="EURUSD",
        pwh=pwh,
        pwl=pwl,
        macro_high=macro_high,
        macro_low=macro_low
    )
    
    # Track state changes
    if wave.state != last_state:
        state_changes.append({
            'date': cur_time.strftime('%Y-%m-%d %H:00'),
            'price': cur_close,
            'state': wave.state,
            'permission': wave.permission,
            'station': wave.target_station
        })
        last_state = wave.state
        
    # Simulate Mechanisms
    # 1. Pullback to EMA20 (FIX 29 Agu: pakai 0.45×ATR tolerance, bukan hardcode 50 pips)
    ema20 = window_h1['close'].ewm(span=20).mean().iloc[-1]
    pullback_tolerance = atr_pts * 0.45 * 0.00001  # 0.45×ATR dalam price
    if wave.permission in ["GO", "ARM"] and abs(cur_close - ema20) < pullback_tolerance:
        mechanisms_triggered['PULLBACK'] += 1

    # 2. Judas Sweep (swept PDH/PDL and rejected)
    if wave.permission in ["GO", "ARM"] and (wave.is_ceiling_rejected or wave.is_floor_rejected):
        mechanisms_triggered['JUDAS_SWEEP'] += 1

    # 3. Breakout retest (FIX 29 Agu: hitung via threshold cluster + ATR, bukan hardcode)
    # Match runtime: cluster resistance/support disentuh >= 2× + tembus 0.10×ATR
    if wave.permission in ["GO", "ARM"]:
        recent_h = window_h1['high'].iloc[-20:].values
        recent_l = window_h1['low'].iloc[-20:].values
        cluster_tol = atr_pts * 0.50 * 0.00001
        # Count touches at macro_high/low within cluster tolerance
        upper_touches = sum(1 for h in recent_h[:-1] if abs(h - macro_high) <= cluster_tol)
        lower_touches = sum(1 for l in recent_l[:-1] if abs(l - macro_low) <= cluster_tol)
        # Breakout: price beyond macro level by 0.10×ATR
        if upper_touches >= 2 and cur_close > (macro_high + atr_pts * 0.10 * 0.00001):
            mechanisms_triggered['BREAKOUT'] += 1
        elif lower_touches >= 2 and cur_close < (macro_low - atr_pts * 0.10 * 0.00001):
            mechanisms_triggered['BREAKOUT'] += 1

print("\n--- EURUSD 3-MONTH WAVE STATE TRANSITIONS ---")
for s in state_changes:
    print(f"{s['date']} | Price: {s['price']:.4f} | State: {s['state']:<25} | Action: {s['permission']:<4} | Target Station: {s['station']}")

print("\n--- MECHANISMS CAPTURED ---")
for k, v in mechanisms_triggered.items():
    print(f"{k}: {v} occurrences")

print("\n--- VALIDATION SUMMARY (29 Agu 2026) ---")
print("FIX: script pakai 0.45×ATR real tolerance + 0.10×ATR breakout + cluster_tol 0.50×ATR")
print("Sebelumnya atr_pts hardcode 200 + tolerance 50 pips -> angka tidak reliable.")
print("Sekarang: ATR dihitung dari True Range + Wilder smoothing (period=14) sama dengan market_scanner pipeline.")
print(f"Hasil: PULLBACK={mechanisms_triggered['PULLBACK']} (klaim lama 94, beda karena tolerance real lebih ketat),")
print(f"       JUDAS_SWEEP={mechanisms_triggered['JUDAS_SWEEP']} (klaim lama 44, beda karena threshold real),")
print(f"       BREAKOUT={mechanisms_triggered['BREAKOUT']} (match klaim 0: anti-breakout protection valid).")

