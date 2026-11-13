"""Edge cases for the overwrite guards: the ways a result file could still be replaced by mistake."""
import os
import sqlite3

import pytest

from src.output_guard import refuse_if_table_has_rows, refuse_to_overwrite


def test_a_path_passed_on_its_own_is_checked_as_a_path_not_letter_by_letter(tmp_path, monkeypatch):
    # "summary" iterated as a string is the letters "s", "u", "m" ... and none of those files exist,
    # so a careless call refuse_to_overwrite("summary") would let the real file be overwritten.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "summary").write_text("published")
    with pytest.raises(SystemExit):
        refuse_to_overwrite("summary")


def test_a_broken_symlink_counts_as_an_existing_result_file(tmp_path):
    # Writing to a dangling link creates the file it points to, which may sit outside results/.
    link = tmp_path / "result.csv"
    try:
        os.symlink(tmp_path / "elsewhere.csv", link)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available here")
    with pytest.raises(SystemExit):
        refuse_to_overwrite([link])


def test_a_table_holding_exactly_one_row_is_still_protected(tmp_path):
    # One stored price is already data that every first-study result was computed from.
    db = tmp_path / "q.db"
    connection = sqlite3.connect(db)
    connection.execute("CREATE TABLE prices (date TEXT, ticker TEXT, adj_close REAL)")
    connection.execute("INSERT INTO prices VALUES ('2020-01-31', 'AAA', 100.0)")
    connection.commit()
    connection.close()
    with pytest.raises(SystemExit):
        refuse_if_table_has_rows("prices", [], db_path=db)
