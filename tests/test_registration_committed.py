"""The registration gate must see a committed amendment, not a heading typed into a working file."""
import subprocess

import pytest

from src.registration_guard import require_committed


def _git(folder, *args):
    subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.com", *args],
                   cwd=folder, check=True, capture_output=True)


def test_an_uncommitted_amendment_heading_is_refused_and_a_committed_one_passes(tmp_path, monkeypatch):
    # Pre-registration only means something if git can show the plan was committed before the result was written.
    monkeypatch.chdir(tmp_path)
    _git(tmp_path, "init", "-q")
    plan = tmp_path / "plan.md"
    plan.write_text("## Amendment 18 (x)\ntext\n")
    _git(tmp_path, "add", "plan.md")
    _git(tmp_path, "commit", "-q", "-m", "plan")
    require_committed(plan)                                   # clean file passes
    plan.write_text("## Amendment 18 (x)\ntext\n\n## Amendment 19 (draft)\n")
    with pytest.raises(SystemExit):                           # heading typed but not committed
        require_committed(plan)
    _git(tmp_path, "commit", "-q", "-am", "amendment 19")
    require_committed(plan)                                   # committed again


def test_outside_a_git_repository_the_gate_refuses(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    plan = tmp_path / "plan.md"
    plan.write_text("## Amendment 19 (x)\n")
    with pytest.raises(SystemExit):
        require_committed(plan)
