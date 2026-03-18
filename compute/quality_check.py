"""
IDP Data Quality Checks + Telegram Alerts

Per spec section 6: checks at ETL load time and before compute.
Logs issues to data_quality_log table and sends Telegram alerts.

Checks:
  1. MISSING — required data not present for today
  2. STALE — last update > N days
  3. OUTLIER — Z-score > 4 for numeric indicators
  4. RANGE — value outside valid_min/valid_max from instrument_dict
  
  ETE�OILATE — same (date, ticker, source) appears multiple times

Usage:
  python quality_check.py              # Run all checks
  python quality_check.py --no-alert   # Run without sending Telegram
"""
import sys
import os
import json
import statistics
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_helpers import rest_get, rest_upsert, get_instruments, log

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

STALE_WARN_DAYS = 2
STALE_ERROR_DAYS = 5
ZSCORE_OUTLIER = 4.0

