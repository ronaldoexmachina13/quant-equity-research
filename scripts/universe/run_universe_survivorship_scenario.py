"""
DO NOT RUN WITH --write UNTIL AMENDMENT 19 IS IN docs/LIMITATIONS_PLAN.md. The script checks this itself.

Survivorship scenario table for the Momentum quintile spread. The calculation is in src/survivorship_scenario.py
(read its header for the rule and the assumptions). This script reads three saved files, runs the gate and prints
or writes the table.

Run from the repository root:
  python -m scripts.universe.run_universe_survivorship_scenario --dry-run --out PATH   (PATH outside results/)
  python -m scripts.universe.run_universe_survivorship_scenario --write --registered 19
"""
import argparse
from pathlib import Path

import pandas as pd

from src.registration_guard import check_dry_run_target, require_committed, require_registered, write_new_csv
from src.survivorship_scenario import gate_failures, scenario_table

RESULTS = Path("results")
PLAN = Path("docs/LIMITATIONS_PLAN.md")
OUTPUT = RESULTS / "universe_study_survivorship_scenario.csv"
AMENDMENT = 19


def main():
    parser = argparse.ArgumentParser(description="Survivorship scenario table for the Momentum quintile spread.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="print the table; write only to --out if given")
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

    table = scenario_table(
        pd.read_csv(RESULTS / "universe_study_quintile_returns_monthly.csv"),
        pd.read_csv(RESULTS / "universe_coverage_monthly.csv"),
    )
    failures = gate_failures(table, pd.read_csv(RESULTS / "universe_study_signal_summary_momentum.csv"))
    if failures:
        raise SystemExit("Gate failed, nothing written:\n  " + "\n  ".join(failures))
    print("Gate passed: the no-adjustment rows reproduce the saved Momentum quintile spread to 1e-9.")
    pd.set_option("display.width", 220)
    print(table.drop(columns=["note", "signal"]).round(4).to_string(index=False))
    if args.write:
        write_new_csv(table, OUTPUT)
        print(f"Wrote {OUTPUT}")
    elif args.out:
        write_new_csv(table, args.out)
        print(f"Dry run: wrote {args.out}")


if __name__ == "__main__":
    main()
