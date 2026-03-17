"""
IDP ETL — Database helpers for Supabase REST API (PostgREST)
"""
import json
import logging
import requests
from datetime import date, datetime
from config import REST_URL, HEADERS

log = logging.getLogger("idp.db")


def upsert_raw_market_data(rows: list[dict]) -> int:
    """
    Upsert rows into raw_market_data via Supabase REST API.
    Each row must have: date, ticker, source, close_price, revision_num.
    Optional: volume, extra_json, etl_run_id.
    Returns number of rows upserted.
    """
    if not rows:
        return 0

    # Ensure date is string
    for r in rows:
        if isinstance(r.get("date"), date):
            r["date"] = r["date"].isoformat()
        if isinstance(r.get("extra_json"), dict):
            r["extra_json"] = json.dumps(r["extra_json"])

    url = f"{REST_URL}/raw_market_data"
    # PostgREST upsert: Prefer: resolution=merge-duplicates
    # On conflict (date, ticker, source, revision_num) → update
    resp = requests.post(url, headers=HEADERS, json=rows, timeout=30)

    if resp.status_code in (200, 201):
        log.info(f"Upserted {len(rows)} rows into raw_market_data")
        return len(rows)
    else:
        log.error(f"Upsert failed: {resp.status_code} {resp.text[:500]}")
        raise RuntimeError(f"Upsert failed: {resp.status_code} {resp.text[:300]}")


def create_etl_run(source_id: str) -> int:
    """Create a new etl_runs entry, return run_id."""
    url = f"{REST_URL}/etl_runs"
    headers = {**HEADERS, "Prefer": "return=representation"}
    payload = {"source_id": source_id, "status": "RUNNING"}
    resp = requests.post(url, headers=headers, json=payload, timeout=10)
    if resp.status_code in (200, 201):
        run = resp.json()
        run_id = run[0]["run_id"] if isinstance(run, list) else run["run_id"]
        log.info(f"Created etl_run {run_id} for source={source_id}")
        return run_id
    else:
        log.error(f"Failed to create etl_run: {resp.status_code} {resp.text[:300]}")
        raise RuntimeError(f"etl_run creation failed: {resp.text[:300]}")


def finish_etl_run(run_id: int, status: str, rows_loaded: int = 0,
                   rows_skipped: int = 0, error_message: str = None):
    """Update etl_runs with final status."""
    url = f"{REST_URL}/etl_runs?run_id=eq.{run_id}"
    payload = {
        "status": status,
        "rows_loaded": rows_loaded,
        "rows_skipped": rows_skipped,
        "finished_at": datetime.now().isoformat(),
    }
    if error_message:
        payload["error_message"] = error_message[:2000]

    resp = requests.patch(url, headers=HEADERS, json=payload, timeout=10)
    if resp.status_code in (200, 204):
        log.info(f"etl_run {run_id} → {status} ({rows_loaded} loaded, {rows_skipped} skipped)")
    else:
        log.warning(f"Failed to update etl_run {run_id}: {resp.status_code}")


def get_active_tickers(level: str = None) -> list[dict]:
    """Get active tickers from instrument_dict, optionally filtered by level."""
    url = f"{REST_URL}/instrument_dict?is_active=eq.true&select=ticker,asset_class,level,source_default"
    if level:
        url += f"&level=eq.{level}"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    if resp.status_code == 200:
        return resp.json()
    else:
        log.error(f"Failed to get tickers: {resp.status_code}")
        return []


def log_quality_issue(check_date: str, check_type: str, ticker: str,
                      severity: str, message: str):
    """Log a data quality issue."""
    url = f"{REST_URL}/data_quality_log"
    payload = {
        "check_date": check_date,
        "check_type": check_type,
        "ticker": ticker,
        "severity": severity,
        "message": message[:1000],
    }
    resp = requests.post(url, headers=HEADERS, json=payload, timeout=10)
    if resp.status_code not in (200, 201):
        log.warning(f"Quality log failed: {resp.status_code}")
