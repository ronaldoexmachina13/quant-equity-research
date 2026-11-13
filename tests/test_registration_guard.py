"""Tests for the guards that keep registered-amendment scripts from writing results too early."""
import pandas as pd
import pytest

from src.registration_guard import amendment_is_registered, check_dry_run_target, require_registered, write_new_csv

PLAN_WITH = "## Amendment 18 (x)\ntext\n\n## Amendment 19 (2026-12-01, after ...)\ntext\n"
PLAN_WITHOUT = "## Amendment 18 (x)\nA later entry may add Amendment 19 as a ledger.\n"


def test_amendment_is_registered_needs_a_heading_not_a_mention():
    assert amendment_is_registered(PLAN_WITH, 19)
    assert not amendment_is_registered(PLAN_WITHOUT, 19)
    assert not amendment_is_registered(PLAN_WITH, 1)           # Amendment 18 or 19 must not satisfy 1
    assert not amendment_is_registered("## Amendment 190 (x)\n", 19)


def test_require_registered_exits_when_missing_and_passes_when_present(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(PLAN_WITHOUT)
    with pytest.raises(SystemExit):
        require_registered(plan, 19)
    plan.write_text(PLAN_WITH)
    require_registered(plan, 19)
    with pytest.raises(SystemExit):
        require_registered(tmp_path / "missing.md", 19)


def test_dry_run_target_refuses_results_folder_and_existing_file(tmp_path):
    results = tmp_path / "results"
    results.mkdir()
    with pytest.raises(SystemExit):
        check_dry_run_target(results / "x.csv", results)
    existing = tmp_path / "y.csv"
    existing.write_text("a")
    with pytest.raises(SystemExit):
        check_dry_run_target(existing, results)
    check_dry_run_target(tmp_path / "new.csv", results)


def test_write_new_csv_writes_lf_and_never_overwrites(tmp_path):
    path = tmp_path / "t.csv"
    write_new_csv(pd.DataFrame({"a": [1, 2]}), path)
    assert path.read_bytes() == b"a\n1\n2\n"
    with pytest.raises(SystemExit):
        write_new_csv(pd.DataFrame({"a": [9]}), path)
    assert path.read_bytes() == b"a\n1\n2\n"
