"""
Prueba de acceso a cada tienda con tres estrategias:
  1. requests con headers de browser real
  2. cloudscraper (bypass Cloudflare JS challenge)
  3. WooCommerce REST API pública (/wp-json/wc/v3/products)

Objetivo: saber qué método funciona para cada sitio antes de armar el scraper real.
"""

import requests
import cloudscraper
from bs4 import BeautifulSoup
import json
import time

SITIOS = [
    "https://extremetechcr.com/",
    "https://techzilla.cr/",
    "https://extremeoutletcr.com/",
    "https://crtechstore.com/",
    "https://igamingcr.com/",
    "https://www.adntienda.com/",
    "https://www.intelec.co.cr/",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-CR,es;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Connection": "keep-alive",
}


def probar_requests(url: str) -> dict:
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        return {"status": r.status_code, "bytes": len(r.content)}
    except Exception as e:
        return {"status": "ERROR", "detalle": str(e)}


def probar_cloudscraper(url: str) -> dict:
    try:
        scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        r = scraper.get(url, timeout=15)
        return {"status": r.status_code, "bytes": len(r.content)}
    except Exception as e:
        return {"status": "ERROR", "detalle": str(e)}


def probar_woocommerce_api(base_url: str) -> dict:
    """Intenta la API pública de WooCommerce (sin auth, solo productos visibles)."""
    api_url = base_url.rstrip("/") + "/wp-json/wc/v3/products?per_page=3"
    try:
        r = requests.get(api_url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            productos = r.json()
            muestra = [
                {"nombre": p.get("name"), "precio": p.get("price")}
                for p in productos[:3]
            ]
            return {"status": 200, "productos_muestra": muestra}
        return {"status": r.status_code}
    except Exception as e:
        return {"status": "ERROR", "detalle": str(e)}


def extraer_titulo(html_bytes: bytes) -> str:
    try:
        soup = BeautifulSoup(html_bytes, "html.parser")
        return soup.title.string.strip() if soup.title else "(sin título)"
    except Exception:
        return "(error parseando)"


print("=" * 65)
print("ANÁLISIS DE ACCESO POR SITIO")
print("=" * 65)

resultados = {}

for url in SITIOS:
    print(f"\n>> {url}")

    # --- Estrategia 1: requests + headers ---
    r1 = probar_requests(url)
    print(f"  [requests]      status={r1['status']}", end="")
    if r1.get("bytes"):
        print(f"  ({r1['bytes']:,} bytes)", end="")
    print()

    # --- Estrategia 2: cloudscraper ---
    r2 = probar_cloudscraper(url)
    print(f"  [cloudscraper]  status={r2['status']}", end="")
    if r2.get("bytes"):
        print(f"  ({r2['bytes']:,} bytes)", end="")
    print()

    # --- Estrategia 3: WooCommerce API ---
    r3 = probar_woocommerce_api(url)
    print(f"  [wc api]        status={r3['status']}", end="")
    if r3.get("productos_muestra"):
        print(f"  → {r3['productos_muestra']}", end="")
    print()

    resultados[url] = {"requests": r1, "cloudscraper": r2, "wc_api": r3}

    time.sleep(1)  # cortesía entre requests

# Resumen final
print("\n" + "=" * 65)
print("RESUMEN")
print("=" * 65)
for url, res in resultados.items():
    nombre = url.replace("https://", "").replace("www.", "").split("/")[0]
    metodos_ok = []
    if str(res["requests"].get("status")) == "200":
        metodos_ok.append("requests")
    if str(res["cloudscraper"].get("status")) == "200":
        metodos_ok.append("cloudscraper")
    if str(res["wc_api"].get("status")) == "200":
        metodos_ok.append("wc_api")

    estado = "✅ " + " + ".join(metodos_ok) if metodos_ok else "❌ bloqueado"
    print(f"  {nombre:<30} {estado}")

print()
