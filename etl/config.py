"""
IDP ETL Configuration
Reads secrets from environment variables (GitHub Actions secrets or .env)
"""
import os

# Supabase
SUPABASE_URL = os.environ["SUPABASE_URL"]          # https://sjrskryuihrirhhrtoqu.supabase.co
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]   # service_role key (server-side writes)

# Finance Marker API
FM_API_TOKEN = os.environ.get("FM_API_TOKEN", "")

# Supabase REST helpers
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates",        # UPSERT mode
}

REST_URL = f"{SUPABASE_URL}/rest/v1"

# MOEX ISS endpoints
MOEX_BASE = "https://iss.moex.com/iss"
MOEX_STOCKS_URL = f"{MOEX_BASE}/engines/stock/markets/shares/boards/TQBR/securities.json"
MOEX_INDEX_URL = f"{MOEX_BASE}/engines/stock/markets/index/securities"  # /{TICKER}.json

# Rate limits
MOEX_DELAY_SEC = 0.5
FM_DELAY_SEC = 0.4
