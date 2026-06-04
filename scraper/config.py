from dotenv import load_dotenv
import os

load_dotenv(".env.local")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

JIKAN_BASE = "https://api.jikan.moe/v4"
REQUEST_DELAY = 0.5  # seconds between requests (Jikan: max 3 req/s)

ANIMEFLV_BASE = "https://www4.animeflv.net"
KITSU_BASE = "https://kitsu.io/api/edge"
TPEAD_BASE = "https://tpead.net"
CLOUDSCRAPER_BROWSER = {"browser": "chrome", "platform": "windows", "mobile": False}
