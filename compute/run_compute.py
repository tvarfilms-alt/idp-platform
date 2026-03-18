"""
IDP Compute Runner — Orchestrates all compute modules.

Usage:
  python run_compute.py                    # Run all levels
  python run_compute.py l1                 # Run L1 only
  python run_compute.py l2                 # Run L2 only
  python run_compute.py l3                 # Run L3 only
  python run_compute.py bonds              # Run Bonds only
  python run_compute.py l1 2026-03-01      # Run L1 for specific date
"""
import sys
import os
import traceback

# Add current dir to path for db_helpers
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_helpers import log


def run_l1(target=None):
    from compute_l1 import compute_l1
    return compute_l1(target)

def run_l2(target=None):
    from compute_l2 import compute_l2
    return compute_l2(target)

def run_l3(target=None):
    from compute_l3 import compute_l3
    return compute_l3(target)

def run_bonds(target=None):
    from compute_bonds import compute_bonds
    return compute_bonds(target)


RUNNERS = {
    "l1": run_l1,
    "l2": run_l2,
    "l3": run_l3,
    "bonds": run_bonds,
}

# Default execution order (respects dependencies)
DEFAULT_ORDER = ["l1", "l2", "bonds", "l3"]


def main():
    level = sys.argv[1] if len(sys.argv) > 1 else "all"
    target = sys.argv[2] if len(sys.argv) > 2 else None

    levels = DEFAULT_ORDER if level == "all" else [level]
    results = {}
    errors = {}

    for lvl in levels:
        runner = RUNNERS.get(lvl)
        if not runner:
            log(f"Unknown level: {lvl}")
            continue
        try:
            log(f"{'='*60}")
            log(f"Starting {lvl.upper()}")
            log(f"{'='*60}")
            result = runner(target)
            results[lvl] = "OK"
            log(f"{lvl.upper()} completed successfully")
        except Exception as e:
            errors[lvl] = str(e)
            log(f"{lvl.upper()} FAILED: {e}")
            traceback.print_exc()

    # Summary
    log(f"\n{'='*60}")
    log("COMPUTE SUMMARY")
    log(f"{'='*60}")
    for lvl in levels:
        status = results.get(lvl, errors.get(lvl, "SKIPPED"))
        icon = "OK" if lvl in results else "FAIL"
        log(f"  {lvl.upper()}: {icon} — {status}")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
