"""Tests for src/sector_neutral.py. Inputs are hand-made."""
import numpy as np
import pandas as pd
import pytest

from src.sector_neutral import restrict_to_names, sector_neutral_score


def _frame():
    dates = pd.to_datetime(["2020-01-31", "2020-02-29"])
    tickers = [f"A{i}" for i in range(6)] + [f"B{i}" for i in range(4)] + ["N0"]
    scores = [[-1, -2, -3, -4, -5, -6, -10, -20, -30, -40, -7],
              [-1, -2, -3, -4, -5, -6, -10, -20, -30, -40, np.nan]]
    return pd.DataFrame(scores, index=dates, columns=tickers, dtype=float)


def _sectors():
    return pd.Series({**{f"A{i}": "X" for i in range(6)}, **{f"B{i}": "Y" for i in range(4)}})


def test_scores_are_standardised_inside_each_sector():
    neutral, _ = sector_neutral_score(_frame(), _sectors(), min_names=4)
    row = neutral.loc["2020-01-31"]
    for names in (["A0", "A1", "A2", "A3", "A4", "A5"], ["B0", "B1", "B2", "B3"]):
        assert row[names].mean() == pytest.approx(0.0, abs=1e-12)
        assert row[names].std() == pytest.approx(1.0)


def test_a_cheap_sector_no_longer_dominates_the_top():
    raw = _frame().loc["2020-01-31"].dropna()
    neutral, _ = sector_neutral_score(_frame(), _sectors(), min_names=4)
    row = neutral.loc["2020-01-31"].dropna()
    assert set(raw.nlargest(4).index) == {"A0", "A1", "A2", "A3"}   # sector X holds the top four before
    assert row.nlargest(2).index.map(lambda t: t[0]).nunique() == 2  # both sectors reach the top two after


def test_unknown_sector_and_small_sector_are_left_out_and_counted():
    neutral, counts = sector_neutral_score(_frame(), _sectors(), min_names=5)
    first = counts.iloc[0]
    assert (first["names_scored"], first["no_sector"], first["small_sector"], first["kept"]) == (11, 1, 4, 6)
    assert first["sectors_ranked"] == 1
    assert neutral.loc["2020-01-31", ["B0", "B1", "B2", "B3", "N0"]].isna().all()


def test_count_identity_holds_every_month():
    _, counts = sector_neutral_score(_frame(), _sectors(), min_names=4)
    assert (counts["names_scored"] == counts["no_sector"] + counts["small_sector"] + counts["kept"]).all()


def test_missing_scores_stay_missing():
    neutral, _ = sector_neutral_score(_frame(), _sectors(), min_names=4)
    assert np.isnan(neutral.loc["2020-02-29", "N0"])


def test_restrict_to_names_keeps_only_reference_names():
    signal = _frame()
    reference = signal.copy()
    reference.loc["2020-01-31", ["A0", "A1"]] = np.nan
    out = restrict_to_names(signal, reference)
    assert out.loc["2020-01-31", ["A0", "A1"]].isna().all()
    assert out.loc["2020-01-31", "A2"] == signal.loc["2020-01-31", "A2"]
