"""
DO NOT RUN WITH --write UNTIL AMENDMENT 19 IS IN docs/LIMITATIONS_PLAN.md. The script checks this itself.

Test ledger by family. The counting rules and the calculation are in src/family_ledger.py. This script reads
the saved result files, runs the gate on the registered families and prints or writes the ledger.

Run from the repository root:
  python -m scripts.universe.make_test_ledger --dry-run --out PATH   (PATH outside results/)
  python -m scripts.universe.make_test_ledger --write --registered 19
"""
import argparse
from pathlib import Path

import pandas as pd

from src.family_ledger import gate_failures, ledger
from src.registration_guard import check_dry_run_target, require_committed, require_registered, write_new_csv

RESULTS = Path("results")
PLAN = Path("docs/LIMITATIONS_PLAN.md")
OUTPUT = RESULTS / "universe_study_test_ledger.csv"
AMENDMENT = 19


def main():
    parser = argparse.ArgumentParser(description="Test ledger by family.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--write", action="store_true", help="write results/ (needs --registered 19)")
    parser.add_argument("--out", type=Path, help="dry-run output file; must not be inside results/")
    parser.add_argument("--registered", type=int, help="the amendment number, to confirm it is registered")
    args = parser.parse_args()

    if args.write:
        if args.registered != AMENDMENT:
            raise SystemExit(f"--write needs --registered {AMENDMENT}. Nothing was written.")
        require_registered(PLAN, AMENDMENT)
        require_committed(PLAN)
        if OUTPUT.exists():
            raise SystemExit(f"{OUTPUT} already exists, left unchanged.")
    elif args.out:
        check_dry_run_target(args.out, RESULTS)

    table = ledger(RESULTS)
    failures = gate_failures(table)
    if failures:
        raise SystemExit("Gate failed, nothing written:\n  " + "\n  ".join(failures))
    print("Gate passed: the registered families match the published counts.")
    pd.set_option("display.width", 220)
    print(table.drop(columns=["source_files"]).to_string(index=False))
    if args.write:
        write_new_csv(table, OUTPUT)
        print(f"Wrote {OUTPUT}")
    elif args.out:
        write_new_csv(table, args.out)
        print(f"Dry run: wrote {args.out}")


if __name__ == "__main__":
    main()
