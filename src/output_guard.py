"""
Guards for the 17-stock study scripts.

CLAUDE.md rule 1: never overwrite or regenerate an existing result file. The
500-stock scripts enforce this by opening every output with mode "x". The
17-stock scripts wrote with plain to_csv and would silently replace a
published file. These two functions give them the same behaviour: stop before
any work is done, and say what was in the way.
"""
import os
import sqlite3
from pathlib import Path

import src.database as database

GUARDED_TABLES = ("prices", "book_value")


def refuse_to_overwrite(paths) -> None:
    """Exit with a message, writing nothing, if any of the output files already exists."""
    if isinstance(paths, (str, os.PathLike)):
        paths = [paths]  # a single path passed on its own would otherwise be read letter by letter
    # lexists, not exists: a broken symlink "does not exist" but writing to it would still create its target.
    existing = [str(p) for p in paths if os.path.lexists(p)]
    if existing:
        raise SystemExit(
            "Refusing to overwrite existing result files (CLAUDE.md rule 1). Nothing was written.\n  "
            + "\n  ".join(existing)
            + "\nWrite to a new file, or move the old one away on purpose."
        )


def refuse_if_table_has_rows(table: str, argv, replace_flag: str = "--replace", db_path=None) -> None:
    """
    Exit with a message if the SQLite table already holds rows, unless the
    replace flag is in argv. The data pipelines write with INSERT OR REPLACE,
    so a rerun would quietly change stored prices or book values that every
    first-study result was computed from. A missing database or an empty
    table is fine, and a missing database is not created by this check.
    """
    if table not in GUARDED_TABLES:
        raise ValueError(f"Unknown table: {table}")
    if replace_flag in argv:
        return
    db_path = database.DB_PATH if db_path is None else db_path
    if not Path(db_path).exists():
        return
    connection = sqlite3.connect(db_path)
    try:
        try:
            rows = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.OperationalError:  # the table has not been created yet
            rows = 0
    finally:
        connection.close()
    if rows:
        raise SystemExit(
            f"Table {table} already holds {rows} rows. A rerun would replace them with whatever the data "
            f"vendors return today. Nothing was written. To do it on purpose, run again with {replace_flag}."
        )
