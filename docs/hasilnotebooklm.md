# ?? High-Probability Quantitative Trading Strategies Matrix

Dokumen ini berisi kumpulan 10 strategi kuantitatif teruji yang diekstrak dari 11 buku panduan trading utama (*The Candlestick Trading Bible*, *Apex Paragon Atlas*, *Rayner Teo Guides*, *Teknik S&D*, *Edianto Ong*, dll.) untuk diintegrasikan ke dalam Python Rule Engine (scanner.py).

---

## ?? Bagian 1: 5 Strategi Utuh Pertama

| Strategy Name | Source Book | Core Pattern & Market Logic | Python Mathematical Condition (OHLC/Indicator) | Stop Loss (SL) & Take Profit (TP) Rules |
| :--- | :--- | :--- | :--- | :--- |
| **1. Supply & Demand (S&D) Zone Retest** | *Teknik S&D.pdf*, *Candlestick Trading Bible* | Ketidakseimbangan (imbalances) besar institusi menciptakan struktur RBD/DBR. Entri pada *first pullback retest* dari zona base. | **DBR Base Setup:**<br>is_drop = Close[i-2] < Open[i-2]<br>is_base = abs(Close[i-1] - Open[i-1]) < (0.3 * ATR[i-1])<br>is_rally = Close[i] > Open[i] + (Open[i-2] - Close[i-2]) * 0.5<br><br>**Boundaries:**<br>Demand_Proximal = max(Open[i-1], Close[i-1])<br>Demand_Distal = Low[i-1]<br>Supply_Proximal = min(Open[i-1], Close[i-1])<br>Supply_Distal = High[i-1]<br><br>**Trigger:** Low <= Demand_Proximal | **SL**: Demand_Distal - (1.0 * ATR)<br>**TP**: Zona Supply H1/M30 terdekat atau swing high sebelumnya. |
| **2. Break-Hook-Go (BHG)** | *Apex Paragon Atlas Booklet* | Level H4/D1 pecah (Break), harga pullback (Hook) ke Fib 38.2%-50%, ditutup dengan reversal candle (Go). | **Bullish Impulse:** Swing Low $ ke Swing High $.<br>Break: Close[i] > H<br>Hook: (Low <= Fib_382) & (Low >= Fib_500)<br>Go: Close > Open & Close > High[i-1] | **SL**: H - 0.886 * (H - L) (Fib 88.6%)<br>**TP**: H + 0.27 * (H - L) (Fib Extension -27%). |
| **3. Trend Trading Breakout (Buildup)** | *The Complete Guide to Breakout Trading* | Tren kuat (Close > EMA20 > EMA50), terjadi *buildup* (konsolidasi rapat < 1.5 ATR) di bawah Resistance. | **Uptrend:** Close > EMA20 > EMA50<br>**Buildup:** Buildup_Range = max(High[0:10]) - min(Low[0:10]) < 1.5 * ATR<br>**Overextended Filter:** bs(Close - EMA20) < 2.5 * ATR<br>**Strong Close Filter:** (High - Close) <= 0.2 * Range<br>**Trigger:** Close > max(High[1:11]) | **SL**: min(Low[0:10]) - 1.0 * ATR<br>**TP**: Trail posisi menggunakan 21 EMA (exit jika Close < EMA21). |
| **4. Moving Average & Bearish Engulfing Combo** | *Bearish Engulfing Strategy*, *Candlestick Bible* | Tren turun sehat (Close < EMA50), harga *pullback* menyentuh EMA50, lalu membentuk *Bearish Engulfing*. | **Downtrend:** Close < EMA50 & EMA50 < EMA50[i-10]<br>**Pullback:** High >= EMA50 * 0.998<br>**Engulfing:** Close[i-1] > Open[i-1] & Close[i] < Open[i] & Open[i] >= Close[i-1] & Close[i] <= Open[i-1] | **SL**: max(High[i], High[i-1]) + 0.5 * ATR<br>**TP**: Support horizontal terdekat atau R:R 1.5:1. |
| **5. Swing Liquidity False Breakout (Sweep)** | *The NO BS Guide to Swing Trading* | Harga menembus Support 40-bar untuk menyapu *stop loss* ritel (*liquidity sweep*), lalu berbalik *Close* di dalam range. | **Support:** S = min(Low[1:40])<br>**Sweep:** Low < S<br>**Reclaim:** Close > S & Close > Open | **SL**: Low - 1.0 * ATR<br>**TP**: max(High[1:40]) - 0.5 * ATR (Batas atas range). |

---

## ?? Bagian 2: 5 Hidden Trading Edges Tambahan

| Strategy Name | Source Book | Core Pattern & Market Logic | Python Mathematical Condition (OHLC/Indicator) | Stop Loss (SL) & Take Profit (TP) Rules |
| :--- | :--- | :--- | :--- | :--- |
| **6. Inside Bar False Breakout ( Fakey)** | *The Candlestick Trading Bible* | Konsolidasi *inside bar* di area penting. Market maker menyapu *low/high* inside bar lalu berbalik tutup di dalam range. | **Inside Bar:** High[i-1] < High[i-2] & Low[i-1] > Low[i-2]<br>**Bullish Fakey:** Low[i] < Low[i-1] & Close[i] > High[i-1] | **SL**: Low[i] - 0.5 * ATR<br>**TP**: Resistance terdekat atau R:R minimal 1.5:1. |
| **7. Trendline Price Gap Breakout (Kennedy Gap)** | *Trading the Trendline* (Jeffrey Kennedy) | Breakout Trendline yang disertai **Gap Up** (seluruh bar i berada di atas garis trendline). Menyaring 90% false breakout. | **Gap Up:** Open[i] > TL[i] & Low[i] > TL[i]<br>**Pending Trigger:** Buy Stop @ High[i] + 1 tick | **SL**: Low[i-1] - 1 tick<br>**TP**: Resistance horizontal terdekat / slope trendline. |
| **8. Dual Trendline Retest (Institutional Double Tap)** | *Trading the Trendline* (Jeffrey Kennedy) | Trendline pecah $\rightarrow$ *Retest 1* $\rightarrow$ *Interim High* $\rightarrow$ *Retest 2* $\rightarrow$ Breakout *Interim High*. | **TL Breakout:** Close > TL<br>**Retest 1 & 2:** Low[R1] <= TL & Low[R2] <= TL<br>**Interim High:** H_interim = max(Close[R1:i])<br>**Trigger:** Close[i] > H_interim | **SL**: Low[R2] - 0.5 * ATR<br>**TP**: Resistance utama atau Fib Extension -27%. |
| **9. Horn Bottoms / Horn Tops Reversal** | *Technical Analysis for Mega Profit* (Edianto Ong) | Reversal Double Bottom mini (< 10 bar) dengan jarak lembah , L2 < 0.25 \times ATR$ + Gap Up menembus *Interim High*. | **Parallel Bottoms:** bs(L1 - L2) < 0.25 * ATR<br>**Confirmation:** Open[i] > Close[i-1] & Close[i] > H_interim | **SL**: min(L1, L2) - 1.0 * ATR<br>**TP**: H_interim + (H_interim - min(L1, L2)). |
| **10. 21 EMA Dynamic Pullback + Fib + Pinbar** | *The Candlestick Trading Bible* | Tren naik (EMA21[i] > EMA21[i-5]) + *retest* EMA21 & Fib 50%-61.8% + candle **Bullish Pin Bar**. | **Trend:** EMA21[i] > EMA21[i-5]<br>**Touch:** Low[i] <= EMA21[i] & Close[i] > EMA21[i]<br>**Fib Confluence:** Low[i] >= Fib_618 & Low[i] <= Fib_500<br>**Pin Bar:** Lower_Tail > 2 * Body & Upper_Tail < 0.5 * Lower_Tail | **SL**: Low[i] - 0.5 * ATR<br>**TP**: Swing High sebelumnya / Trail 21 EMA. |

---

## ?? Implementasi Kode Python Vectorized (pandas/
umpy) untuk scanner.py

`python
import numpy as np
import pandas as pd

# =====================================================================
# 1. Supply & Demand Zone Retest
# =====================================================================
def scan_supply_demand_zones(df: pd.DataFrame) -> pd.DataFrame:
    df['is_drop'] = df['Close'].shift(2) < df['Open'].shift(2)
    df['is_base'] = np.abs(df['Close'].shift(1) - df['Open'].shift(1)) < (0.3 * df['ATR'].shift(1))
    df['is_rally'] = df['Close'] > (df['Open'] + (df['Open'].shift(2) - df['Close'].shift(2)) * 0.5)
    
    df['Zone_Demand_Inner'] = np.where(df['is_drop'] & df['is_base'] & df['is_rally'], 
                                       df[['Open', 'Close']].shift(1).max(axis=1), np.nan)
    df['Zone_Demand_Outer'] = np.where(df['is_drop'] & df['is_base'] & df['is_rally'], 
                                       df['Low'].shift(1), np.nan)
    
    df['Zone_Demand_Inner'] = df['Zone_Demand_Inner'].ffill()
    df['Zone_Demand_Outer'] = df['Zone_Demand_Outer'].ffill()
    
    df['Signal_Buy_SND'] = (df['Low'] <= df['Zone_Demand_Inner']) & (df['Low'] >= df['Zone_Demand_Outer'])
    return df

# =====================================================================
# 2. Break-Hook-Go (BHG)
# =====================================================================
def scan_break_hook_go(df: pd.DataFrame) -> pd.DataFrame:
    df['Swing_Low'] = df['Low'].rolling(window=30).min()
    df['Swing_High'] = df['High'].rolling(window=30).max()
    
    df['Impulse_Low'] = np.where(df['Close'] > df['Swing_High'].shift(1), df['Swing_Low'].shift(1), np.nan)
    df['Impulse_High'] = np.where(df['Close'] > df['Swing_High'].shift(1), df['Swing_High'].shift(1), np.nan)
    df['Impulse_Low'] = df['Impulse_Low'].ffill()
    df['Impulse_High'] = df['Impulse_High'].ffill()
    
    df['Fib_382'] = df['Impulse_High'] - 0.382 * (df['Impulse_High'] - df['Impulse_Low'])
    df['Fib_500'] = df['Impulse_High'] - 0.500 * (df['Impulse_High'] - df['Impulse_Low'])
    
    df['is_hook'] = (df['Low'] <= df['Fib_382']) & (df['Low'] >= df['Fib_500'])
    df['is_go'] = (df['Close'] > df['Open']) & (df['Close'] > df['High'].shift(1))
    
    df['Signal_Buy_BHG'] = df['is_hook'] & df['is_go']
    return df

# =====================================================================
# 3. Genuine Trend Trading Breakout (With Buildup & Filters)
# =====================================================================
def scan_trend_breakout(df: pd.DataFrame, window=10) -> pd.DataFrame:
    df['EMA20'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
    
    df['is_trending'] = (df['Close'] > df['EMA20']) & (df['EMA20'] > df['EMA50'])
    df['Buildup_High'] = df['High'].rolling(window=window).max()
    df['Buildup_Low'] = df['Low'].rolling(window=window).min()
    df['is_buildup'] = (df['Buildup_High'] - df['Buildup_Low']) < (1.5 * df['ATR'])
    df['is_not_overextended'] = np.abs(df['Close'] - df['EMA20']) < (2.5 * df['ATR'])
    
    df['Candle_Range'] = df['High'] - df['Low']
    df['is_strong_close'] = (df['High'] - df['Close']) <= (0.2 * df['Candle_Range'])
    
    df['Signal_Buy_Breakout'] = (
        df['is_trending'] & 
        df['is_buildup'] & 
        df['is_not_overextended'] & 
        df['is_strong_close'] & 
        (df['Close'] > df['Buildup_High'].shift(1))
    )
    return df

# =====================================================================
# 4. Moving Average & Bearish Engulfing Combo
# =====================================================================
def scan_ma_bearish_engulfing(df: pd.DataFrame) -> pd.DataFrame:
    df['EMA50'] = df['Close'].ewm(span=50, adjust=False).mean()
    df['is_downtrend'] = (df['Close'] < df['EMA50']) & (df['EMA50'] < df['EMA50'].shift(10))
    df['is_pullback'] = (df['High'] >= df['EMA50'] * 0.998) | (df['High'].shift(1) >= df['EMA50'].shift(1) * 0.998)
    
    df['is_engulfing'] = (
        (df['Close'].shift(1) > df['Open'].shift(1)) &
        (df['Close'] < df['Open']) &
        (df['Open'] >= df['Close'].shift(1)) &
        (df['Close'] < df['Open'].shift(1))
    )
    df['Signal_Sell_MA_Engulfing'] = df['is_downtrend'] & df['is_pullback'] & df['is_engulfing']
    return df

# =====================================================================
# 5. Swing Liquidity False Breakout (Sweep)
# =====================================================================
def scan_false_breakout(df: pd.DataFrame) -> pd.DataFrame:
    df['Support'] = df['Low'].rolling(window=40).min().shift(1)
    df['is_sweep'] = df['Low'] < df['Support']
    df['is_reclaim'] = df['Close'] > df['Support']
    df['is_bullish'] = df['Close'] > df['Open']
    
    df['Signal_Buy_Sweep'] = df['is_sweep'] & df['is_reclaim'] & df['is_bullish']
    return df

# =====================================================================
# 6. Inside Bar False Breakout (The Fakey)
# =====================================================================
def scan_inside_bar_false_breakout(df: pd.DataFrame) -> pd.DataFrame:
    df['is_inside_bar'] = (df['High'].shift(1) < df['High'].shift(2)) & (df['Low'].shift(1) > df['Low'].shift(2))
    df['Signal_Buy_Fakey'] = (
        df['is_inside_bar'] & 
        (df['Low'] < df['Low'].shift(1)) & 
        (df['Close'] > df['High'].shift(1))
    )
    return df

# =====================================================================
# 7. Trendline Price Gap Breakout (The Kennedy Gap)
# =====================================================================
def scan_trendline_gap_breakout(df: pd.DataFrame, trendline_series: pd.Series) -> pd.DataFrame:
    df['is_gap_up'] = (df['Open'] > trendline_series) & (df['Low'] > trendline_series)
    df['Signal_Buy_Gap'] = df['is_gap_up']
    return df

# =====================================================================
# 8. 21 EMA Dynamic Pullback & Fib Confluence Pinbar
# =====================================================================
def scan_ema_dynamic_pullback(df: pd.DataFrame) -> pd.DataFrame:
    df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()
    df['Local_Swing_Low'] = df['Low'].rolling(window=30).min()
    df['Local_Swing_High'] = df['High'].rolling(window=30).max()
    df['Fib_500'] = df['Local_Swing_High'] - 0.500 * (df['Local_Swing_High'] - df['Local_Swing_Low'])
    df['Fib_618'] = df['Local_Swing_High'] - 0.618 * (df['Local_Swing_High'] - df['Local_Swing_Low'])
    
    df['is_uptrend'] = df['EMA21'] > df['EMA21'].shift(5)
    df['ema_touch'] = (df['Low'] <= df['EMA21']) & (df['Close'] > df['EMA21'])
    df['fib_confluence'] = (df['Low'] >= df['Fib_618']) & (df['Low'] <= df['Fib_500'])
    
    df['Body'] = np.abs(df['Close'] - df['Open'])
    df['Lower_Tail'] = np.minimum(df['Open'], df['Close']) - df['Low']
    df['Upper_Tail'] = df['High'] - np.maximum(df['Open'], df['Close'])
    df['is_bullish_pin'] = (df['Lower_Tail'] >= 2.0 * df['Body']) & (df['Upper_Tail'] <= 0.2 * (df['High'] - df['Low']))
    
    df['Signal_Buy_EMA21_Pinbar'] = df['is_uptrend'] & df['ema_touch'] & df['fib_confluence'] & df['is_bullish_pin']
    return df
