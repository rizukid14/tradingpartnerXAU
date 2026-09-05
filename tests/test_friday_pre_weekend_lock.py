import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
from zoneinfo import ZoneInfo
import config
from src.core.risk_engine import RiskEngine

WIB = ZoneInfo("Asia/Jakarta")

class TestFridayPreWeekendLock(unittest.TestCase):

    def setUp(self):
        self.risk = RiskEngine()

    def test_friday_pre_weekend_lock_activates_at_cutoff(self):
        # 2026-09-04 was Friday, 23:15 WIB>=23:00
        dt_friday_night = datetime(2026, 9, 4, 23, 15, tzinfo=WIB)
        can_trade, reason = self.risk._check_friday_pre_weekend_lock(symbol="EURUSD-ECNc", now_wib=dt_friday_night)
        self.assertFalse(can_trade)
        self.assertIn("Friday Pre-Weekend Lock", reason)

    def test_friday_before_cutoff_allowed(self):
        dt_friday_day = datetime(2026, 9, 4, 21, 30, tzinfo=WIB)
        can_trade, reason = self.risk._check_friday_pre_weekend_lock(symbol="EURUSD-ECNc", now_wib=dt_friday_day)
        self.assertTrue(can_trade)
        self.assertEqual(reason, "")

    def test_saturday_morning_pre_close_blocked(self):
        dt_sat_morning = datetime(2026, 9, 5, 2, 30, tzinfo=WIB)
        can_trade, reason = self.risk._check_friday_pre_weekend_lock(symbol="EURUSD-ECNc", now_wib=dt_sat_morning)
        self.assertFalse(can_trade)
        self.assertIn("Friday/Weekend Pre-Close Lock", reason)

    def test_crypto_excluded_when_btc_rotation_enabled(self):
        dt_sat_morning = datetime(2026, 9, 5, 2, 30, tzinfo=WIB)
        with patch.object(config, "ENABLE_BTC_ROTATION", True):
            can_trade, reason = self.risk._check_friday_pre_weekend_lock(symbol="BTCUSD.c", now_wib=dt_sat_morning)
            self.assertTrue(can_trade)
            self.assertEqual(reason, "")

if __name__ == "__main__":
    unittest.main()
