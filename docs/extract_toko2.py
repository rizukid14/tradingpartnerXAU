"""Ekstrak detail: base URL, endpoint, signature dari docs TokoCrypto."""
import re

html = open("Tokocrypto API Documentation.html", encoding="utf-8", errors="replace").read()

# Cari base URL / host
for m in re.finditer(r"https?://[a-zA-Z0-9._-]+tokocrypto[a-zA-Z0-9._/-]*", html):
    print("URL:", m.group(0)[:100])
for m in re.finditer(r"https?://api[a-zA-Z0-9._-]*", html):
    print("URL api:", m.group(0)[:100])

# Cari konteks 'api/v3' dan 'open/v1'
print("\n--- konteks open/v1 ---")
for m in list(re.finditer(r"open/v1/[a-z0-9/_-]+", html))[:15]:
    print(" ", m.group(0))

print("\n--- konteks api/v3 ---")
for m in list(re.finditer(r"api/v3/[a-z0-9/_-]+", html))[:10]:
    print(" ", m.group(0))

# Signature / auth
print("\n--- signature context ---")
for m in list(re.finditer(r".{80}signature.{100}", html, re.DOTALL))[:3]:
    print(" ", m.group(0)[:200].replace("\n", " "))

# Endpoint order
print("\n--- order endpoints ---")
for m in list(re.finditer(r"open/v1/orders[a-z0-9/_-]*", html))[:10]:
    print(" ", m.group(0))
