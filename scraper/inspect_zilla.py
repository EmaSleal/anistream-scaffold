import re
import cloudscraper
from bs4 import BeautifulSoup

scraper = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "mobile": False}
)

url = "https://player.zilla-networks.com/play/4a870ee9bd16efa522eaf330f84da5c1"

resp = scraper.get(url, timeout=20, headers={
    "Referer": "https://animeav1.com/",
    "Origin": "https://animeav1.com",
})
print(f"Status: {resp.status_code}")
print()

soup = BeautifulSoup(resp.text, "html.parser")

# 1. video / source tags
print("=== <video> / <source> ===")
for tag in soup.find_all(["video", "source"]):
    print(tag)
print()

# 2. iframes
print("=== <iframe> ===")
for tag in soup.find_all("iframe"):
    print(tag)
print()

# 3. JS with file/stream/m3u8/mp4
print("=== Relevant JS snippets ===")
for script in soup.find_all("script"):
    text = script.string or script.get("src") or ""
    if any(k in text for k in ["file", "m3u8", "mp4", "source", "jwplayer", "hls", "stream", "token"]):
        print(text[:800].strip())
        print("---")
print()

# 4. All external script srcs (might load player config)
print("=== Script srcs ===")
for script in soup.find_all("script", src=True):
    print(script["src"])
print()

print("=== Raw HTML (first 3000 chars) ===")
print(resp.text[:3000])
