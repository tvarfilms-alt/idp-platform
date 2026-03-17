#!/usr/bin/env python3
"""
IDP ETL — fetch_cbr_rates.py
Загружает данные ЦБ РФ:
  - Ключевая ставка (KEY_RATE)
  - RUONIA
  - CPI YoY (CPI_YOY)
  - USD/RUB курс (USD_RUB)

Источники:
  - cbr.ru XML daily (курсы валют)
  - cbr.ru/hd_base/KeyRate/ (ключевая ставка)
  - cbr.ru/hd_base/ruonia/ (RUONIA)
  - cbr.ru/hd_base/infl/ (CPI)

Расписание: ежедневно 20:00 MSK
"""
import json
import logging
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime

import requests

from db import (
    create_etl_run, finish_etl_run, upsert_raw_market_data,
    log_quality_issue,
)

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","module":"%(name)s","msg":"%(message)s"}',
)
log = logging.getLogger("idp.cbr")

TODAY = date.today().isoformat()


# ── 1. USD/RUB from CBR XML daily ──────────────────────────────────
def fetch_usd_rub() -> list[dict]:
    """Fetch USD/RUB rate from CBR daily XML feed."""
    url = "https://www.cbr.ru/scripts/XML_daily.asp"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        for valute in root.findall("Valute"):
            char_code = valute.find("CharCode")
            if char_code is not None and char_code.text == "USD":
                vunit = valute.find("VunitRate") or valute.find("Value")
                if vunit is not None:
                    rate = float(vunit.text.replace(",", "."))
                    log.info(f"USD/RUB = {rate}")
                    return [{
                        "date": TODAY,
                        "ticker": "USD_RUB",
                        "source": "CBR",
                        "close_price": rate,
                        "revision_num": 1,
                        "extra_json": json.dumps({}),
                    }]

        log.warning("USD not found in CBR XML")
        return []
    except Exception as e:
        log.error(f"USD/RUB fetch error: {e}")
        log_quality_issue(TODAY, "PARSE", "USD_RUB", "ERROR", str(e)[:500])
        return []


# ── 2. Key Rate from CBR ───────────────────────────────────────────
def fetch_key_rate() -> list[dict]:
    """Fetch current key rate from CBR HTML page."""
    url = "https://www.cbr.ru/hd_base/KeyRate/"
    try:
        resp = requests.get(url, timeout=15,
                            headers={"User-Agent": "IDP-ETL/1.0"})
        resp.raise_for_status()
        html = resp.text

        pattern = r'(\d{2}\.\d{2}\.\d{4})\s*</td>\s*<td[^>]*>\s*([\d,\.]+)'
        matches = re.findall(pattern, html)

        if matches:
            date_str, rate_str = matches[-1]
            rate = float(rate_str.replace(",", "."))
            log.info(f"KEY_RATE = {rate}% (from {date_str})")
            return [{
                "date": TODAY,
                "ticker": "KEY_RATE",
                "source": "CBR",
                "close_price": rate,
                "revision_num": 1,
                "extra_json": json.dumps({"effective_date": date_str}),
            }]

        log.warning("Key rate not found in HTML")
        return []
    except Exception as e:
        log.error(f"Key rate fetch error: {e}")
        log_quality_issue(TODAY, "PARSE", "KEY_RATE", "ERROR", str(e)[:500])
        return []


# ── 3. RUONIA ──────────────────────────────────────────────────────
def fetch_ruonia() -> list[dict]:
    """Fetch RUONIA rate from CBR."""
    url = "https://www.cbr.ru/hd_base/ruonia/"
    try:
        resp = requests.get(url, timeout=15,
                            headers={"User-Agent": "IDP-ETL/1.0"})
        resp.raise_for_status()

        pattern = r'(\d{2}\.\d{2}\.\d{4})\s*</td>\s*<td[^>]*>\s*(-?[\d]+[,.][\d]{1,4})\s*</td>'
        matches = re.findall(pattern, resp.text)

        valid = [(d, r) for d, r in matches if len(r) < 10 and r.count('.') <= 1]

        if valid:
            date_str, rate_str = valid[-1]
            rate = float(rate_str.replace(",", "."))
            log.info(f"RUONIA = {rate}% (from {date_str})")
            return [{
                "date": TODAY,
                "ticker": "RUONIA",
                "source": "CBR",
                "close_price": rate,
                "revision_num": 1,
                "extra_json": json.dumps({"value_date": date_str}),
            }]

        log.warning("RUONIA not found in HTML")
        return []
    except Exception as e:
        log.error(f"RUONIA fetch error: {e}")
        log_quality_issue(TODAY, "PARSE", "RUONIA", "ERROR", str(e)[:500])
        return []


# ── 4. CPI YoY ────────────────────────────────────────────────────
def fetch_cpi() -> list[dict]:
    """Fetch CPI YoY from CBR inflation page."""
    url = "https://www.cbr.ru/hd_base/infl/"
    try:
        resp = requests.get(url, timeout=15,
                            headers={"User-Agent": "IDP-ETL/1.0"})
        resp.raise_for_status()
        html = resp.text

        patterns = [
            r'(\d{2}\.\d{2}\.\d{4})\s*</td>\s*<td[^>]*>[^<]*</td>\s*<td[^>]*>\s*([\d,\.]+)',
            r'(\d{2}\.\d{2}\.\d{4})\s*</td>\s*<td[^>]*>\s*([\d,\.]+)',
            r'(\d{2}\.\d{2}\.\d{4})\s*</td>\s*<td[^>]*>\s*[\d,\.]+\s*</td>\s*<td[^>]*>\s*([\d,\.]+)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, html)
            valid = []
            for d, v in matches:
                try:
                    val = float(v.replace(",", "."))
                    if 0 < val < 30:
                        valid.append((d, v))
                except ValueError:
                    pass

            if valid:
                date_str, cpi_str = valid[-1]
                cpi = float(cpi_str.replace(",", "."))
                log.info(f"CPI_YOY = {cpi}% (from {date_str})")
                return [{
                    "date": TODAY,
                    "ticker": "CPI_YOY",
                    "source": "CBR",
                    "close_price": cpi,
                    "revision_num": 1,
                    "extra_json": json.dumps({"report_date": date_str}),
                }]

        log.warning("CPI not found in HTML")
        return []
    except Exception as e:
        log.error(f"CPI fetch error: {e}")
        log_quality_issue(TODAY, "PARSE", "CPI_YOY", "ERROR", str(e)[:500])
        return []


# ── 5. Main ────────────────────────────────────────────────────────
def main():
    log.info("=== fetch_cbr_rates START ===")
    run_id = create_etl_run("CBR")
    total_loaded = 0

    try:
        all_rows = []

        all_rows.extend(fetch_usd_rub())
        all_rows.extend(fetch_key_rate())
        all_rows.extend(fetch_ruonia())
        all_rows.extend(fetch_cpi())

        for row in all_rows:
            row["etl_run_id"] = run_id

        if all_rows:
            upsert_raw_market_data(all_rows)
            total_loaded = len(all_rows)

        status = "SUCCESS" if total_loaded >= 3 else ("PARTIAL" if total_loaded > 0 else "FAILED")
        finish_etl_run(run_id, status, total_loaded)
        log.info(f"=== fetch_cbr_rates DONE: {status} ({total_loaded} rows) ===")

    except Exception as e:
        log.error(f"Fatal error: {e}", exc_info=True)
        finish_etl_run(run_id, "FAILED", total_loaded, error_message=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
