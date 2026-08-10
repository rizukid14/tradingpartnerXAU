"""Ekstrak info penting dari docs TokoCrypto HTML — jalankan: py extract_toko.py"""
import re

html = open("Tokocrypto API Documentation.html", encoding="utf-8", errors="replace").read()
print("HTML size:", len(html))

# Cek apakah konten ada di HTML langsung atau dimuat via JS
if "api.tokocrypto" in html or "www.tokocrypto.com" in html:
    print("Base URL ada di HTML")
else:
    print("Base URL TIDAK ada di HTML (mungkin dimuat via JS)")

# Cari endpoint penting
for kw in ["klines", "order/oco", "account", "userDataStream", "api/v3", "open/v1", "recvWindow", "signature"]:
    count = html.lower().count(kw.lower())
    print(f"  '{kw}': {count} kemunculan")

# Coba ekstrak teks
text = re.sub(r"<script.*?</script>", " ", html, flags=re.DOTALL)
text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL)
text = re.sub(r"<[^>]+>", " ", text)
text = re.sub(r"\s+", " ", text)
print("\nTeks (500 char pertama):")
print(text[:500])
