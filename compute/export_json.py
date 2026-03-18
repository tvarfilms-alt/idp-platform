"""
IDP JSON Export — Generates data.json for the Dashboard

Per spec section 10:
  - l1 {} — current regime + 24 months history
  - l2 {} — current market regime + 250 days history
  - l3 [] — 50 stocks with factors and IdeaScore
  - bonds {} — market data + recommendations
  - meta {} — update date, config version, ETL status

Output: data.json next to the dashboard HTML.
Trigger: After each compute run.
"""
import sys
import os
import json
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_helpers import rest_get, log


def export_l1() -> dict:
    """Export L1 data: current + 24 months history."""
    rows = rest_get("l1_regime", {
        "select": "month,regime,risk_cap,growth_v5,monet_v5,pmi,cpi_yoy,ks,imoex,rgbi,bcom,urals,growth_base,monet_base,bcom_score",
        "order": "month.desc",
        "limit": "24",
    })
    if not rows:
        return {"current": None, "history": []}

    current = rows[0]
    return {
        "current": {
            "month": current["month"],
            "regime": current["regime"],
            "risk_cap": current["risk_cap"],
            "growth_v5": current["growth_v5"],
            "monet_v5": current["monet_v5"],
        },
        "indicators": {
            "pmi": current["pmi"],
            "cpi_yoy": current["cpi_yoy"],
            "key_rate": current["ks"],
            "imoex": current["imoex"],
            "rgbi": current["rgbi"],
            "bcom": current["bcom"],
            "urals": current["urals"],
        },
        "history": [{
            "month": r["month"],
            "regime": r["regime"],
            "risk_cap": r["risk_cap"],
            "growth_v5": r["growth_v5"],
            "monet_v5": r["monet_v5"],
        } for r in rows],
    }

def export_l2() -> dict:
    """Export L2 data: current + 250 days history."""
    rows = rest_get("l2_daily", {
        "select": "date,regime,multiplier,wms,vol_score,credit_score,liquidity_score,correlation_score,raw_indicators",
        "order": "date.desc",
        "limit": "250",
    })
    if not rows:
        return {"current": None, "history": []}

    current = rows[0]
    return {
        "current": {
            "date": current["date"],
            "regime": current["regime"],
            "multiplier": current["multiplier"],
            "wms": current["wms"],
        },
        "scores": {
            "volatility": current["vol_score"],
            "credit": current["credit_score"],
            "liquidity": current["liquidity_score"],
            "correlation": current["correlation_score"],
        },
        "history": [{
            "date": r["date"],
            "regime": r["regime"],
            "wms": r["wms"],
            "multiplier": r["multiplier"],
        } for r in rows],
    }

def export_l3() -> list:
    """Export L3 data: latest 50 stocks with scores."""
    latest = rest_get("l3_screening", {
        "select": "date",
        "order": "date.desc",
        "limit": "1",
    })
    if not latest:
        return []

    latest_date = latest[0]["date"]
    rows = rest_get("l3_screening", {
        "select": "ticker,pe,pbv,ev_ebitda,roe,debt_ratio,price,return_1m,return_3m,return_6m,mom_pctile,rv_pctile,qual_pctile,idea_score,signal",
        "date": f"eq.{latest_date}",
        "order": "idea_score.desc",
    })
    return [{
        "ticker": r["ticker"],
        "price": r["price"],
        "pe": r["pe"],
        "pbv": r["pbv"],
        "ev_ebitda": r["ev_ebitda"],
        "roe": r["roe"],
        "debt_ratio": r["debt_ratio"],
        "return_1m": r["return_1m"],
        "return_3m": r["return_3m"],
        "return_6m": r["return_6m"],
        "momentum": r["mom_pctile"],
        "value": r["rv_pctile"],
        "quality": r["qual_pctile"],
        "idea_score": r["idea_score"],
        "signal": r["signal"],
    } for r in rows]

def export_bonds() -> dict:
    """Export bonds data: current strategy + market metrics."""
    rows = rest_get("bonds_daily", {
        "select": "*",
        "order": "date.desc",
        "limit": "1",
    })
    if not rows:
        return {}

    r = rows[0]
    return {
        "date": r["date"],
        "market": {
            "gbi_ytm": r["gbi_ytm"],
            "cbi_ytm": r["cbi_ytm"],
            "g_spread": r["g_spread"],
            "key_rate": r["key_rate"],
            "ruonia": r["ruonia"],
            "cpi_yoy": r["cpi_yoy"],
            "real_yield": r["real_yield"],
            "rgb_index": r["rgb_index"],
        },
        "strategy": {
            "l1_regime": r["current_l1_regime"],
            "duration": r["duration_target"],
            "credit": r["credit_segment"],
            "coupon": r["coupon_type"],
            "quality": r["quality_label"],
            "target_ytm": r["target_ytm"],
            "bond_alloc_pct": r["bond_alloc_pct"],
        },
    }

def export_meta() -> dict:
    """Export metadata: versions, ETL status, update timestamp."""
    etl_runs = rest_get("etl_runs", {
        "select": "source_id,status,started_at,rows_loaded",
        "order": "started_at.desc",
        "limit": "10",
    })

    versions = rest_get("calc_versions", {
        "select": "level,version_id,valid_from,comment",
        "valid_to": "is.null",
    })

    return {
        "updated_at": date.today().isoformat(),
        "calc_versions": {v["level"]: {"id": v["version_id"], "from": v["valid_from"]}
                         for v in versions},
        "last_etl": [{
            "source": r["source_id"],
            "status": r["status"],
            "at": r["started_at"],
            "rows": r["rows_loaded"],
        } for r in etl_runs[:5]],
    }

def export_all(output_path: str = None):
    """Generate complete data.json."""
    if output_path is None:
        output_path = os.path.join(os.path.dirname(__file__), "..", "data.json")

    log("Exporting data.json...")

    data = {
        "l1": export_l1(),
        "l2": export_l2(),
        "l3": export_l3(),
        "bonds": export_bonds(),
        "meta": export_meta(),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    backup_path = output_path.replace(".json", f"_prev.json")
    if os.path.exists(output_path):
        import shutil
        try:
            shutil.copy2(output_path, backup_path)
        except Exception:
            pass

    size_kb = os.path.getsize(output_path) / 1024
    l3_count = len(data["l3"])
    l2_hist = len(data["l2"].get("history", []))
    log(f"  Exported: {size_kb:.1f} KB, L3={l3_count} stocks, L2={l2_hist} days history")
    log(f"  Output: {output_path}")

    return data


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else None
    export_all(output)
