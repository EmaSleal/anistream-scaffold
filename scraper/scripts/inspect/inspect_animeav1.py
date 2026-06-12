import re
import json
import cloudscraper
from bs4 import BeautifulSoup

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)

url = "https://animeav1.com/media/jujutsu-kaisen/1"

resp = scraper.get(url, timeout=20)
print(f"Status: {resp.status_code}")
print(f"Final URL: {resp.url}")
print()

soup = BeautifulSoup(resp.text, "html.parser")

# 1. Look for <video> or <source> tags
print("=== <video> / <source> tags ===")
for tag in soup.find_all(["video", "source"]):
    print(tag)
print()

# 2. Look for iframes (embedded players)
print("=== <iframe> tags ===")
for tag in soup.find_all("iframe"):
    print(tag)
print()

# 3. Look for inline JS with video URLs or player config
print("=== JS vars with video/player/stream ===")
for script in soup.find_all("script"):
    text = script.string or ""
    if any(k in text for k in ["file", "source", "player", "stream", "m3u8", "mp4", "jwplayer", "videojs"]):
        snippet = text[:600].strip()
        if snippet:
            print(snippet)
            print("---")
print()

# 4. Dump page title and any server/option list
print("=== Page title ===")
print(soup.title)
print()

# 5. Look for download/server links
print("=== Links with 'server' or 'download' ===")
for a in soup.find_all("a", href=True):
    href = a["href"]
    text = a.get_text(strip=True)
    if any(k in href.lower() or k in text.lower() for k in ["server", "download", "embed", "play"]):
        print(f"  {text!r} → {href}")
