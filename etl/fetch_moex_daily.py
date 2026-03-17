#!/usr/bin/env python3
"""
IDP ETL — fetch_moex_daily.py
Загружает ежедневные данные с MOEX ISS API:
  - 50 акций (TQBR): цена, объём, ohlc
  - 4 индекса (IMOEX, RGBI, RVI, MCFTR): значение
  - RGBITR, BRENT: значения
  - Дивиденды (по всем акциям)
  - Fундаментальные мультипликаторы (из Finance Marker API, если токен задан)

Расписание: ежедневно 19:30 MSK (после закрытия торгов в 18:50)
"""
import json
import logging
import sys
import time
from datetime import date, timedelta

import requests

from config import MOEX_BASE, MOEX_STOCKS_URL, MOEX_INDEX_URL, MOEX_DELAY_SEC
from db import (
    create_etl_run, finish_etl_run, upsert_raw_market_data,
    get_active_tickers, log_quality_issue,
)

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","module":"%(name)s","msg":"%(message)s"}',
)
log = logging.getLogger("idp.moex")

TODAY = date.today().isoformat()


# ── 1. Fetch stocks from TQBR ──────────────────────────────────────
def fetch_stocks(tickers: list[str]) -> list[dict]:
    """Fetch all TQBR stocks in one request, filter by our tickers."""
    log.info(f"Fetching TQBR stocks for {len(tickers)} tickers...")
    url = f"{MOEX_STOCKS_URL}?iss.meta=off&iss.json=extended&securities.columns=SECID,PREVPRICE,LAST,OPEN,HIGH,LOW,VOLTODAY,VALTODAY"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    data = resp.json()
    # ISS returns [metadata, data_array]
    securities = data[1]["securities"] if len(data) > 1 else []

    ticker_set = set(tickers)
    rows = []
    found = set()

    for sec in securities:
        secid = sec.get("SECID")
        if secid not in ticker_set:
            continue

        price = sec.get("LAST") or sec.get("PREVPRICE")
        if price is None or price == 0:
            continue

        found.add(secid)
        rows.append({
            "date": TODAY,
            "ticker": secid,
            "source": "MOEX",
            "close_price": float(price),
            "volume": int(sec.get("VOLTODAY") or 0),
            "revision_num": 1,
            "extra_json": json.dumps({
                "open": sec.get("OPEN"),
                "high": sec.get("HIGH"),
                "low": sec.get("LOW"),
                "value_traded": sec.get("VALTODAY"),
            }),
        })

    missing = ticker_set - found
    if missing:
        log.warning(f"Missing stocks: {sorted(missing)}")
        for t in missing:
            log_quality_issue(TODAY, "MISSING", t, "WARN",
                              f"Ticker {t} not found in MOEX TQBR response")

    log.info(f"Fetched {len(rows)} stocks ({len(missing)} missing)")
    return rows


# ── 2. Fetch indexes ────────────────────────────────────────────────
def fetch_indexes(tickers: list[str]) -> list[dict]:
    """Fetch index values one by one from MOEX ISS."""
    rows = []
    for ticker in tickers:
        time.sleep(MOEX_DELAY_SEC)
        url = f"{MOEX_INDEX_URL}/{ticker}.json?iss.meta=off&iss.json=extended&securities.columns=SECID,CURRENTVALUE,VOLUME"
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            securities = data[1]["securities"] if len(data) > 1 else []
            if securities:
                sec = securities[0]
                val = sec.get("CURRENTVALUE")
                if val and val > 0:
                    rows.append({
                        "date": TODAY,
                        "ticker": ticker,
                        "source": "MOEX",
                        "close_price": float(val),
                        "volume": int(sec.get("VOLUME") or 0),
                        "revision_num": 1,
                    })
                    log.info(f"Index {ticker} = {val}")
                else:
                    log.warning(f"Index {ticker}: no value")
                    log_quality_issue(TODAY, "MISSING", ticker, "WARN",
                                      f"Index {ticker} has no CURRENTVALUE")
            else:
                log.warning(f"Index {ticker}: empty response")
        except Exception as e:
            log.error(f"Index {ticker} error: {e}")
            log_quality_issue(TODAY, "PARSE", ticker, "ERROR", str(e)[:500])

    log.info(f"Fetched {len(rows)} indexes")
    return rows


# ── 3. Fetch dividends ─────────────────────────────────────────────
def fetch_dividends(tickers: list[str]) -> dict:
    """Fetch last dividend info for all tickers. Returns {ticker: {last_div, last_div_date}}."""
    dividends = {}
    for i, ticker in enumerate(tickers):
        if i > 0 and i % 10 == 0:
            time.sleep(MOEX_DELAY_SEC * 2)
        time.sleep(MOEX_DELAY_SEC)

        url = f"{MOEX_BASE}/securities/{ticker}/dividends.json?iss.meta=off"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            rows = data.get("dividends", {}).get("data", [])
            cols = data.get("dividends", {}).get("columns", [])

            if rows:
                last = rows[-1]
                col_map = {c: idx for idx, c in enumerate(cols)}
                div_val = last[col_map.get("value", 0)]
                div_date = last[col_map.get("registryclosedate", 1)]
                if div_val and div_val > 0:
                    dividends[ticker] = {
                        "last_div": float(div_val),
                        "last_div_date": str(div_date),
                    }
        except Exception as e:
            log.warning(f"Dividend {ticker}: {e}")

    log.info(f"Fetched dividends for {len(dividends)} tickers")
    return dividends


# ── 4. Main ─────────────────────────────────────────────────────────
def main():
    log.info("=== fetch_moex_daily START ===")
    run_id = create_etl_run("MOEX")
    total_loaded = 0
    total_skipped = 0

    try:
        # Get ticker lists from DB
        all_instruments = get_active_tickers()
        equity_tickers = [i["ticker"] for i in all_instruments
                          if i["asset_class"] == "EQUITY"]
        index_tickers = [i["ticker"] for i in all_instruments
                         if i["asset_class"] == "INDEX" and i["source_default"] == "MOEX"]

        # 1. Stocks
        stock_rows = fetch_stocks(equity_tickers)

        # 2. Indexes
        index_rows = fetch_indexes(index_tickers)

        # 3. Dividends → merge into stock rows extra_json
        dividends = fetch_dividends(equity_tickers)
        for row in stock_rows:
            ticker = row["ticker"]
            if ticker in dividends:
                extra = json.loads(row.get("extra_json") or "{}")
                extra.update(dividends[ticker])
                row["extra_json"] = json.dumps(extra)

        # 4. Add etl_run_id
        all_rows = stock_rows + index_rows
        for row in all_rows:
            row["etl_run_id"] = run_id

        # 5. Upsert to Supabase
        if all_rows:
            # Batch in groups of 50
            for i in range(0, len(all_rows), 50):
                batch = all_rows[i:i+50]
                upsert_raw_market_data(batch)
                total_loaded += len(batch)

        # Determine status
        expected = len(equity_tickers) + len(index_tickers)
        if total_loaded == 0:
            status = "FAILED"
        elif total_loaded < expected * 0.9:
            status = "PARTIAL"
            total_skipped = expected - total_loaded
        else:
            status = "SUCCESS"

        finish_etl_run(run_id, status, total_loaded, total_skipped)
        log.info(f"=== fetch_moex_daily DONE: {status} ({total_loaded} rows) ===")

    except Exception as e:
        log.error(f"Fatal error: {e}", exc_info=True)
        finish_etl_run(run_id, "FAILED", total_loaded, error_message=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
