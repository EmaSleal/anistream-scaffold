import cloudscraper

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)

headers = {
    "Referer": "https://player.zilla-networks.com/play/4a870ee9bd16efa522eaf330f84da5c1",
    "Origin": "https://player.zilla-networks.com",
}

hash_id = "4a870ee9bd16efa522eaf330f84da5c1"

candidates = [
    f"https://player.zilla-networks.com/m3u8/{hash_id}",
    f"https://player.zilla-networks.com/m3u8/{hash_id}/index.m3u8",
    f"https://player.zilla-networks.com/m3u8/{hash_id}/master.m3u8",
    f"https://player.zilla-networks.com/api/video/{hash_id}",
    f"https://player.zilla-networks.com/api/source/{hash_id}",
]

for url in candidates:
    resp = scraper.get(url, timeout=15, headers=headers, allow_redirects=True)
    ct = resp.headers.get("content-type", "")
    print(f"[{resp.status_code}] {url}")
    print(f"  Content-Type: {ct}")
    print(f"  Body (200 chars): {resp.text[:200]}")
    print()
