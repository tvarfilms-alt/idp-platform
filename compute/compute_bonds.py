"""
IDP Compute Bonds — Bond Strategy (Daily)

Source of truth: IDP_Level3_CrossSection.xlsx (Bond Allocation sheet)

Pipeline:
  1. Read bond indicators: RGBI, GBI_YTM, CBI_YTM, KEY_RATE, RUONIA, CPI_YOY
  2. Compute g_spread (CBI - GBI), real_yield (GBI - CPI)
  3. Get current L1 regime
  4. Map regime → bond strategy (duration, credit, coupon, quality)
  5. Compute bond allocation %
  6. Write to bonds_daily

Trigger: Daily 21:15 MSK, after compute_l2 (needs L1 regime + L2 market data).
"""
import sys
import json
from datetime import date
from db_helpers import (
    get_raw_range, get_calc_version, rest_upsert, rest_get,
    log, today_str
)


def get_current_l1_regime() -> tuple[str, str]:
    """Get the latest L1 regime and risk_cap."""
    rows = rest_get("l1_regime", {
        "select": "regime,risk_cap",
        "order": "month.desc",
        "limit": "1",
    })
    if rows:
        return rows[0]["regime"], rows[0]["risk_cap"]
    return "TRANSITION", "60%"  # safe default


def compute_bonds(target_date: str = None):
    """Main bonds compute function."""
    if target_date is None:
        target_date = today_str()

    log(f"compute_bonds: target_date={target_date}")

    # Get config
    cv = get_calc_version("BONDS")
    version_id = cv["version_id"]
    cfg = cv["config_json"] if isinstance(cv["config_json"], dict) else json.loads(cv["config_json"])

    strategy_matrix = cfg.get("strategy_matrix", {})
    alloc_rules = cfg.get("alloc_rules", {"base_bond_alloc": 28, "equity_alloc_from_l1": True, "cash_min": 5})
    yield_targets = cfg.get("yield_targets", {"spread_over_key_rate": -2.0, "min_real_yield": 3.0})
    quality_thresholds = cfg.get("quality_thresholds", {})

    # Get current L1 regime
    l1_regime, l1_risk_cap = get_current_l1_regime()
    log(f"  L1 regime: {l1_regime} (risk_cap={l1_risk_cap})")

    # Fetch bond-related indicators
    d = date.fromisoformat(target_date)
    tickers = ["RGBI", "KEY_RATE", "RUONIA", "CPI_YOY", "GBI_YTM", "CBI_YTM"]
    data = get_raw_range(tickers, (d - __import__("datetime").timedelta(days=30)).isoformat(), target_date)
    log(f"  Fetched {len(data)} records")

    # Get latest values
    vals = {}
    for r in sorted(data, key=lambda x: x["date"], reverse=True):
        t = r["ticker"]
        if t not in vals:
            vals[t] = float(r["close_price"])

    rgbi = vals.get("RGBI")
    key_rate = vals.get("KEY_RATE")
    ruonia = vals.get("RUONIA")
    cpi_yoy = vals.get("CPI_YOY")
    gbi_ytm = vals.get("GBI_YTM")
    cbi_ytm = vals.get("CBI_YTM")

    # Compute derived metrics
    g_spread = None
    if cbi_ytm is not None and gbi_ytm is not None:
        g_spread = cbi_ytm - gbi_ytm

    real_yield = None
    if gbi_ytm is not None and cpi_yoy is not None:
        real_yield = gbi_ytm - cpi_yoy

    log(f"  RGBI={rgbi} KS={key_rate} RUONIA={ruonia} CPI={cpi_yoy}")
    log(f"  GBI_YTM={gbi_ytm} CBI_YTM={cbi_ytm} G-Spread={g_spread} Real_Yield={real_yield}")

    # Strategy from matrix
    strategy = strategy_matrix.get(l1_regime, {
        "duration": "Medium", "credit": "IG", "coupon": "Fixed", "quality": "Умеренно"
    })
    duration_target = strategy.get("duration", "Medium")
    credit_segment = strategy.get("credit", "IG")
    coupon_type = strategy.get("coupon", "Fixed")
    quality_label = strategy.get("quality", "Умеренно")

    # Target YTM
    target_ytm = None
    if key_rate is not None:
        target_ytm = key_rate + yield_targets.get("spread_over_key_rate", -2.0)
        min_real = yield_targets.get("min_real_yield", 3.0)
        if cpi_yoy is not None:
            min_ytm = cpi_yoy + min_real
            target_ytm = max(target_ytm, min_ytm)

    # Bond allocation
    base_alloc = alloc_rules.get("base_bond_alloc", 28)
    cash_min = alloc_rules.get("cash_min", 5)
    if alloc_rules.get("equity_alloc_from_l1"):
        # equity% comes from L1 risk_cap
        equity_pct = int(l1_risk_cap.replace("%", ""))
        bond_alloc = 100 - equity_pct - cash_min
        bond_alloc = max(bond_alloc, 0)
    else:
        bond_alloc = base_alloc

    log(f"  Strategy: duration={duration_target}, credit={credit_segment}, "
        f"coupon={coupon_type}, quality={quality_label}")
    log(f"  Target YTM={target_ytm}, Bond alloc={bond_alloc}%")

    # Write to bonds_daily
    row = {
        "date": target_date,
        "calc_version_id": version_id,
        "gbi_ytm": gbi_ytm,
        "cbi_ytm": cbi_ytm,
        "g_spread": round(g_spread, 4) if g_spread is not None else None,
        "key_rate": key_rate,
        "ruonia": ruonia,
        "cpi_yoy": cpi_yoy,
        "real_yield": round(real_yield, 4) if real_yield is not None else None,
        "rgbi_index": rgbi,
        "current_l1_regime": l1_regime,
        "duration_target": duration_target,
        "credit_segment": credit_segment,
        "coupon_type": coupon_type,
        "target_ytm": round(target_ytm, 2) if target_ytm is not None else None,
        "quality_label": quality_label,
        "bond_alloc_pct": bond_alloc,
    }
    rest_upsert("bonds_daily", [row])
    log(f"  Written to bonds_daily: {target_date} → {l1_regime}/{quality_label}")
    return row


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    sys.path.insert(0, ".")
    compute_bonds(target)
