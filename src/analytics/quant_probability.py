import numpy as np


def calculate_quant_probabilities(df, timeframe_minutes=60, num_simulations=1000, horizon_candles=4):
    """
    Calculates quantitative direction probabilities, price targets, and estimated time horizon
    purely using Python (Monte Carlo Simulation + Log-Return Drift & Volatility).

    Parameters:
      df: DataFrame containing 'close', 'high', 'low', 'atr_14' columns.
      timeframe_minutes: Candle duration in minutes (30 for M30, 5 for M5).
      num_simulations: Number of Monte Carlo price paths to simulate.
      horizon_candles: Forecast horizon in candles (e.g. 4 candles = 2 hours for M30).

    Returns dict:
      {
        'prob_up_pct': float,
        'prob_down_pct': float,
        'expected_target_up': float,
        'expected_target_down': float,
        'estimated_hours': float,
        'estimated_time_str': str
      }
    """
    if df is None or len(df) < 20 or 'close' not in df.columns:
        return {
            'prob_up_pct': 50.0,
            'prob_down_pct': 50.0,
            'expected_target_up': 0.0,
            'expected_target_down': 0.0,
            'estimated_hours': 0.0,
            'estimated_time_str': 'Unknown'
        }

    prices = df['close'].values
    current_price = float(prices[-1])

    # Log returns drift (mu) and volatility (sigma)
    returns = np.diff(np.log(prices))
    mu = np.mean(returns)
    sigma = np.std(returns)

    if sigma == 0:
        return {
            'prob_up_pct': 50.0,
            'prob_down_pct': 50.0,
            'expected_target_up': current_price,
            'expected_target_down': current_price,
            'estimated_hours': 0.0,
            'estimated_time_str': '0 min'
        }

    # Monte Carlo simulation of `horizon_candles` ahead
    # S_t = S_0 * exp( (mu - 0.5*sigma^2)*t + sigma * sqrt(t) * Z )
    dt = 1.0
    random_shocks = np.random.normal(0, 1, (num_simulations, horizon_candles))

    # Path simulation
    log_paths = np.zeros((num_simulations, horizon_candles + 1))
    log_paths[:, 0] = np.log(current_price)

    for t in range(1, horizon_candles + 1):
        log_paths[:, t] = log_paths[:, t - 1] + (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * random_shocks[:, t - 1]

    simulated_final_prices = np.exp(log_paths[:, -1])

    # Count how many paths end higher vs lower
    up_count = np.sum(simulated_final_prices > current_price)
    prob_up = round((up_count / num_simulations) * 100.0, 1)
    prob_down = round(100.0 - prob_up, 1)

    # Calculate 75th percentile (bull target) and 25th percentile (bear target)
    target_up = round(float(np.percentile(simulated_final_prices, 75)), 2)
    target_down = round(float(np.percentile(simulated_final_prices, 25)), 2)

    # Estimated time horizon calculation based on ATR velocity
    atr_val = float(df['atr_14'].iloc[-1]) if 'atr_14' in df.columns else (sigma * current_price)
    target_distance = abs(target_up - current_price)
    candles_needed = (target_distance / atr_val) if atr_val > 0 else horizon_candles
    estimated_minutes = round(candles_needed * timeframe_minutes)

    if estimated_minutes >= 60:
        hrs = estimated_minutes / 60.0
        time_str = f"~{hrs:.1f} Jam"
    else:
        time_str = f"~{estimated_minutes} Menit"

    return {
        'prob_up_pct': prob_up,
        'prob_down_pct': prob_down,
        'expected_target_up': target_up,
        'expected_target_down': target_down,
        'estimated_hours': round(estimated_minutes / 60.0, 2),
        'estimated_time_str': time_str
    }
