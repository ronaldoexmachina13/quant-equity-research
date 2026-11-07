"""
Manifest of the raw-data cache (LIMITATIONS_PLAN.md, Amendment 14, decision 4).

The cache is not in Git. The manifest records what was in it when the results
were produced: for every file its relative path, size, SHA-256 checksum and
modification time in UTC. The modification time is when the file was last
written on that machine. It stands in for the download date but is not proof
of it. Folders whose name starts with "_" and files ending in ".log" are
scratch and are left out.
"""
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

MANIFEST_COLUMNS = ["path", "size_bytes", "sha256", "modified_utc"]
CHUNK_BYTES = 1024 * 1024


def sha256_of(path: Path) -> str:
    """SHA-256 of a file, read in chunks so large files are not loaded whole."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cache_files(root: Path) -> list[Path]:
    """Every data file under root, sorted by relative path."""
    files = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if not path.is_file() or path.suffix == ".log" or any(part.startswith("_") for part in relative.parts[:-1]):
            continue
        files.append(path)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def file_manifest(root: Path) -> pd.DataFrame:
    """One row per file: relative path (with /), size in bytes, SHA-256, modification time in UTC."""
    rows = []
    for path in cache_files(root):
        stat = path.stat()
        rows.append({"path": path.relative_to(root).as_posix(), "size_bytes": stat.st_size, "sha256": sha256_of(path),
                     "modified_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    return pd.DataFrame(rows, columns=MANIFEST_COLUMNS)


def verify_manifest(root: Path, manifest: pd.DataFrame) -> dict:
    """
    Compare the cache with a saved manifest. Returns the paths that are
    changed (checksum differs), missing (in the manifest, not on disk) and new
    (on disk, not in the manifest).
    """
    recorded = dict(zip(manifest["path"], manifest["sha256"]))
    present = {path.relative_to(root).as_posix(): path for path in cache_files(root)}
    changed = sorted(p for p in recorded if p in present and sha256_of(present[p]) != recorded[p])
    return {"changed": changed, "missing": sorted(set(recorded) - set(present)), "new": sorted(set(present) - set(recorded))}
