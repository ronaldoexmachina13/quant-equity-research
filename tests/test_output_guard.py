"""Tests for the overwrite guards used by the 17-stock scripts. Everything is built by hand in a temporary folder."""
import sqlite3

import pytest

from src.output_guard import refuse_if_table_has_rows, refuse_to_overwrite


def test_refuse_to_overwrite_passes_when_no_file_exists(tmp_path):
    refuse_to_overwrite([tmp_path / "a.csv", tmp_path / "b.csv"])


def test_refuse_to_overwrite_names_the_existing_file_and_writes_nothing(tmp_path):
    existing = tmp_path / "a.csv"
    existing.write_text("old")
    with pytest.raises(SystemExit) as info:
        refuse_to_overwrite([existing, tmp_path / "b.csv"])
    assert str(existing) in str(info.value)
    assert "b.csv" not in str(info.value)
    assert existing.read_text() == "old"
    assert not (tmp_path / "b.csv").exists()


def _make_db(path, table, rows):
    connection = sqlite3.connect(path)
    connection.execute(f"CREATE TABLE {table} (ticker TEXT)")
    connection.executemany(f"INSERT INTO {table} VALUES (?)", [("A",)] * rows)
    connection.commit()
    connection.close()


def test_table_guard_stops_when_table_has_rows(tmp_path):
    db = tmp_path / "x.db"
    _make_db(db, "prices", 3)
    with pytest.raises(SystemExit) as info:
        refuse_if_table_has_rows("prices", ["script.py"], db_path=db)
    assert "3 rows" in str(info.value)


def test_table_guard_allows_replace_flag(tmp_path):
    db = tmp_path / "x.db"
    _make_db(db, "prices", 3)
    refuse_if_table_has_rows("prices", ["script.py", "--replace"], db_path=db)


def test_table_guard_allows_empty_table_and_missing_table(tmp_path):
    db = tmp_path / "x.db"
    _make_db(db, "prices", 0)
    refuse_if_table_has_rows("prices", [], db_path=db)
    refuse_if_table_has_rows("book_value", [], db_path=db)  # table not created yet


def test_table_guard_does_not_create_a_missing_database(tmp_path):
    db = tmp_path / "none.db"
    refuse_if_table_has_rows("prices", [], db_path=db)
    assert not db.exists()


def test_table_guard_rejects_unknown_table_name(tmp_path):
    with pytest.raises(ValueError):
        refuse_if_table_has_rows("prices; DROP TABLE prices", [], db_path=tmp_path / "x.db")
