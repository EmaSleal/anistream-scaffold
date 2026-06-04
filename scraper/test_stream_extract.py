"""
Extracción confirmada de URL directa desde tpead.net (StreamTape).
Patrón: captchalink = part1 + part2.substring(N) + '&stream=1'
"""
import re
import cloudscraper

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)

def extract_streamtape_url(video_id: str) -> str | None:
    url = f"https://tpead.net/v/{video_id}/"
    print(f"[StreamTape/tpead] {url}")

    resp = scraper.get(url, headers={
        "Referer": "https://streamtape.com/",
    }, timeout=15)
    print(f"  Status: {resp.status_code}")
    if resp.status_code != 200:
        return None

    # Patrón: getElementById('captchalink').innerHTML = 'PART1'+ ('PART2').substring(N)
    m = re.search(
        r"getElementById\('captchalink'\)\.innerHTML\s*=\s*'([^']+)'\s*\+\s*\('([^']+)'\)\.substring\((\d+)\)",
        resp.text
    )
    if not m:
        print("  Patrón no encontrado")
        return None

    part1  = m.group(1)           # e.g. '//tpead.net/get_video?id=xoMo7'
    part2  = m.group(2)           # e.g. 'defgbA3LMIkd2e&expires=...&token=...'
    offset = int(m.group(3))      # e.g. 4

    raw = part1 + part2[offset:]  # '//tpead.net/get_video?id=xoMo7bA3LMIkd2e&expires=...&token=...'
    stream_url = f"https:{raw}&stream=1"
    print(f"  URL extraída: {stream_url}")
    return stream_url


def verify(url: str):
    print(f"\n  Verificando...")
    r = scraper.head(url, headers={"Referer": "https://tpead.net/"}, timeout=10, allow_redirects=True)
    print(f"  Status:         {r.status_code}")
    print(f"  Content-Type:   {r.headers.get('Content-Type', '?')}")
    print(f"  Content-Length: {r.headers.get('Content-Length', '?')} bytes")
    print(f"  Final URL:      {r.url}")


result = extract_streamtape_url("xoMo7bA3LMIkd2e")
if result:
    verify(result)
