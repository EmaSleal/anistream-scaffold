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

# Base URL for this scraper service — used to build self-referencing proxy URLs.
# Override via environment variable when running behind a reverse proxy.
SCRAPER_BASE_URL = os.environ.get("SCRAPER_BASE_URL", "http://localhost:5000")

# NAS API (disk-api-skeleton on astro1). Both must be set for NAS lookups to activate.
NAS_BASE_URL = os.environ.get("NAS_BASE_URL", "")
NAS_API_KEY = os.environ.get("NAS_API_KEY", "")
