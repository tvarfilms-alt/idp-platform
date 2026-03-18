"""
Shared database helpers for IDP compute modules.
All compute modules read from raw_market_data (via v_raw_latest)
and write to their respective output tables.
"""
import os
import json
import requests
from datetime import date, datetime, timedelta

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

REST_URL = f"{SUPABASE_URL}/rest/v1"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


def rest_get(table: str, params: dict = None) -> list:
    """GET from Supabase REST API."""
    r = requests.get(f"{REST_URL}/{table}", headers=HEADERS, params=params or {})
    r.raise_for_status()
    return r.json()


def rest_upsert(table: str, rows: list, on_conflict: str = None) -> int:
    """UPSERT rows to Supabase REST API. Returns count of rows sent."""
    if not rows:
        return 0
    h = {**HEADERS, "Prefer": "resolution=merge-duplicates"}
    if on_conflict:
        h["Prefer"] += f",on_conflict={on_conflict}"
    r = requests.post(f"{REST_URL}/{table}", headers=h, json=rows)
    r.raise_for_status()
    return len(rows)


def get_raw_latest(tickers: list, date_from: str = None, date_to: str = None) -> list:
    """Fetch latest revision data for given tickers from v_raw_latest."""
    params = {"select": "date,ticker,close_price,extra_json,source"}
    if tickers:
        params["ticker"] = f"in.({','.join(tickers)})"
    if date_from:
        params["date"] = f"gte.{date_from}"
    if date_to:
        if "date" in params:
            # Need to use AND logic — use separate calls or range
            pass
        params["date"] = f"lte.{date_to}" if "date" not in params else params["date"]
    params["order"] = "date.asc,ticker.asc"
    return rest_get("v_raw_latest", params)


def get_raw_range(tickers: list, date_from: str, date_to: str) -> list:
    """Fetch raw data for tickers in a date range."""
    params = {
        "select": "date,ticker,close_price,extra_json,source",
        "ticker": f"in.({','.join(tickers)})",
        "and": f"(date.gte.{date_from},date.lte.{date_to})",
        "order": "date.asc,ticker.asc",
        "limit": "10000",
    }
    return rest_get("v_raw_latest", params)


def get_calc_version(level: str) -> dict:
    """Get active calc_versions config for a level."""
    rows = rest_get("calc_versions", {
        "level": f"eq.{level}",
        "valid_to": "is.null",
        "select": "version_id,config_json",
        "limit": "1",
    })
    if not rows:
        raise ValueError(f"No active calc_version for level={level}")
    return rows[0]


def get_instruments(level: str = None, active_only: bool = True) -> list:
    """Get instruments from instrument_dict."""
    params = {"select": "*", "order": "ticker"}
    if level:
        params["level"] = f"eq.{level}"
    if active_only:
        params["is_active"] = "eq.true"
    return rest_get("instrument_dict", params)


def today_str() -> str:
    return date.today().isoformat()


def first_of_month(d: date = None) -> str:
    d = d or date.today()
    return d.replace(day=1).isoformat()


def months_ago(n: int, d: date = None) -> str:
    d = d or date.today()
    month = d.month - n
    year = d.year
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1).isoformat()


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")
