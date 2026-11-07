"""
Amendment 14, decision 4: manifest of the raw-data cache.

    python -m scripts.universe.make_data_manifest            writes results/data_manifest.csv once
    python -m scripts.universe.make_data_manifest --verify   compares the cache with the saved manifest

The cache is UNIVERSE_CACHE_DIR if set, else data_cache/. It is outside Git.
The existing manifest is never overwritten. Modification time is when a file
was last written on that machine; it stands in for the download date.
"""
import argparse
from pathlib import Path

import pandas as pd

from src.data_manifest import file_manifest, verify_manifest
from src.universe import cache_dir

MANIFEST_PATH = Path("results") / "data_manifest.csv"


def write_manifest(root: Path):
    if MANIFEST_PATH.exists():
        raise SystemExit(f"{MANIFEST_PATH} already exists and is never overwritten. Use --verify to compare. Stopping.")
    if not root.is_dir():
        raise SystemExit(f"Cache folder {root} not found. Set UNIVERSE_CACHE_DIR. Stopping.")
    manifest = file_manifest(root)
    manifest.to_csv(MANIFEST_PATH, index=False, mode="x")
    top = manifest["path"].str.split("/").str[0].value_counts()
    print(f"Wrote {MANIFEST_PATH}: {len(manifest)} files, {manifest['size_bytes'].sum() / 1e6:.1f} MB, from {root}")
    print("Files by top-level folder:\n" + top.to_string())
    print(f"Last written: {manifest['modified_utc'].min()} to {manifest['modified_utc'].max()}")


def verify(root: Path):
    result = verify_manifest(root, pd.read_csv(MANIFEST_PATH))
    for label, paths in result.items():
        print(f"{label}: {len(paths)}")
        for path in paths[:20]:
            print(f"  {path}")
    raise SystemExit(0 if not result["changed"] and not result["missing"] else 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verify", action="store_true", help="compare the cache with results/data_manifest.csv")
    args = parser.parse_args()
    verify(cache_dir()) if args.verify else write_manifest(cache_dir())


if __name__ == "__main__":
    main()
