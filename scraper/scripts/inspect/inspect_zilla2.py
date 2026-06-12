import re
import json
import cloudscraper

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)

headers = {
    "Referer": "https://animeav1.com/",
    "Origin": "https://animeav1.com",
}

# 1. Fetch the JS bundle
bundle_url = "https://player.zilla-networks.com/assets/index-DOYntJxP.js"
print(f"Fetching bundle: {bundle_url}")
resp = scraper.get(bundle_url, timeout=20, headers=headers)
print(f"Status: {resp.status_code} | Size: {len(resp.text)} chars")
print()

js = resp.text

# 2. Look for API endpoint patterns
print("=== API/fetch/axios patterns ===")
patterns = [
    r'fetch\(["\`]([^"\'`]+)["\``]',
    r'axios\.[a-z]+\(["\`]([^"\'`]+)["\`]',
    r'["\'](/api/[^"\']+)["\']',
    r'["\'](https?://[^"\']*(?:api|video|source|stream|m3u8)[^"\']*)["\']',
    r'baseURL["\s:=]+["\'](https?://[^"\']+)["\']',
]
for pat in patterns:
    for m in re.findall(pat, js):
        print(f"  {m}")
print()

# 3. Look for m3u8 / mp4 patterns
print("=== m3u8 / mp4 references ===")
for m in re.findall(r'["\'][^"\']*(?:m3u8|\.mp4)[^"\']*["\']', js):
    print(f"  {m}")
print()

# 4. Dump first 2000 and last 1000 chars of the bundle
print("=== Bundle start (2000 chars) ===")
print(js[:2000])
print()
print("=== Bundle end (1000 chars) ===")
print(js[-1000:])
