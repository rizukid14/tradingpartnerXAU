import numpy as np


def calculate_hurst_exponent(prices, max_lag=20):
    """
    Calculates the Hurst Exponent (H) of a price time-series using Rescaled Range (R/S) analysis.
    Interpretation:
      H ~ 0.50 (0.45 - 0.55): Pure Random Walk (no edge / pure noise)
      H > 0.55: Persistent / Trending (momentum continuation)
      H < 0.45: Anti-persistent / Mean Reverting (range bound)
    """
    try:
        prices = np.asarray(prices, dtype=float)
        if len(prices) < 20:
            return 0.5

        returns = np.diff(np.log(prices))
        if len(returns) < 10 or np.std(returns) == 0:
            return 0.5

        lags = list(range(2, min(max_lag, len(returns) // 2)))
        rs_list = []
        valid_lags = []

        for lag in lags:
            num_chunks = len(returns) // lag
            if num_chunks < 1:
                continue
            rs_sub = []
            for i in range(num_chunks):
                chunk = returns[i * lag : (i + 1) * lag]
                mean_c = np.mean(chunk)
                std_c = np.std(chunk)
                if std_c > 0:
                    dev = np.cumsum(chunk - mean_c)
                    r = np.max(dev) - np.min(dev)
                    rs_sub.append(r / std_c)
            if len(rs_sub) > 0:
                rs_list.append(np.mean(rs_sub))
                valid_lags.append(lag)

        if len(rs_list) < 2:
            return 0.5

        reg = np.polyfit(np.log(valid_lags), np.log(rs_list), 1)
        hurst = float(reg[0])
        return max(0.0, min(1.0, round(hurst, 4)))
    except Exception as e:
        print(f"[RANDOMNESS ERROR] Gagal menghitung Hurst Exponent: {e}")
        return 0.5


def calculate_fat_tail_metrics(prices):
    """
    Calculates Excess Kurtosis, Skewness, and Tail Risk of log returns.
    Interpretation:
      Excess Kurtosis (K):
        K ~ 0: Normal / Gaussian distribution (thin tails)
        K > 1.5: High Fat-Tails (Heavy Tail Risk — extreme spikes happen more often!)
      Skewness (S):
        S < -0.5: Negative Skew (Fat Left Tail / Crash Risk)
        S > +0.5: Positive Skew (Fat Right Tail / Spike Risk)
    """
    try:
        prices = np.asarray(prices, dtype=float)
        if len(prices) < 15:
            return {'kurtosis': 0.0, 'skewness': 0.0, 'fat_tailed': False, 'label': 'NORMAL'}

        returns = np.diff(np.log(prices))
        n = len(returns)
        if n < 10 or np.std(returns) == 0:
            return {'kurtosis': 0.0, 'skewness': 0.0, 'fat_tailed': False, 'label': 'NORMAL'}

        mean_r = np.mean(returns)
        std_r = np.std(returns)

        # 3rd and 4th central moments
        m3 = np.mean((returns - mean_r) ** 3)
        m4 = np.mean((returns - mean_r) ** 4)

        skewness = float(m3 / (std_r ** 3)) if std_r > 0 else 0.0
        # Excess Kurtosis (Kurtosis - 3.0)
        excess_kurtosis = float((m4 / (std_r ** 4)) - 3.0) if std_r > 0 else 0.0

        fat_tailed = excess_kurtosis > 1.5

        if excess_kurtosis > 3.0:
            label = 'EXTREME_FAT_TAILS'
        elif excess_kurtosis > 1.5:
            label = 'MODERATE_FAT_TAILS'
        elif excess_kurtosis < -0.5:
            label = 'THIN_TAILS'
        else:
            label = 'NEAR_GAUSSIAN'

        return {
            'kurtosis': round(excess_kurtosis, 2),
            'skewness': round(skewness, 2),
            'fat_tailed': fat_tailed,
            'label': label
        }
    except Exception as e:
        print(f"[RANDOMNESS ERROR] Gagal menghitung Fat-Tail metrics: {e}")
        return {'kurtosis': 0.0, 'skewness': 0.0, 'fat_tailed': False, 'label': 'NORMAL'}


def analyze_market_randomness(df, symbol=None):
    """
    Analyzes DataFrame of candles for market randomness & fat-tail metrics.
    - Hurst Exponent (H): Calculated on main timeframe (H1/M5) for trend persistence.
    - Kurtosis & Skewness: Calculated on micro timeframe (M5 for BTC, M1 for XAU)
      to detect micro-structure wicks, stop-hunts, and fat-tail spikes.
    """
    if df is None or len(df) < 30 or 'close' not in df.columns:
        return {
            'hurst': 0.5,
            'fat_tail': {'kurtosis': 0.0, 'skewness': 0.0, 'fat_tailed': False, 'label': 'UNKNOWN'},
            'regime': 'UNKNOWN',
            'is_random': True,
            'reason': 'Data candle tidak cukup untuk kalkulasi randomness'
        }

    prices = df['close'].values
    hurst = calculate_hurst_exponent(prices)

    # Micro-structure Fat-Tail check (M30 for BTC H1 swing, M5 for XAU M5 scalp)
    fat_tail_prices = prices
    micro_label = "main"
    if symbol:
        try:
            import config
            from src.core import mt5_connector as connector
            if sys_mt5 := getattr(connector, "mt5", None):
                is_cr = config.is_crypto(symbol)
                # BTC H1 swing -> M30 (24 candles = 12 jam)
                # XAU M5 scalp -> M5 (48 candles = 4 jam)
                micro_tf = sys_mt5.TIMEFRAME_M30 if is_cr else sys_mt5.TIMEFRAME_M5
                num_micro_candles = 24 if is_cr else 48  
                micro_df = connector.get_market_data(symbol, micro_tf, num_candles=num_micro_candles)
                if micro_df is not None and len(micro_df) >= 15:
                    fat_tail_prices = micro_df['close'].values
                    micro_label = "M30 12h" if is_cr else "M5 4h"
        except Exception:
            pass

    fat_tail = calculate_fat_tail_metrics(fat_tail_prices)
    fat_tail['tf'] = micro_label

    # Regime identification
    if 0.45 <= hurst <= 0.55:
        regime = 'RANDOM_WALK'
    elif hurst > 0.55:
        regime = 'TRENDING'
    else:
        regime = 'MEAN_REVERTING'

    # Filter condition: Pure Random Walk (0.46 <= H <= 0.54)
    is_random = (0.46 <= hurst <= 0.54)

    reason = (
        f"Hurst={hurst:.2f} ({regime}), "
        f"Kurtosis({micro_label})={fat_tail['kurtosis']:+.2f} ({fat_tail['label']})"
    )

    return {
        'hurst': hurst,
        'fat_tail': fat_tail,
        'regime': regime,
        'is_random': is_random,
        'reason': reason
    }
