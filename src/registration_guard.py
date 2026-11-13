"""
Guards for scripts whose results belong to a registered amendment.

A script that writes a result file must not run for real until the amendment that describes it has been
appended to docs/LIMITATIONS_PLAN.md. These functions check that, keep a dry run away from results/, and
write a new file only if it does not already exist (mode "x", as in CLAUDE.md rule 1).
"""
import re
import subprocess
from pathlib import Path

import pandas as pd


def amendment_is_registered(plan_text: str, number: int) -> bool:
    """True if the plan has a heading line that starts '## Amendment <number> ('. A mention in prose does not count."""
    pattern = rf"^## Amendment {int(number)}\b"
    return re.search(pattern, plan_text, flags=re.MULTILINE) is not None


def require_registered(plan_path, number: int) -> None:
    """Exit with a message unless the amendment heading is in the plan file."""
    path = Path(plan_path)
    if not path.exists() or not amendment_is_registered(path.read_text(encoding="utf-8"), number):
        raise SystemExit(f"Amendment {number} is not in {plan_path}. Append and commit it first. Nothing was written.")


def require_committed(plan_path) -> None:
    """
    Exit unless the plan file has no uncommitted changes. The amendment must be committed before any result is
    written, so that git records the date of the plan before the date of the result. A heading typed into the file
    but not yet committed would satisfy require_registered and must not.
    """
    try:
        status = subprocess.run(["git", "status", "--porcelain", "--", str(plan_path)],
                                capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        raise SystemExit(f"Could not ask git whether {plan_path} is committed. Nothing was written.") from None
    if status.strip():
        raise SystemExit(f"{plan_path} has uncommitted changes. Commit the amendment first. Nothing was written.")


def check_dry_run_target(out: Path, results_dir) -> None:
    """A dry run may write one file outside results/, never inside it and never over an existing file."""
    if Path(results_dir).resolve() in Path(out).resolve().parents:
        raise SystemExit("A dry run may not write inside results/.")
    if Path(out).exists():
        raise SystemExit(f"{out} already exists, left unchanged.")


def write_new_csv(table: pd.DataFrame, path) -> None:
    """Write the table to a file that must not exist yet."""
    try:
        with open(path, "x", newline="") as handle:
            table.to_csv(handle, index=False, lineterminator="\n")
    except FileExistsError:
        raise SystemExit(f"{path} already exists, left unchanged.") from None
