"""
The grey detectable-effect bands on the summary page (Exhibit 1). Each band is the smallest true average effect a
signal's 2012 to 2020 test could reliably detect: (1.645 + 0.842) x standard error of the monthly mean, which is
80% power at a 10% two-sided level. The figures are written by the dashboard data generator from saved files, so
these tests check the arithmetic by hand and then check the committed data against an independent recomputation.
"""
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.universe.generate_universe_dashboard_data import detectable_effects

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
Z = 1.645 + 0.842
NEW = "New test (2012-2020)"


def _committed():
    text = (ROOT / "assets" / "universe_data.js").read_text(encoding="utf-8")
    return json.loads(text.split("const UNIVERSE = ", 1)[1].rstrip().rstrip(";"))["detectable"]


def test_detectable_effect_is_worked_by_hand_for_series_and_for_intervals(tmp_path):
    # Monthly series 1%, 3%, 1%, 3%: mean 2%, sample SD = sqrt(4 x 0.01^2 / 3) = 0.011547, 4 months, so the standard
    # error of the mean is 0.011547 / 2 and the band is 2.487 times that. A series dated outside 2012 to 2020 is ignored.
    series = [0.01, 0.03, 0.01, 0.03]
    for name, column in [("ic_monthly", "rank_ic"), ("spread_monthly", "quintile_spread")]:
        for part, signal in (("momentum", "Momentum"), ("value_combined", "Value")):
            frame = pd.DataFrame({"period": [NEW] * 4 + ["Re-test (2021-2026)"], "signal": [signal] * 5, column: series + [9.0]})
            frame.to_csv(tmp_path / f"universe_study_{name}_{part}.csv", index=False)
    # Fama-MacBeth: the saved iid 90% interval is [-0.002, +0.002], half-width 0.002, so the standard error is
    # 0.002 / 1.645 and the band is 2.487 times that. The joint block has no Combined row, so it gets no band.
    robustness = pd.DataFrame({
        "test": ["fama_macbeth_single", "fama_macbeth_joint", "fama_macbeth_single"],
        "signal": ["Value", "Value", "Value"], "period": [NEW, NEW, "Re-test (2021-2026)"],
        "iid_ci_90_lower": [-0.002, -0.004, -9.0], "iid_ci_90_upper": [0.002, 0.004, 9.0],
    })
    robustness.to_csv(tmp_path / "universe_study_inference_robustness.csv", index=False)
    found = detectable_effects(tmp_path)
    expected_series = Z * math.sqrt(4 * 0.01 ** 2 / 3) / 2
    assert found["rank_ic"]["Momentum"] == pytest.approx(expected_series, abs=1e-6)
    assert found["rank_ic"]["Value"] == pytest.approx(expected_series, abs=1e-6)
    assert found["quintile_spread"]["Momentum"] == pytest.approx(expected_series, abs=1e-6)
    assert found["fama_macbeth_single"] == pytest.approx({"Value": Z * 0.002 / 1.645}, abs=1e-6)
    assert found["fama_macbeth_joint"] == pytest.approx({"Value": Z * 0.004 / 1.645}, abs=1e-6)


def test_committed_band_figures_match_the_saved_csvs():
    # Rank IC and quintile spread are recomputed here from the monthly files with numpy; Fama-MacBeth from the iid interval.
    committed = _committed()
    for files, column, test in [
        (("momentum", "value_combined"), "rank_ic", "rank_ic"),
        (("momentum", "value_combined"), "quintile_spread", "quintile_spread"),
    ]:
        stem = "ic_monthly" if column == "rank_ic" else "spread_monthly"
        frame = pd.concat([pd.read_csv(RESULTS / f"universe_study_{stem}_{f}.csv") for f in files])
        frame = frame[frame["period"] == NEW]
        for signal in ("Momentum", "Value", "Combined"):
            x = frame.loc[frame["signal"] == signal, column].to_numpy()
            assert len(x) == 108
            assert committed[test][signal] == pytest.approx(Z * np.std(x, ddof=1) / np.sqrt(108), abs=1e-6)
    robustness = pd.read_csv(RESULTS / "universe_study_inference_robustness.csv")
    robustness = robustness[robustness["period"] == NEW]
    for test in ("fama_macbeth_single", "fama_macbeth_joint"):
        for _, row in robustness[robustness["test"] == test].iterrows():
            half = (row["iid_ci_90_upper"] - row["iid_ci_90_lower"]) / 2
            assert committed[test][row["signal"]] == pytest.approx(Z * half / 1.645, abs=1e-6)
    assert set(committed["fama_macbeth_joint"]) == {"Momentum", "Value"}


def test_published_band_figures_as_displayed():
    committed = _committed()
    assert {s: round(v, 3) for s, v in committed["rank_ic"].items()} == {"Momentum": 0.055, "Value": 0.041, "Combined": 0.052}
    assert {s: round(v * 100, 2) for s, v in committed["quintile_spread"].items()} == {"Momentum": 1.24, "Value": 0.93, "Combined": 1.17}
    assert {s: round(v, 4) for s, v in committed["fama_macbeth_single"].items()} == {"Momentum": 0.0043, "Value": 0.0011, "Combined": 0.0028}


def test_band_rank_ic_equals_the_figures_the_page_computes_from_the_ic_series():
    # The page's own detectable-effect table computes the rank IC figure from the 108 monthly ICs; the band must agree.
    text = (ROOT / "assets" / "universe_data.js").read_text(encoding="utf-8")
    data = json.loads(text.split("const UNIVERSE = ", 1)[1].rstrip().rstrip(";"))
    for signal, series in data["ic"].items():
        first = np.array(series[: data["split"]])
        assert data["detectable"]["rank_ic"][signal] == pytest.approx(Z * first.std(ddof=1) / math.sqrt(data["split"]), abs=1e-5)


def test_summary_page_draws_a_band_per_signal_and_the_caption_calls_them_descriptive():
    index = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "bands: U.detectable[k]" in index
    assert "band: k ===" not in index                       # the old single band is gone
    assert re.search(r"descriptive: they were computed after the registered results", index)
    dashboard = (ROOT / "assets" / "dashboard.js").read_text(encoding="utf-8")
    assert "bandRuns" in dashboard
