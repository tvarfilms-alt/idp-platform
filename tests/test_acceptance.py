"""
IDP Acceptance Testing — Excel vs Python/DB

Compares compute results stored in DB against reference values from Excel models.
Per spec (section 7 of IDP_Data_Architecture_v2.pdf):
  - Intermediate scores: ±0.001 tolerance
  - Final scores: ±0.005 tolerance
  - Discrete results (regime, signal): exact match
  - Numeric results (risk_cap, multiplier): exact match

Usage:
  python test_acceptance.py                     # Run all tests
  python test_acceptance.py l1                  # Run L1 tests only
  python test_acceptance.py l2 2026-03-07       # Run L2 for specific date
  python test_acceptance.py --from-csv tests/reference_l1.csv

Reference data format (CSV):
  level,date,field,expected_value
  L1,2026-03-01,regime,GROWTH
  L1,2026-03-01,risk_cap,75%
  L1,2026-03-01,growth_v5,0.234
"""
import sys
import os
import json
import csv
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "compute"))
from db_helpers import rest_get, log

# ── Tolerances (from spec section 7.2) ──
TOLERANCE_INTERMEDIATE = 0.001  # growth_base, vol_score, mom_pctile, etc.
TOLERANCE_FINAL = 0.005         # growth_v5, wms, idea_score
EXACT_FIELDS = {"regime", "signal", "risk_cap", "multiplier", "quality_label",
                "duration_target", "credit_segment", "coupon_type"}

FINAL_SCORE_FIELDS = {"growth_v5", "monet_v5", "wms", "idea_score",
                      "bond_alloc_pct", "target_ytm"}


def compare_value(field: str, expected, actual) -> tuple[bool, str]:
    """Compare expected vs actual with appropriate tolerance."""
    if expected is None and actual is None:
        return True, "both None"
    if expected is None or actual is None:
        return False, f"expected={expected} actual={actual}"

    # Exact match for discrete fields
    if field in EXACT_FIELDS:
        ok = str(expected).strip() == str(actual).strip()
        return ok, f"expected='{expected}' actual='{actual}'"

    # Numeric comparison
    try:
        exp_f = float(expected)
        act_f = float(actual)
    except (ValueError, TypeError):
        return str(expected) == str(actual), f"expected='{expected}' actual='{actual}'"

    tol = TOLERANCE_FINAL if field in FINAL_SCORE_FIELDS else TOLERANCE_INTERMEDIATE
    diff = abs(exp_f - act_f)
    ok = diff <= tol
    return ok, f"expected={exp_f} actual={act_f} diff={diff:.6f} tol={tol}"


def test_l1(reference: list[dict] = None, control_dates: list[str] = None):
    """Test L1 compute results against reference data."""
    log("=" * 60)
    log("ACCEPTANCE TEST: L1 Macro Regime")
    log("=" * 60)

    if control_dates is None:
        control_dates = ["2025-07-01", "2025-10-01", "2026-01-01", "2026-03-01"]

    results = {"pass": 0, "fail": 0, "skip": 0, "details": []}

    for dt in control_dates:
        rows = rest_get("l1_regime", {"month": f"eq.{dt}", "select": "*"})
        if not rows:
            log(f"  SKIP {dt}: no data in l1_regime")
            results["skip"] += 1
            continue

        row = rows[0]
        log(f"\n  Date: {dt}")
        log(f"  Regime: {row['regime']} | Risk Cap: {row['risk_cap']}")
        log(f"  Growth V5: {row['growth_v5']} | Monet V5: {row['monet_v5']}")

        # If reference data provided, compare
        if reference:
            refs = [r for r in reference if r["date"] == dt and r["level"] == "L1"]
            for ref in refs:
                field = ref["field"]
                expected = ref["expected_value"]
                actual = row.get(field)
                ok, detail = compare_value(field, expected, actual)
                status = "PASS" if ok else "FAIL"
                if ok:
                    results["pass"] += 1
                else:
                    results["fail"] += 1
                results["details"].append({
                    "level": "L1", "date": dt, "field": field,
                    "status": status, "detail": detail
                })
                icon = "✓" if ok else "✗"
                log(f"  {icon} {field}: {detail}")
        else:
            # Self-consistency checks
            checks = [
                ("regime_valid", row["regime"] in [
                    "GOLDILOCKS", "GROWTH", "OVERHEATING", "RECOVERY",
                    "TRANSITION", "SLOWDOWN", "REFLATION", "STAGNATION",
                    "STAGFLATION", "STRESS"
                ]),
                ("risk_cap_format", row["risk_cap"].endswith("%")),
                ("growth_v5_range", row["growth_v5"] is None or -2 <= float(row["growth_v5"]) <= 2),
                ("monet_v5_range", row["monet_v5"] is None or -2 <= float(row["monet_v5"]) <= 2),
            ]
            for name, ok in checks:
                status = "PASS" if ok else "FAIL"
                if ok:
                    results["pass"] += 1
                else:
                    results["fail"] += 1
                results["details"].append({
                    "level": "L1", "date": dt, "field": name, "status": status
                })
                icon = "✓" if ok else "✗"
                log(f"  {icon} {name}")

    return results


def test_l2(reference: list[dict] = None, control_dates: list[str] = None):
    """Test L2 compute results."""
    log("\n" + "=" * 60)
    log("ACCEPTANCE TEST: L2 Market Regime")
    log("=" * 60)

    if control_dates is None:
        control_dates = ["2026-01-15", "2026-02-03", "2026-02-20",
                         "2026-03-07", "2026-03-14"]

    results = {"pass": 0, "fail": 0, "skip": 0, "details": []}

    for dt in control_dates:
        rows = rest_get("l2_daily", {"date": f"eq.{dt}", "select": "*"})
        if not rows:
            log(f"  SKIP {dt}: no data")
            results["skip"] += 1
            continue

        row = rows[0]
        log(f"\n  Date: {dt}")
        log(f"  Regime: {row['regime']} | WMS: {row['wms']} | Mult: {row['multiplier']}")
        log(f"  Scores: vol={row['vol_score']} cred={row['credit_score']} "
            f"liq={row['liquidity_score']} corr={row['correlation_score']}")

        if reference:
            refs = [r for r in reference if r["date"] == dt and r["level"] == "L2"]
            for ref in refs:
                field = ref["field"]
                expected = ref["expected_value"]
                actual = row.get(field)
                ok, detail = compare_value(field, expected, actual)
                status = "PASS" if ok else "FAIL"
                results["pass" if ok else "fail"] += 1
                results["details"].append({
                    "level": "L2", "date": dt, "field": field,
                    "status": status, "detail": detail
                })
                icon = "✓" if ok else "✗"
                log(f"  {icon} {field}: {detail}")
        else:
            # Self-consistency
            checks = [
                ("regime_valid", row["regime"] in ["Risk-on", "Neutral", "Risk-off"]),
                ("wms_range", 0 <= float(row["wms"]) <= 10),
                ("multiplier_valid", float(row["multiplier"]) in [0.5, 1.0, 1.2]),
                ("scores_range", all(0 <= (row.get(f) or 0) <= 2
                    for f in ["vol_score", "credit_score", "liquidity_score", "correlation_score"])),
            ]
            for name, ok in checks:
                status = "PASS" if ok else "FAIL"
                results["pass" if ok else "fail"] += 1
                results["details"].append({"level": "L2", "date": dt, "field": name, "status": status})
                icon = "✓" if ok else "✗"
                log(f"  {icon} {name}")

    return results


def test_l3(reference: list[dict] = None, control_dates: list[str] = None):
    """Test L3 screening results."""
    log("\n" + "=" * 60)
    log("ACCEPTANCE TEST: L3 Cross-Section")
    log("=" * 60)

    if control_dates is None:
        control_dates = ["2026-02-10", "2026-02-24", "2026-03-10"]

    results = {"pass": 0, "fail": 0, "skip": 0, "details": []}

    for dt in control_dates:
        rows = rest_get("l3_screening", {
            "date": f"eq.{dt}", "select": "*", "order": "idea_score.desc"
        })
        if not rows:
            log(f"  SKIP {dt}: no data")
            results["skip"] += 1
            continue

        log(f"\n  Date: {dt} — {len(rows)} stocks scored")
        buys = [r for r in rows if r["signal"] == "BUY"]
        avoids = [r for r in rows if r["signal"] == "AVOID"]
        log(f"  BUY: {', '.join(r['ticker'] for r in buys[:10])}")
        log(f"  AVOID: {', '.join(r['ticker'] for r in avoids[:10])}")

        if reference:
            refs = [r for r in reference if r["date"] == dt and r["level"] == "L3"]
            for ref in refs:
                ticker = ref.get("ticker")
                field = ref["field"]
                expected = ref["expected_value"]
                match = [r for r in rows if r["ticker"] == ticker] if ticker else rows[:1]
                if not match:
                    results["skip"] += 1
                    continue
                actual = match[0].get(field)
                ok, detail = compare_value(field, expected, actual)
                status = "PASS" if ok else "FAIL"
                results["pass" if ok else "fail"] += 1
                results["details"].append({
                    "level": "L3", "date": dt, "ticker": ticker,
                    "field": field, "status": status, "detail": detail
                })
                icon = "✓" if ok else "✗"
                log(f"  {icon} {ticker}.{field}: {detail}")
        else:
            # Self-consistency
            checks = [
                ("stock_count", len(rows) >= 40),
                ("scores_0_1", all(0 <= float(r["idea_score"]) <= 1 for r in rows)),
                ("signals_valid", all(r["signal"] in ["BUY", "HOLD", "AVOID"] for r in rows)),
                ("buy_count", 5 <= len(buys) <= 15),
                ("avoid_count", 5 <= len(avoids) <= 15),
            ]
            for name, ok in checks:
                status = "PASS" if ok else "FAIL"
                results["pass" if ok else "fail"] += 1
                results["details"].append({"level": "L3", "date": dt, "field": name, "status": status})
                icon = "✓" if ok else "✗"
                log(f"  {icon} {name}")

    return results


def test_bonds(reference: list[dict] = None, control_dates: list[str] = None):
    """Test bonds daily results."""
    log("\n" + "=" * 60)
    log("ACCEPTANCE TEST: Bonds Strategy")
    log("=" * 60)

    if control_dates is None:
        control_dates = ["2026-01-15", "2026-02-15", "2026-03-10"]

    results = {"pass": 0, "fail": 0, "skip": 0, "details": []}

    for dt in control_dates:
        rows = rest_get("bonds_daily", {"date": f"eq.{dt}", "select": "*"})
        if not rows:
            log(f"  SKIP {dt}: no data")
            results["skip"] += 1
            continue

        row = rows[0]
        log(f"\n  Date: {dt}")
        log(f"  L1 Regime: {row['current_l1_regime']} | Quality: {row['quality_label']}")
        log(f"  Duration: {row['duration_target']} | Credit: {row['credit_segment']} | Coupon: {row['coupon_type']}")
        log(f"  Bond Alloc: {row['bond_alloc_pct']}% | Target YTM: {row['target_ytm']}")

        if reference:
            refs = [r for r in reference if r["date"] == dt and r["level"] == "BONDS"]
            for ref in refs:
                field = ref["field"]
                expected = ref["expected_value"]
                actual = row.get(field)
                ok, detail = compare_value(field, expected, actual)
                status = "PASS" if ok else "FAIL"
                results["pass" if ok else "fail"] += 1
                results["details"].append({
                    "level": "BONDS", "date": dt, "field": field,
                    "status": status, "detail": detail
                })
                icon = "✓" if ok else "✗"
                log(f"  {icon} {field}: {detail}")
        else:
            checks = [
                ("regime_present", row["current_l1_regime"] is not None),
                ("quality_valid", row["quality_label"] in [
                    "Агрессивно", "Умеренно", "Осторожно", "Защитно"]),
                ("alloc_range", 0 <= (row["bond_alloc_pct"] or 0) <= 100),
            ]
            for name, ok in checks:
                status = "PASS" if ok else "FAIL"
                results["pass" if ok else "fail"] += 1
                results["details"].append({"level": "BONDS", "date": dt, "field": name, "status": status})
                icon = "✓" if ok else "✗"
                log(f"  {icon} {name}")

    return results


def load_reference_csv(filepath: str) -> list[dict]:
    """Load reference data from CSV file."""
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        return list(reader)


def main():
    level = None
    target_date = None
    reference = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--from-csv":
            reference = load_reference_csv(args[i+1])
            i += 2
        elif args[i] in ("l1", "l2", "l3", "bonds", "all"):
            level = args[i]
            i += 1
        else:
            target_date = args[i]
            i += 1

    levels = ["l1", "l2", "l3", "bonds"] if level in (None, "all") else [level]
    all_results = {"pass": 0, "fail": 0, "skip": 0}

    runners = {
        "l1": test_l1,
        "l2": test_l2,
        "l3": test_l3,
        "bonds": test_bonds,
    }

    for lvl in levels:
        dates = [target_date] if target_date else None
        ref = reference if reference else None
        r = runners[lvl](ref, dates)
        all_results["pass"] += r["pass"]
        all_results["fail"] += r["fail"]
        all_results["skip"] += r["skip"]

    # Summary
    log(f"\n{'='*60}")
    log("ACCEPTANCE TEST SUMMARY")
    log(f"{'='*60}")
    total = all_results["pass"] + all_results["fail"]
    log(f"  PASS: {all_results['pass']}/{total}")
    log(f"  FAIL: {all_results['fail']}/{total}")
    log(f"  SKIP: {all_results['skip']}")

    if all_results["fail"] > 0:
        log("\n  RESULT: FAIL — some tests did not pass")
        sys.exit(1)
    else:
        log("\n  RESULT: PASS — all tests passed")

    # Save results
    out_dir = os.path.join(os.path.dirname(__file__), "..", "tests")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"acceptance_results_{date.today().isoformat()}.json")
    with open(out_file, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    log(f"  Results saved to {out_file}")


if __name__ == "__main__":
    main()
