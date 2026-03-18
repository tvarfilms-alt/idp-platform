"""
IDP Compute L1 -- Macro Regime (Monthly)

Source of truth: IDP_Level1_MacroRegime_v5.xlsx

Pipeline:
  1. Read monthly macro data from raw_market_data (PMI, CPI, KS, IMOEX, RGBI, BCOM, Urals)
  2. Compute Growth axis: growth_base -> commodity_score -> growth_v5
  3. Compute Monetary axis: monet_base -> ks_momentum -> monet_v5
  4. Determine regime from 3x3 matrix + stress override
  5. Map regime -> risk_cap
  6. Write to l1_regime table

Trigger: 1st of each month, after all L1 indicators are loaded.
"""
import json
from datetime import date, datetime
from db_helpers import (
    get_raw_range, get_calc_version, rest_upsert, rest_get,
    log, first_of_month, months_ago
)

# ---- Tickers for L1 indicators ----
L1_TICKERS = ["PMI_MANUF", "CPI_MOM", "CPI_YOY", "KS_RATE", "IMOEX", "RGBI", "BCOM", "URALS"]

# ---- 3x3 Regime Matrix ----
# Rows: Growth (low=0, mid=1, high=2), Cols: Monetary (tight=0, neutral=1, easy=2)
REGIME_MATRIX = [
    ["Recession",    "Stagnation",  "Recovery"],     # growth low
    ["Slowdown",     "Neutral",     "Reflation"],    # growth mid
    ["Overheating",  "Expansion",   "Boom"],          # growth high
]

# Regime -> risk_cap mapping
RISK_CAP = {
    "Recession":   "20%",
    "Stagnation":  "40%",
    "Recovery":    "60%",
    "Slowdown":    "40%",
    "Neutral":     "60%",
    "Reflation":   "80%",
    "Overheating": "60%",
    "Expansion":   "80%",
    "Boom":        "100%",
    "Stress":      "10%",
}


def _get_indicator(data: dict, ticker: str, default=None):
    """Get latest value for a ticker from grouped data."""
    values = data.get(ticker, [])
    if not values:
        return default
    return values[-1]["close_price"]


def _get_extra(data: dict, ticker: str, field: str, default=None):
    """Get a field from extra_json for a ticker."""
    values = data.get(ticker, [])
    if not values:
        return default
    extra = values[-1].get("extra_json")
    if isinstance(extra, str):
        extra = json.loads(extra)
    if isinstance(extra, dict):
        return extra.get(field, default)
    return default


def _classify_score(value: float, lo: float, hi: float) -> int:
    """Classify into 0 (low), 1 (mid), 2 (high)."""
    if value is None:
        return 1
    if value <= lo:
        return 0
    if value >= hi:
        return 2
    return 1


def _commodity_score(bcom_3m: float, urals_3m: float) -> tuple:
    """Score commodity momentum: -1, 0, or +1 each."""
    def score(ret):
        if ret is None:
            return 0
        if ret > 0.05:
            return 1
        if ret < -0.05:
            return -1
        return 0
    return score(bcom_3m), score(urals_3m)


def compute_l1(target_date: str = None):
    """Main L1 compute function."""
    # Determine target month
    if target_date:
        td = date.fromisoformat(target_date)
    else:
        td = date.today()
    month = td.replace(day=1)
    month_str = month.isoformat()

    log(f"L1 Compute: target month = {month_str}")

    # Get calc version
    try:
        cv = get_calc_version("L1")
        version_id = cv["version_id"]
        config = cv.get("config_json", {})
        if isinstance(config, str):
            config = json.loads(config)
    except Exception as e:
        log(f"Warning: no calc_version for L1, using defaults: {e}")
        version_id = 1
        config = {}

    # Fetch data: last 6 months for momentum calculations
    date_from = months_ago(6, month)
    date_to = month_str

    log(f"Fetching data from {date_from} to {date_to}")
    raw = get_raw_range(L1_TICKERS, date_from, date_to)

    # Group by ticker
    by_ticker = {}
    for row in raw:
        t = row["ticker"]
        by_ticker.setdefault(t, []).append(row)

    # Extract current month indicators
    pmi = _get_indicator(by_ticker, "PMI_MANUF")
    cpi_mom = _get_indicator(by_ticker, "CPI_MOM")
    cpi_yoy = _get_indicator(by_ticker, "CPI_YOY")
    ks = _get_indicator(by_ticker, "KS_RATE")
    imoex = _get_indicator(by_ticker, "IMOEX")
    rgbi = _get_indicator(by_ticker, "RGBI")
    bcom = _get_indicator(by_ticker, "BCOM")
    urals = _get_indicator(by_ticker, "URALS")

    log(f"Indicators: PMI={pmi}, CPI_MOM={cpi_mom}, CPI_YOY={cpi_yoy}, KS={ks}")
    log(f"  IMOEX={imoex}, RGBI={rgbi}, BCOM={bcom}, URALS={urals}")

    # ---- Growth axis ----
    # growth_base: PMI deviation from 50 (expansion threshold)
    pmi_val = float(pmi) if pmi is not None else 50.0
    growth_base = (pmi_val - 50.0) / 10.0  # normalized to ~[-1, 1]

    # Commodity momentum (3-month returns)
    bcom_vals = [float(r["close_price"]) for r in by_ticker.get("BCOM", []) if r["close_price"] is not None]
    urals_vals = [float(r["close_price"]) for r in by_ticker.get("URALS", []) if r["close_price"] is not None]

    bcom_3m = (bcom_vals[-1] / bcom_vals[0] - 1.0) if len(bcom_vals) >= 2 else None
    urals_3m = (urals_vals[-1] / urals_vals[0] - 1.0) if len(urals_vals) >= 2 else None

    bcom_sc, urals_sc = _commodity_score(bcom_3m, urals_3m)

    # growth_v5: base + commodity adjustment
    commodity_adj = (bcom_sc + urals_sc) * 0.15
    growth_v5 = growth_base + commodity_adj

    # ---- Monetary axis ----
    # monet_base: real rate proxy (KS - CPI_YOY)
    ks_val = float(ks) if ks is not None else 16.0
    cpi_yoy_val = float(cpi_yoy) if cpi_yoy is not None else 8.0
    monet_base = (ks_val - cpi_yoy_val) / 10.0  # normalized

    # KS momentum: compare current KS to 3-month ago
    ks_vals = [float(r["close_price"]) for r in by_ticker.get("KS_RATE", []) if r["close_price"] is not None]
    if len(ks_vals) >= 2:
        ks_momentum = (ks_vals[-1] - ks_vals[0]) / 100.0  # delta in pp normalized
    else:
        ks_momentum = 0.0

    monet_v5 = monet_base + ks_momentum

    # ---- Regime classification ----
    # Growth: low (<-0.3), mid, high (>0.3)
    growth_thresholds = config.get("growth_thresholds", [-0.3, 0.3])
    monet_thresholds = config.get("monet_thresholds", [-0.3, 0.3])

    g_idx = _classify_score(growth_v5, growth_thresholds[0], growth_thresholds[1])
    m_idx = _classify_score(monet_v5, monet_thresholds[0], monet_thresholds[1])

    regime = REGIME_MATRIX[g_idx][m_idx]

    # Stress override: if IMOEX drawdown > 15% or RGBI drawdown > 10%
    imoex_vals = [float(r["close_price"]) for r in by_ticker.get("IMOEX", []) if r["close_price"] is not None]
    rgbi_vals = [float(r["close_price"]) for r in by_ticker.get("RGBI", []) if r["close_price"] is not None]

    stress = False
    if len(imoex_vals) >= 2:
        imoex_peak = max(imoex_vals)
        imoex_dd = (imoex_vals[-1] / imoex_peak - 1.0)
        if imoex_dd < -0.15:
            stress = True
            log(f"Stress override: IMOEX drawdown = {imoex_dd:.1%}")

    if not stress and len(rgbi_vals) >= 2:
        rgbi_peak = max(rgbi_vals)
        rgbi_dd = (rgbi_vals[-1] / rgbi_peak - 1.0)
        if rgbi_dd < -0.10:
            stress = True
            log(f"Stress override: RGBI drawdown = {rgbi_dd:.1%}")

    if stress:
        regime = "Stress"

    risk_cap = RISK_CAP.get(regime, "60%")

    log(f"Result: growth_v5={growth_v5:.3f}, monet_v5={monet_v5:.3f}")
    log(f"  Regime={regime}, Risk Cap={risk_cap}")

    # ---- Write to l1_regime ----
    row = {
        "month": month_str,
        "calc_version_id": version_id,
        "pmi": float(pmi) if pmi is not None else None,
        "cpi_mom": float(cpi_mom) if cpi_mom is not None else None,
        "cpi_yoy": float(cpi_yoy) if cpi_yoy is not None else None,
        "ks": float(ks) if ks is not None else None,
        "imoex": float(imoex) if imoex is not None else None,
        "rgbi": float(rgbi) if rgbi is not None else None,
        "bcom": float(bcom) if bcom is not None else None,
        "urals": float(urals) if urals is not None else None,
        "growth_base": round(growth_base, 4),
        "monet_base": round(monet_base, 4),
        "bcom_score": bcom_sc,
        "urals_score": urals_sc,
        "growth_v5": round(growth_v5, 4),
        "monet_v5": round(monet_v5, 4),
        "regime": regime,
        "risk_cap": risk_cap,
        "computed_at": datetime.utcnow().isoformat() + "Z",
    }

    n = rest_upsert("l1_regime", [row])
    log(f"L1: upserted {n} row(s) to l1_regime")
    return row
