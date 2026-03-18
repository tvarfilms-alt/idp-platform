#!/usr/bin/env python3
"""
IDP ETL — fetch_fm_fundamentals.py
Загружает фундаментальные мультипликаторы из Finance Marker API v2:
  - P/E, P/BV, P/S, EV/EBITDA, ROE, ROA, ROIC, Debt Ratio, Net Margin, Div Yield

ВАЖНО: Используем ТОЛЬКО запись с active=true (период YTM — trailing 12 months),
а не первую запись в массиве ratios (которая может быть annual).

Расписание: понедельник 08:30 MSK (еженедельно, совмещено с L3 compute)
"""
import json
import logging
import sys
import time
from datetime import date

import requests

from config import FM_API_TOKEN, FM_DELAY_SEC
from db import (
    create_etl_run, finish_etl_run,
    get_active_tickers, log_quality_issue,
)
from config import REST_URL, HEADERS

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","module":"%(name)s","msg":"%(message)s"}',
)
log = logging.getLogger("idp.fm")

TODAY = date.today().isoformat()
FM_BASE = "https://financemarker.ru/api/fm/v2"


def fetch_ticker_ratios(ticker: str) -> dict | None:
    """
    Fetch ratios for a single ticker from Finance Marker API.
    Returns dict with fundamental metrics or None on failure.
    CRITICAL: Uses ONLY the entry with active=true (YTM period).
    """
    url = f"{FM_BASE}/stocks/MOEX:{ticker}?api_token={FM_API_TOKEN}&include=ratios,dividends"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 404:
            log.warning(f"{ticker}: not found in FM")
            return None
        resp.raise_for_status()
        data = resp.json()

        ratios_list = data.get("ratios", [])
        if not ratios_list:
            log.warning(f"{ticker}: no ratios data")
            return None

        active_entry = None
        for entry in ratios_list:
            if entry.get("active") is True:
                active_entry = entry
                break

        if active_entry is None:
            for entry in ratios_list:
                if entry.get("period") == "YTM":
                    active_entry = entry
                    break

        if active_entry is None:
            log.warning(f"{ticker}: no active/YTM ratios entry, skipping")
            log_quality_issue(TODAY, "MISSING", ticker, "WARN",
                              "FM API: no active=true ratios entry found")
            return None

        result = {}
        field_map = {
            "pe": "pe", "pbv": "pbv", "ps": "ps",
            "evebitda": "evebitda", "ev_ebit": "ev_ebit",
            "debt_ratio": "debt_ratio", "debt_equity": "debt_equity",
            "roe": "roe", "roa": "roa", "roic": "roic",
            "net_margin": "net_margin", "ebitda_margin": "ebitda_margin",
            "gross_margin": "gross_margin", "operation_margin": "operation_margin",
            "pfcf": "pfcf", "pcf": "pcf", "dpr": "dpr",
            "capex_revenue": "capex_revenue", "capital": "capital",
        }

        for fm_key, our_key in field_map.items():
            val = active_entry.get(fm_key)
            if val is not None:
                try:
                    result[our_key] = round(float(val), 2)
                except (ValueError, TypeError):
                    pass

        if result:
            log.info(f"{ticker}: PE={result.get('pe')}, PBV={result.get('pbv')}, ROE={result.get('roe')}")
        return result if result else None

    except Exception as e:
        log.error(f"{ticker}: FM API error: {e}")
        log_quality_issue(TODAY, "PARSE", ticker, "ERROR", f"FM API: {e}"[:500])
        return None


def main():
    if not FM_API_TOKEN:
        log.error("FM_API_TOKEN not set, skipping fundamental data fetch")
        sys.exit(0)

    log.info("=== fetch_fm_fundamentals START ===")
    run_id = create_etl_run("MOEX")
    total_loaded = 0
    total_skipped = 0

    try:
        instruments = get_active_tickers("L3")
        tickers = [i["ticker"] for i in instruments]
        log.info(f"Processing {len(tickers)} L3 tickers")

        for i, ticker in enumerate(tickers):
            if i > 0:
                time.sleep(FM_DELAY_SEC)

            if i > 0 and i % 10 == 0:
                time.sleep(1.0)
                log.info(f"Progress: {i}/{len(tickers)}")

            ratios = fetch_ticker_ratios(ticker)
            if ratios:
                merge_url = f"{REST_URL}/raw_market_data?date=eq.{TODAY}&ticker=eq.{ticker}&source=eq.MOEX&revision_num=eq.1"
                patch_headers = {**HEADERS, "Prefer": "return=minimal"}
                get_resp = requests.get(merge_url, headers=HEADERS, timeout=10)
                if get_resp.status_code == 200 and get_resp.json():
                    existing = get_resp.json()[0]
                    old_extra = existing.get("extra_json") or {}
                    if isinstance(old_extra, str):
                        old_extra = json.loads(old_extra)
                    old_extra.update(ratios)
                    patch_payload = {"extra_json": json.dumps(old_extra)}
                    patch_resp = requests.patch(merge_url, headers=patch_headers, json=patch_payload, timeout=10)
                    if patch_resp.status_code in (200, 204):
                        total_loaded += 1
                    else:
                        log.warning(f"{ticker}: PATCH failed {patch_resp.status_code}")
                        total_skipped += 1
                else:
                    log.warning(f"{ticker}: no MOEX row for {TODAY}, skipping FM merge")
                    total_skipped += 1
            else:
                total_skipped += 1

        if total_loaded == 0:
            status = "FAILED"
        elif total_loaded < len(tickers) * 0.8:
            status = "PARTIAL"
        else:
            status = "SUCCESS"

        finish_etl_run(run_id, status, total_loaded, total_skipped)
        log.info(f"=== fetch_fm_fundamentals DONE: {status} ({total_loaded}/{len(tickers)}) ===")

    except Exception as e:
        log.error(f"Fatal error: {e}", exc_info=True)
        finish_etl_run(run_id, "FAILED", total_loaded, error_message=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
