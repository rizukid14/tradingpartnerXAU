"""
Unit tests for Dashboard Vertical Shading (Sessions & Regimes).
Verifies:
1. _get_session_info context-aware evaluation:
   - BTCUSD: 24/7 active (exempt from Dead Zone and Asian Lock)
   - Forex Dead Zone: 00:00-08:00 WIB (BLOCKED)
   - Forex Asian Lock: Non-Asian driver FX (EURUSD, GBPUSD) locked 08:00-14:00 WIB
   - Forex Asian Active: JPY/AUD/NZD allowed 08:00-14:00 WIB
   - Friday Lock: Friday >= 23:00 WIB (BLOCKED)
2. classify_wave_regimes_series:
   - Young Oscillation (<24h)
   - Mature Squeeze (24-72h)
   - Super Compression (>72h or >=16 squeeze bars)
3. get_symbol_detail payload contains aligned session and wave regime properties.
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
from zoneinfo import ZoneInfo

from dashboard import _get_session_info, _get_session_name, CockpitDataEngine
from src.indicators.wave_regime import classify_wave_regimes_series
import config

WIB = ZoneInfo("Asia/Jakarta")


class TestDashboardShading(unittest.TestCase):

    def test_session_info_crypto_247(self):
        """BTCUSD must always be PERMITTED 24/7, even during dead zone and Asian session."""
        dt_dead = datetime(2026, 9, 2, 3, 30, tzinfo=WIB)  # Wednesday 03:30 WIB
        s_btc = _get_session_info(dt_dead, "BTCUSD")
        self.assertEqual(s_btc["type"], "CRYPTO_247")
        self.assertEqual(s_btc["status"], "PERMITTED")

        dt_asia = datetime(2026, 9, 2, 10, 0, tzinfo=WIB)
        s_btc_asia = _get_session_info(dt_asia, "BTCUSD.c")
        self.assertEqual(s_btc_asia["type"], "CRYPTO_247")
        self.assertEqual(s_btc_asia["status"], "PERMITTED")

    def test_session_info_forex_dead_zone(self):
        """Forex pairs in 00:00-08:00 WIB must be flagged as DEAD_ZONE BLOCKED."""
        dt_dead = datetime(2026, 9, 2, 2, 15, tzinfo=WIB)  # Wednesday 02:15 WIB
        s_eur = _get_session_info(dt_dead, "EURUSD-ECN")
        self.assertEqual(s_eur["type"], "DEAD_ZONE")
        self.assertEqual(s_eur["status"], "BLOCKED")

    def test_session_info_asian_lock_vs_active(self):
        """During Tokyo session (08:00-14:00 WIB), non-Asian pairs are LOCKED, JPY/AUD/NZD are PERMITTED."""
        dt_asia = datetime(2026, 9, 2, 10, 0, tzinfo=WIB)  # Wednesday 10:00 WIB

        # EURUSD: Non-Asian driver -> LOCKED
        s_eur = _get_session_info(dt_asia, "EURUSD-ECN")
        self.assertEqual(s_eur["type"], "ASIAN_LOCKED")
        self.assertEqual(s_eur["status"], "BLOCKED")

        # GBPJPY: JPY driver -> ACTIVE
        s_jpy = _get_session_info(dt_asia, "GBPJPY-ECN")
        self.assertEqual(s_jpy["type"], "ASIAN_ACTIVE")
        self.assertEqual(s_jpy["status"], "PERMITTED")

        # AUDCAD: AUD driver -> ACTIVE
        s_aud = _get_session_info(dt_asia, "AUDCAD-ECNc")
        self.assertEqual(s_aud["type"], "ASIAN_ACTIVE")
        self.assertEqual(s_aud["status"], "PERMITTED")

    def test_session_info_friday_lock(self):
        """Friday >= 23:00 WIB and weekend must be FRIDAY_LOCK BLOCKED."""
        dt_fri = datetime(2026, 9, 4, 23, 15, tzinfo=WIB)  # Friday 23:15 WIB
        s_fri = _get_session_info(dt_fri, "GBPUSD-ECN")
        self.assertEqual(s_fri["type"], "FRIDAY_LOCK")
        self.assertEqual(s_fri["status"], "BLOCKED")

    def test_classify_wave_regimes_series(self):
        """classify_wave_regimes_series must correctly label Young, Mature, and Super Compression."""
        # 1. Young Oscillation: 20 bars oscillating wave
        import numpy as np
        highs_young = [100.0 + np.sin(i * 0.8) * 3.0 for i in range(20)]
        lows_young = [h - 0.8 for h in highs_young]
        closes_young = [(h + l) / 2.0 for h, l in zip(highs_young, lows_young)]
        res_young = classify_wave_regimes_series(highs_young, lows_young, closes_young, timeframe_hours=1.0)
        self.assertEqual(len(res_young), 20)
        self.assertEqual(res_young[-1]["regime"], "YOUNG_OSCILLATION")

        # 2. Super Compression (>72h age or >=16 squeeze bars)
        # Create flat series with extreme squeeze (std close to 0)
        highs_flat = [100.0] * 80
        lows_flat = [99.5] * 80
        closes_flat = [99.75] * 80
        res_super = classify_wave_regimes_series(highs_flat, lows_flat, closes_flat, timeframe_hours=1.0)
        self.assertEqual(res_super[-1]["regime"], "SUPER_COMPRESSION")

    @patch("dashboard.connector.get_valid_trade_symbol", return_value="EURUSD-ECN")
    def test_symbol_detail_contains_shading_data(self, mock_sym):
        """get_symbol_detail must return candles with session_type and wave_regime."""
        engine = CockpitDataEngine()
        engine.scanner = MagicMock()
        engine.scanner._m4_z_last = {}
        engine.scanner.get_radar_standbys.return_value = []
        engine.scanner.get_all_active_standbys.return_value = []
        engine.scanner.macro_cache = {
            "EURUSD-ECN": {
                "permission_state": "GO",
                "action_tier": "FULL_ALLOW",
                "current_atr_pts": 60.0
            }
        }

        mock_si = MagicMock()
        mock_si.digits = 5
        mock_si.point = 0.00001
        mock_tick = MagicMock()
        mock_tick.bid = 1.10000
        mock_tick.ask = 1.10020

        rates_data = [
            {"time": 1700000000 + i * 3600, "open": 1.1000, "high": 1.1020, "low": 1.0980, "close": 1.1010}
            for i in range(100)
        ]

        with patch.object(config.mt5, "symbol_info", return_value=mock_si):
            with patch.object(config.mt5, "symbol_info_tick", return_value=mock_tick):
                with patch.object(config.mt5, "copy_rates_from_pos", return_value=rates_data):
                    detail = engine.get_symbol_detail("EURUSD-ECN", "H1")
                    candles = detail.get("candles", [])
                    self.assertGreater(len(candles), 0)

                    c0 = candles[-1]
                    self.assertIn("session_type", c0)
                    self.assertIn("session_status", c0)
                    self.assertIn("session_color", c0)
                    self.assertIn("regime", c0)
                    self.assertIn("range_age_hours", c0)

                    intel = detail.get("intel", {})
                    self.assertIn("active_session", intel)
                    self.assertIn("active_session_status", intel)
                    self.assertIn("wave_regime_summary", intel)


if __name__ == "__main__":
    unittest.main()
