"""Hand-worked tests for the test-ledger counting functions."""
import pandas as pd

from src.family_ledger import counts, gate_failures, inference_rows, sharpe_rows


def test_counts_returns_run_flagged_positive_and_negative():
    table = pd.DataFrame({"est": [0.5, -0.2, 0.1, -0.3], "flag": [True, True, False, False]})
    assert counts(table, "est", "flag") == (4, 2, 1, 1)


def test_counts_with_nothing_flagged():
    table = pd.DataFrame({"est": [0.5, -0.2], "flag": [False, False]})
    assert counts(table, "est", "flag") == (2, 0, 0, 0)


def test_sharpe_rows_keeps_only_headline_tests():
    files = {"a.csv": pd.DataFrame({"headline_test": [True, False, True], "x": [1, 2, 3]})}
    assert sharpe_rows(files.__getitem__, ["a.csv"])["x"].tolist() == [1, 3]


def test_inference_rows_lists_two_intervals_per_test():
    table = pd.DataFrame({"mean": [0.1, -0.2], "nw_excludes_zero": [True, False], "block_excludes_zero": [False, False]})
    both = inference_rows(lambda name: table, "x.csv")
    assert len(both) == 4
    assert both["flag"].tolist() == [True, False, False, False]
    assert both["point"].tolist() == [0.1, -0.2, 0.1, -0.2]


def _ledger(r1, r2):
    return pd.DataFrame({"family_id": ["R1", "R2"], "intervals_run": [r1[0], r2[0]], "exclude_zero": [r1[1], r2[1]]})


def test_gate_failures_passes_on_published_counts_and_reports_a_changed_count():
    assert gate_failures(_ledger((33, 0), (18, 2))) == []
    failures = gate_failures(_ledger((33, 1), (18, 2)))
    assert len(failures) == 1 and failures[0].startswith("R1")
