"""
Unit tests for src/data_manifest.py (LIMITATIONS_PLAN.md, Amendment 14, decision 4).
Small files in a temporary folder; no real data.
"""
import re

import pandas as pd

from src.data_manifest import file_manifest, verify_manifest, MANIFEST_COLUMNS

HELLO_SHA256 = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
WORLD_SHA256 = "486ea46224d1bb4fb680f34f7c9ad96a8f24ec88be73ea8e5a6c65260e9cb8a7"


def make_cache(root):
    (root / "sub").mkdir()
    (root / "_preview").mkdir()
    (root / "a.txt").write_text("hello")
    (root / "sub" / "b.txt").write_text("world")
    (root / "_preview" / "scratch.txt").write_text("not data")
    (root / "run.log").write_text("not data")


def test_manifest_lists_data_files_only_in_path_order(tmp_path):
    make_cache(tmp_path)
    manifest = file_manifest(tmp_path)
    assert manifest.columns.tolist() == MANIFEST_COLUMNS
    assert manifest["path"].tolist() == ["a.txt", "sub/b.txt"]
    assert manifest["size_bytes"].tolist() == [5, 5]
    assert manifest["sha256"].tolist() == [HELLO_SHA256, WORLD_SHA256]
    assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", t) for t in manifest["modified_utc"])


def test_an_empty_cache_gives_an_empty_manifest_with_columns(tmp_path):
    manifest = file_manifest(tmp_path)
    assert manifest.empty and manifest.columns.tolist() == MANIFEST_COLUMNS


def test_verify_finds_nothing_when_the_cache_is_unchanged(tmp_path):
    make_cache(tmp_path)
    assert verify_manifest(tmp_path, file_manifest(tmp_path)) == {"changed": [], "missing": [], "new": []}


def test_verify_reports_changed_missing_and_new_files(tmp_path):
    make_cache(tmp_path)
    manifest = file_manifest(tmp_path)
    (tmp_path / "a.txt").write_text("hello!")
    (tmp_path / "sub" / "b.txt").unlink()
    (tmp_path / "d.txt").write_text("extra")
    assert verify_manifest(tmp_path, manifest) == {"changed": ["a.txt"], "missing": ["sub/b.txt"], "new": ["d.txt"]}
