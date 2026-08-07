import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import config
from src.core import telegram_alerts as tg

def main():
    print("=" * 60)
    print("             TEST RUN: TELEGRAM ALERTS BOT                 ")
    print("=" * 60)
    print(f"Telegram Enabled: {config.TELEGRAM_ENABLED}")
    print(f"Bot Token Configured: {'YA' if config.TELEGRAM_BOT_TOKEN else 'TIDAK'}")
    print(f"Chat ID Configured: {'YA' if config.TELEGRAM_CHAT_ID else 'TIDAK'}")
    print("-" * 60)
    
    if not config.TELEGRAM_ENABLED:
        print("⚠️ TELEGRAM_ENABLED=false di .env. Ubah menjadi TELEGRAM_ENABLED=true untuk menguji!")
        return

    print("🚀 Mengirim pesan uji coba ke Telegram...")
    success = tg.send_message("🤖 *Bot Trading XAUUSD Connected!*\nNotifikasi Telegram berhasil terhubung dan siap digunakan! 🔥")
    if success:
        print("🎉 BERHASIL! Pesan uji coba telah terkirim ke Telegram Anda.")
    else:
        print("❌ GAGAL! Periksa TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID di file .env Anda.")

if __name__ == "__main__":
    main()
