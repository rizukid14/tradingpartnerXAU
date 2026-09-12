"""
MACRO HISTORICAL DATA LOADER AND AUTO-SEEDER
===========================================
Loads multi-decade historical secular data from assets/macro_history/ (FBS 1990-2026)
and seamlessly appends real-time live bars from active MT5 broker (VTMarkets).

Features:
  - 30+ Year Secular Foundation: W1 (~1,650 bars) and MN1 (~440 bars).
  - Real-time Live Merge: Appends/upserts current forming bar from MT5 tick/bar stream.
  - Auto-Seeding (W1 Weekly / MN1 Monthly):
      * W1: Automatically persists newly closed weekly bar upon weekend rollover.
      * MN1: Automatically persists newly closed monthly bar at the start of a new month.
  - Graceful Fallback: If local seed CSV is missing, falls back to native MT5 query.
"""

import os
import sys
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
import numpy as np
import pandas as pd

logger = logging.getLogger("macro_data_loader")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASSETS_MACRO_DIR = os.path.join(BASE_DIR, "assets", "macro_history")

COL_MAP = {
    "time": "time",
    "O": "open", "open": "open",
    "H": "high", "high": "high",
    "L": "low", "low": "low",
    "C": "close", "close": "close",
    "Vol": "tick_volume", "tick_volume": "tick_volume",
    "spread": "spread",
    "real_volume": "real_volume"
}


class MacroDataLoader:
    """
    Manages loading, merging, and caching of deep historical macro candles (W1 and MN1).
    """
    _cached_seeds: Dict[str, pd.DataFrame] = {}

    @classmethod
    def clean_symbol(cls, symbol: str) -> str:
        """Strips broker suffixes to get base clean symbol (e.g., EURUSD-ECNc -> EURUSD)."""
        return (
            symbol.replace("-ECNc", "")
            .replace(".c", "")
            .replace("-ECN", "")
            .replace("m", "")
            .upper()
        )

    @classmethod
    def get_seed_path(cls, symbol: str, timeframe_str: str) -> str:
        clean_sym = cls.clean_symbol(symbol)
        tf = timeframe_str.upper()
        return os.path.join(ASSETS_MACRO_DIR, f"{clean_sym}_{tf}.csv.gz")

    @classmethod
    def load_seed(cls, symbol: str, timeframe_str: str) -> Optional[pd.DataFrame]:
        """Loads historical baseline from compressed CSV file."""
        clean_sym = cls.clean_symbol(symbol)
        tf = timeframe_str.upper()
        cache_key = f"{clean_sym}_{tf}"

        if cache_key in cls._cached_seeds:
            return cls._cached_seeds[cache_key].copy()

        seed_path = cls.get_seed_path(clean_sym, tf)
        if not os.path.exists(seed_path):
            logger.debug(f"[MacroDataLoader] Seed file not found: {seed_path}")
            return None

        try:
            df = pd.read_csv(seed_path, compression="gzip")
            df = df.rename(columns={k: v for k, v in COL_MAP.items() if k in df.columns})

            if "time" in df.columns:
                if df["time"].dtype == object or str(df["time"].iloc[0]).startswith("19") or str(df["time"].iloc[0]).startswith("20"):
                    df["time"] = pd.to_datetime(df["time"]).map(lambda x: int(x.timestamp()))
                else:
                    df["time"] = df["time"].astype("int64")

            for col in ["open", "high", "low", "close"]:
                if col in df.columns:
                    df[col] = df[col].astype(float)

            if "tick_volume" in df.columns:
                df["tick_volume"] = df["tick_volume"].astype("int64")

            df = df.sort_values("time").reset_index(drop=True)
            cls._cached_seeds[cache_key] = df
            return df.copy()
        except Exception as e:
            logger.error(f"[MacroDataLoader] Failed loading seed for {clean_sym}_{tf}: {e}")
            return None

    @classmethod
    def get_deep_macro_rates(
        cls,
        symbol: str,
        timeframe_const: int,
        mt5_connector=None,
        live_fetch_bars: int = 15
    ) -> Optional[np.ndarray]:
        """
        Retrieves complete multi-decade rates merged with live broker bars.
        Returns a numpy structured array matching mt5.copy_rates_from_pos() format.
        """
        import config
        from config import mt5

        tf_str = "W1" if timeframe_const == mt5.TIMEFRAME_W1 else ("MN1" if timeframe_const == mt5.TIMEFRAME_MN1 else None)
        clean_sym = cls.clean_symbol(symbol)

        live_rates = None
        try:
            live_sym = symbol
            if mt5_connector and hasattr(mt5_connector, "get_valid_trade_symbol"):
                live_sym = mt5_connector.get_valid_trade_symbol(symbol)
            live_rates = mt5.copy_rates_from_pos(live_sym, timeframe_const, 0, live_fetch_bars)
            if live_rates is None or len(live_rates) == 0:
                live_rates = mt5.copy_rates_from_pos(clean_sym, timeframe_const, 0, live_fetch_bars)
        except Exception as e:
            logger.debug(f"[MacroDataLoader] Live rates fetch warning for {symbol}: {e}")

        if not tf_str:
            return live_rates

        df_hist = cls.load_seed(clean_sym, tf_str)
        if df_hist is None or df_hist.empty:
            return live_rates

        if live_rates is not None and len(live_rates) > 0:
            df_live = pd.DataFrame(live_rates)
            df_live = df_live.rename(columns={k: v for k, v in COL_MAP.items() if k in df_live.columns})
            if "time" in df_live.columns:
                df_live["time"] = df_live["time"].astype("int64")

            cls._maybe_auto_seed_new_bars(clean_sym, tf_str, df_hist, df_live)

            combined = pd.concat([df_hist, df_live]).drop_duplicates(subset=["time"], keep="last")
            combined = combined.sort_values("time").reset_index(drop=True)
        else:
            combined = df_hist

        dtypes = [
            ("time", "i8"),
            ("open", "f8"),
            ("high", "f8"),
            ("low", "f8"),
            ("close", "f8"),
            ("tick_volume", "i8"),
            ("spread", "i4"),
            ("real_volume", "i8")
        ]
        records = [
            (
                int(row["time"]),
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                int(row.get("tick_volume", 0)),
                int(row.get("spread", 10)),
                int(row.get("real_volume", 0))
            )
            for _, row in combined.iterrows()
        ]
        return np.array(records, dtype=dtypes)

    @classmethod
    def _maybe_auto_seed_new_bars(cls, clean_sym: str, tf_str: str, df_hist: pd.DataFrame, df_live: pd.DataFrame):
        """Auto-seeding periodic persistence for closed W1/MN1 bars."""
        try:
            if df_live.empty or len(df_live) < 2:
                return

            closed_bar = df_live.iloc[-2]
            closed_time = int(closed_bar["time"])
            hist_last_time = int(df_hist["time"].iloc[-1])

            if closed_time > hist_last_time:
                seed_path = cls.get_seed_path(clean_sym, tf_str)
                logger.info(f"[MacroDataLoader AUTO-SEED] New closed {tf_str} bar for {clean_sym} (time={closed_time}). Persisting to {seed_path}...")

                new_row = closed_bar.to_dict()
                iso_date = datetime.fromtimestamp(closed_time, tz=timezone.utc).strftime("%Y-%m-%d")
                new_row["time"] = iso_date
                rename_back = {"open": "O", "high": "H", "low": "L", "close": "C", "tick_volume": "Vol"}
                new_row = {rename_back.get(k, k): v for k, v in new_row.items()}

                raw_df = pd.read_csv(seed_path, compression="gzip")
                append_df = pd.DataFrame([new_row])
                updated_df = pd.concat([raw_df, append_df]).drop_duplicates(subset=["time"], keep="last")
                updated_df.to_csv(seed_path, index=False, compression="gzip")

                cache_key = f"{clean_sym}_{tf_str}"
                cls._cached_seeds.pop(cache_key, None)
                logger.info(f"[MacroDataLoader AUTO-SEED SUCCESS] {clean_sym}_{tf_str} updated. Total bars: {len(updated_df)}")
        except Exception as e:
            logger.debug(f"[MacroDataLoader AUTO-SEED Error] {clean_sym}_{tf_str}: {e}")
