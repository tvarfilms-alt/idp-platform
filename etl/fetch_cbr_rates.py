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

        # Parse HTML table: Date | Rate
        # Find last row with rate value
        pattern = r'(\d{2}\.\d{2}\.\d{4})\s*</td>\s*<td[^>]*>\s*([\d,\.]+)'
        matches = re.findall(pattern, html)

        if matches:
            # Last entry is the current rate
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
    """Fetch RUONIA rate from CBR.
    CBR RUONIA page uses a TRANSPOSED table:
      Row 0: "Дата ставки"            | 13.03.2026 | 16.03.2026
      Row 1: "Ставка RUONIA, % годовых" | 14,85      | 14,81
    We extract dates from row 0 and rates from row 1, take the last column.
    """
    url = "https://www.cbr.ru/hd_base/ruonia/"
    try:
        resp = requests.get(url, timeout=15,
                            headers={"User-Agent": "IDP-ETL/1.0"})
        resp.raise_for_status()
        html = resp.text

        # Extract all dates (DD.MM.YYYY) from the page
        dates = re.findall(r'(\d{2}\.\d{2}\.\d{4})', html)

        # Find the RUONIA rate row: look for "Ставка RUONIA" then capture numbers
        # The rate row has format: <td>Ставка RUONIA...</td><td>14,85</td><td>14,81</td>
        rate_match = re.search(
            r'Ставка\s+RUONIA[^<]*</td>\s*'
            r'(?:<td[^>]*>\s*(-?[\d]+[,.][\d]{1,4})\s*</td>\s*)*',
            html, re.DOTALL
        )

        # Alternative: extract all numbers from the row containing "Ставка RUONIA"
        # Find the <tr> that contains "Ставка RUONIA" and get all <td> values
        tr_match = re.search(
            r'<tr[^>]*>\s*<td[^>]*>[^<]*Ставка\s+RUONIA[^<]*</td>(.*?)</tr>',
            html, re.DOTALL | re.IGNORECASE
        )

        if tr_match:
            rate_cells = re.findall(r'<td[^>]*>\s*(-?[\d]+[,.][\d]{1,4})\s*</td>', tr_match.group(1))
            if rate_cells and dates:
                # Take the last rate (most recent date)
                rate_str = rate_cells[-1]
                date_str = dates[-1] if len(dates) >= len(rate_cells) else dates[0]
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
    """Fetch CPI YoY from CBR inflation page.
    CBR inflation table has 4 columns:
      Дата (MM.YYYY) | Ключевая ставка, % | Инфляция, % г/г | Цель, %
    Example row: 02.2026 | 15,50 | 5,91 | 4,00
    We need the 3rd column (Инфляция, % г/г) from the first data row.
    """
    url = "https://www.cbr.ru/hd_base/infl/"
    try:
        resp = requests.get(url, timeout=15,
                            headers={"User-Agent": "IDP-ETL/1.0"})
        resp.raise_for_status()
        html = resp.text

        # Date format is MM.YYYY (not DD.MM.YYYY!)
        # Pattern: <td>MM.YYYY</td><td>key_rate</td><td>CPI</td><td>target</td>
        pattern = (
            r'<td[^>]*>\s*(\d{2}\.\d{4})\s*</td>\s*'   # date MM.YYYY
            r'<td[^>]*>\s*[\d,\.]+\s*</td>\s*'           # key rate (skip)
            r'<td[^>]*>\s*([\d,\.]+)\s*</td>'             # CPI YoY (capture)
        )
        matches = re.findall(pattern, html, re.DOTALL)

        # Filter: CPI should be a reasonable number (0-30%)
        valid = []
        for d, v in matches:
            try:
                val = float(v.replace(",", "."))
                if 0 < val < 30:
                    valid.append((d, v))
            except ValueError:
                pass

        if valid:
            # First match is the most recent (table is sorted desc)
            date_str, cpi_str = valid[0]
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

        # Fetch all CBR indicators
        all_rows.extend(fetch_usd_rub())
        all_rows.extend(fetch_key_rate())
        all_rows.extend(fetch_ruonia())
        all_rows.extend(fetch_cpi())

        # Add etl_run_id
        for row in all_rows:
            row["etl_run_id"] = run_id

        # Upsert
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
