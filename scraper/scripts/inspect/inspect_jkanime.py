"""
Inspección de jkanime.net — extracción completa hasta el m3u8 final.
URL de prueba: https://jkanime.net/jujutsu-kaisen-tv/1/
"""
import re
import base64
import cloudscraper
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)

EPISODE_URL = "https://jkanime.net/jujutsu-kaisen-tv/1/"

# ── Paso 1: extraer URLs del array video[] ────────────────────────────────────
print(f"[1] Episode page: {EPISODE_URL}")
resp = scraper.get(EPISODE_URL, timeout=20)
print(f"    Status: {resp.status_code}")

soup = BeautifulSoup(resp.text, "html.parser")
video_entries: list[tuple[int, str]] = []
for script in soup.find_all("script"):
    text = script.string or ""
    for idx_str, iframe_html in re.findall(r"video\[(\d+)\]\s*=\s*'(<iframe[^']+)'", text):
        src_match = re.search(r'src="([^"]+)"', iframe_html)
        if src_match:
            video_entries.append((int(idx_str), src_match.group(1)))

print(f"    Servidores: {len(video_entries)}")
for idx, url in video_entries:
    print(f"      [{idx}] {url}")

# ── Paso 2: extraer m3u8 del player Magi (umv) — tiene <source> directo ──────
# Elegimos umv por ser el más limpio. Si falla, caemos en um.
def extract_m3u8_from_player(player_url: str) -> str | None:
    print(f"\n[2] Fetching player: {player_url[:80]}...")
    r = scraper.get(player_url, headers={"Referer": EPISODE_URL}, timeout=20)
    print(f"    Status: {r.status_code}")
    psoup = BeautifulSoup(r.text, "html.parser")

    # Opción A: <source src="...m3u8...">
    source = psoup.find("source", src=re.compile(r"\.m3u8"))
    if source:
        url = source["src"]
        print(f"    [source tag] {url}")
        return url

    # Opción B: JS con url: '...m3u8...' (DPlayer / commented out)
    for script in psoup.find_all("script"):
        m = re.search(r"url:\s*['\"]([^'\"]+\.m3u8[^'\"]*)['\"]", script.string or "")
        if m:
            url = m.group(1)
            print(f"    [JS url:] {url}")
            return url

    print("    No se encontró m3u8")
    return None

# Preferir umv (index 1), fallback a um (index 0)
m3u8_url = None
for idx in [1, 0]:
    entry = next((url for i, url in video_entries if i == idx), None)
    if entry:
        m3u8_url = extract_m3u8_from_player(entry)
        if m3u8_url:
            break

if not m3u8_url:
    print("\n!! No se pudo extraer la URL m3u8")
    exit(1)

# ── Paso 3: fetch del m3u8 master ─────────────────────────────────────────────
print(f"\n[3] Fetching master m3u8: {m3u8_url[:80]}...")
mr = scraper.get(m3u8_url, headers={"Referer": "https://jkanime.net/"}, timeout=15)
print(f"    Status:       {mr.status_code}")
print(f"    Content-Type: {mr.headers.get('Content-Type', '?')}")
print(f"    Final URL:    {mr.url}")
print()
print("    Content:")
print(mr.text[:2000])

# ── Paso 4: si es master playlist, seguir la primera variante ─────────────────
lines = [l.strip() for l in mr.text.splitlines() if l.strip()]
variant_urls = [l for l in lines if l and not l.startswith("#")]
if variant_urls:
    from urllib.parse import urljoin
    first_variant = urljoin(mr.url, variant_urls[0])
    print(f"\n[4] Fetching first variant: {first_variant[:80]}...")
    vr = scraper.get(first_variant, headers={"Referer": "https://jkanime.net/"}, timeout=15)
    print(f"    Status: {vr.status_code}")
    print()
    print("    Content (first 30 lines):")
    for line in vr.text.splitlines()[:30]:
        print(f"    {line}")

    # Buscar codec en el master
    codec_match = re.search(r'CODECS="([^"]+)"', mr.text)
    if codec_match:
        print(f"\n    CODECS declarados: {codec_match.group(1)!r}")
    else:
        print("\n    (No se declararon CODECS en el master)")
