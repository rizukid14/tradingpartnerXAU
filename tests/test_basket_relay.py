import pytest
from dataclasses import dataclass, field
from typing import Dict, Any, List

import config
from src.analytics.basket_sync_engine import (
    filter_and_rank_batch_candidates,
    check_basket_directional_conflict,
    check_basket_concurrency_cap
)


@dataclass
class DummyCandidate:
    symbol: str
    direction: int
    trigger_price: float = 1.00000
    suggested_sl: float = 0.99500
    suggested_tp: float = 1.01000
    current_atr_pts: float = 50.0
    setup_type: str = "MULTI_TOUCH_BREAKOUT_RETEST"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DummyPosition:
    ticket: int
    symbol: str
    type: int  # 0 = BUY, 1 = SELL


def test_intra_batch_directional_conflict_resolution():
    """
    Uji resolusi konflik intra-batch:
    Jika batch memiliki EURAUD SELL (Short EUR) dan EURNZD BUY (Long EUR),
    dan CSM EUR > 0 (+10.7), maka EURAUD SELL wajib digugurkan dan EURNZD BUY lolos.
    """
    cand1 = DummyCandidate(symbol="EURAUD-ECNc", direction=-1, trigger_price=1.61238)
    cand2 = DummyCandidate(symbol="EURNZD-ECNc", direction=1, trigger_price=1.98970)

    # Mock macro cache with ample runway for both
    macro_cache = {
        "EURAUD-ECNc": {
            "atr": 0.0050,
            "zce_walls": {"f1_price": 1.59000, "c1_price": 1.63000, "f1_grade": "G1", "c1_grade": "G1"}
        },
        "EURNZD-ECNc": {
            "atr": 0.0050,
            "zce_walls": {"f1_price": 1.97000, "c1_price": 2.01000, "f1_grade": "G1", "c1_grade": "G1"}
        }
    }

    csm_scores = {
        "EUR": 10.72,
        "AUD": -12.71,
        "NZD": 2.09,
        "USD": 9.43
    }

    champions = filter_and_rank_batch_candidates(
        candidates=[cand1, cand2],
        macro_cache=macro_cache,
        active_positions=[],
        active_orders=[],
        csm_scores=csm_scores
    )

    # Hanya EURNZD BUY yang harus lolos, EURAUD SELL harus dibuang
    assert len(champions) == 1
    assert champions[0].symbol == "EURNZD-ECNc"
    assert champions[0].direction == 1
    assert champions[0].metadata.get("cbss_champion") is True


def test_portfolio_conflict_blocking(monkeypatch):
    """
    Uji Anti-Internal Currency Hedge terhadap posisi portfolio:
    Jika portofolio aktif memegang EURNZD BUY (Long EUR), maka kandidat
    EURAUD SELL (Short EUR) wajib ditolak saat fitur diaktifkan.
    """
    monkeypatch.setattr(config, "ENABLE_ANTI_INTERNAL_HEDGE", True)
    existing_pos = [DummyPosition(ticket=1001, symbol="EURNZD-ECNc", type=0)]  # 0 = BUY
    cand = DummyCandidate(symbol="EURAUD-ECNc", direction=-1)  # SELL

    macro_cache = {
        "EURAUD-ECNc": {
            "atr": 0.0050,
            "zce_walls": {"f1_price": 1.59000, "c1_price": 1.63000, "f1_grade": "G1", "c1_grade": "G1"}
        }
    }

    champions = filter_and_rank_batch_candidates(
        candidates=[cand],
        macro_cache=macro_cache,
        active_positions=existing_pos,
        active_orders=[]
    )

    assert len(champions) == 0


def test_wall_exhaustion_skip():
    """
    Uji skip pair yang mepet benteng ZCE (Runway < 0.50x ATR):
    Jika harga live sangat dekat dengan C1 Ceiling pada BUY setup,
    pair dinyatakan WALL_EXHAUSTED dan tidak dieksekusi.
    """
    # Live price 1.6190, C1 Ceiling 1.6200 -> Runway 0.0010 / ATR 0.0050 = 0.20x ATR (< 0.50x ATR)
    cand = DummyCandidate(symbol="EURAUD-ECNc", direction=1, trigger_price=1.6190)

    macro_cache = {
        "EURAUD-ECNc": {
            "atr": 0.0050,
            "zce_walls": {"f1_price": 1.60000, "c1_price": 1.62000, "f1_grade": "GRADE_3_MACRO", "c1_grade": "GRADE_3_MACRO"}
        }
    }

    champions = filter_and_rank_batch_candidates(
        candidates=[cand],
        macro_cache=macro_cache,
        active_positions=[],
        active_orders=[]
    )

    assert len(champions) == 0


def test_laggard_champion_selection():
    """
    Uji estafet likuiditas ke pair laggard:
    Jika EURAUD BUY memiliki runway 1.0x ATR, sedangkan EURNZD BUY memiliki runway 2.5x ATR,
    maka EURNZD BUY dipilih sebagai Champion dengan runway lebih luas.
    """
    cand1 = DummyCandidate(symbol="EURAUD-ECNc", direction=1, trigger_price=1.6100)  # Runway ~1.0x ATR
    cand2 = DummyCandidate(symbol="EURNZD-ECNc", direction=1, trigger_price=1.9800)  # Runway ~2.5x ATR

    macro_cache = {
        "EURAUD-ECNc": {
            "atr": 0.0050,
            "zce_walls": {"f1_price": 1.60000, "c1_price": 1.61500, "f1_grade": "G1", "c1_grade": "G1"}
        },
        "EURNZD-ECNc": {
            "atr": 0.0050,
            "zce_walls": {"f1_price": 1.97000, "c1_price": 2.00000, "f1_grade": "G1", "c1_grade": "G1"}
        }
    }

    champions = filter_and_rank_batch_candidates(
        candidates=[cand1, cand2],
        macro_cache=macro_cache,
        active_positions=[],
        active_orders=[]
    )

    # EURNZD harus memiliki skor lebih tinggi karena runway 2.0x vs 1.0x
    assert len(champions) >= 1
    assert champions[0].symbol == "EURNZD-ECNc"
    assert champions[0].metadata["runway_atr"] > 1.5


def test_crypto_and_gold_exempt():
    """
    Uji pengecualian BTCUSD dan XAUUSD dari pembatasan basket mata uang fiat.
    """
    cand_btc = DummyCandidate(symbol="BTCUSD.c", direction=1)
    cand_xau = DummyCandidate(symbol="XAUUSD-ECNc", direction=-1)

    champions = filter_and_rank_batch_candidates(
        candidates=[cand_btc, cand_xau],
        macro_cache={},
        active_positions=[],
        active_orders=[]
    )

    assert len(champions) == 2
    symbols = [c.symbol for c in champions]
    assert "BTCUSD.c" in symbols
    assert "XAUUSD-ECNc" in symbols


def test_tuple_active_positions_does_not_crash():
    """
    Uji ketahanan tipe data: MT5 mengembalikan positions dan orders bertipe tuple.
    Memastikan filter_and_rank_batch_candidates tidak melempar TypeError saat menerima tuple.
    """
    cand = DummyCandidate(symbol="EURUSD-ECNc", direction=1)
    macro_cache = {
        "EURUSD-ECNc": {
            "atr_h1": 0.0010,
            "c1_price": 1.1000,
            "f1_price": 1.0900,
            "immediate_ceiling_c1": 1.1000,
            "immediate_floor_f1": 1.0900,
            "c1_reaction_grade": "GRADE_1_MICRO",
            "f1_reaction_grade": "GRADE_1_MICRO"
        }
    }

    # Pass tuple bertipe TradePosition dummy
    dummy_pos = (DummyPosition(ticket=1001, symbol="GBPUSD-ECNc", type=0),)
    dummy_ord = (DummyPosition(ticket=2001, symbol="USDJPY-ECNc", type=1),)

    champions = filter_and_rank_batch_candidates(
        candidates=[cand],
        macro_cache=macro_cache,
        active_positions=dummy_pos, # TUPLE dari MT5
        active_orders=dummy_ord,    # TUPLE dari MT5
        csm_scores={"EUR": 1.5, "USD": -1.0}
    )

    assert isinstance(champions, list)
