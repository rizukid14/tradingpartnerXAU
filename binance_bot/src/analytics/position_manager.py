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


def manage_all_positions():
    """
    Cek & manage semua posisi open (spot). Fase 1:
    - Deteksi posisi yang ter-close (OCO kena SL/TP) → return info utk P/L tracking.
    - Belum ada trailing/BE aktif (fase 2).

    Return list posisi open yang masih ada.
    """
    # Cek order aktif (OCO). Kalau OCO sudah tidak ada tapi aset masih ada,
    # berarti proteksi hilang → pasang ulang (jika ada entry price tersimpan).
    try:
        open_orders = connector.get_open_orders(config.SYMBOL)
        qty = connector.get_asset_balance(config.SYMBOL)
        if qty > 0 and not open_orders:
            log.warning("[POSMAN] Aset ada tapi tidak ada OCO aktif — proteksi hilang. "
                        "Fase 1: lewati (entry price tidak tersimpan di exchange).")
        return connector.get_balance_and_positions()
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
