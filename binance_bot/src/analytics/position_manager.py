"""
Position Manager untuk bot Binance spot (bot-side, karena spot tanpa SL/TP broker).

Mengelola trailing stop & break-even pada posisi BUY:
- Trailing: kalau harga naik X% dari entry → geser SL (stop-limit) ke belakang harga
- Break-even: kalau profit >= threshold → geser SL ke entry (nol risiko)

Karena posisi spot dilindungi OCO (SL stop-limit + TP limit), manager ini
menyesuaikan OCO saat harga bergerak (cancel + re-place, atau cancel SL leg saja).

Untuk fase 1 (modal kecil, testnet): implementasi sederhana — deteksi posisi
yang ter-close (OCO kena) via order status, tanpa trailing aktif dulu.
Trailing/BE aktif bisa ditambahkan di fase 2.
"""
import logging

import config
from src.core import binance_connector as connector

log = logging.getLogger("binance_bot")


def manage_all_positions(risk):
    """
    Cek & manage semua posisi open (spot) — pakai state lokal risk engine.
    - Deteksi posisi yang ter-close (OCO kena SL/TP) → tandai closed di risk state.
    - Belum ada trailing/BE aktif (fase 2).

    Return list posisi open yang masih ada.
    """
    try:
        open_positions = risk.get_open_positions(config.SYMBOL)
        if not open_positions:
            return []

        open_orders = connector.get_open_orders(config.SYMBOL)
        # Kalau ada posisi di-track tapi tidak ada OCO aktif → posisi sudah close
        # (OCO kena SL/TP) atau proteksi hilang. Tandai closed biar state akurat.
        if not open_orders:
            log.info("[POSMAN] Tidak ada OCO aktif tapi ada posisi ter-track — "
                     "tandai closed (OCO kena SL/TP).")
            risk.close_position(config.SYMBOL)
            return []
        return open_positions
    except Exception as e:
        log.error(f"[POSMAN ERROR] {e}")
        return None


def get_open_oco_status():
    """Status OCO aktif: list {order_id, side, price, stop_price, status}."""
    try:
        orders = connector.get_open_orders(config.SYMBOL)
        out = []
        for o in orders or []:
            out.append({
                "order_id": o.get("orderId"),
                "side": o.get("side"),
                "type": o.get("type"),
                "price": o.get("price"),
                "stop_price": o.get("stopPrice"),
                "status": o.get("status"),
                "symbol": o.get("symbol"),
            })
        return out
    except Exception as e:
        log.error(f"[POSMAN] Gagal get OCO status: {e}")
        return []
