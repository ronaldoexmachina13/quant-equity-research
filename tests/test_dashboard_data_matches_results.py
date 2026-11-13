"""
The dashboard reads assets/universe_*_data.js, which are generated from the
CSV files in results/ (CLAUDE.md rule 7: the CSVs are the source of truth).
This test regenerates every one of them into a temporary folder from the
committed CSVs and requires the text to match the committed copy exactly. It
fails if a CSV changes without the data file being regenerated, if a data file
is edited by hand, or if the generator changes what it writes.
"""
import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = "scripts.universe.generate_universe_dashboard_data"
OUTPUT_FILES = {
    "OUT": "universe_data.js",
    "SENS_OUT": "universe_sens_data.js",
    "STOCKS_OUT": "universe_stocks_data.js",
    "HOLDINGS_OUT": "universe_holdings_data.js",
    "EXTRAS_OUT": "universe_extras_data.js",
    "CONTROLS_OUT": "universe_controls_data.js",
    "FACTOR4_OUT": "universe_factor4_data.js",
    "LEDGER_OUT": "universe_ledger_data.js",
}


@pytest.fixture(scope="module")
def regenerated(tmp_path_factory):
    folder = tmp_path_factory.mktemp("dashboard_data")
    generator = importlib.import_module(GENERATOR)
    patch = pytest.MonkeyPatch()
    try:
        patch.chdir(ROOT)        # the generator reads Path("results") and writes the path into each file's header
        for constant, name in OUTPUT_FILES.items():
            patch.setattr(generator, constant, folder / name)
        generator.main()
    finally:
        patch.undo()
    return folder


@pytest.mark.parametrize("name", sorted(OUTPUT_FILES.values()))
def test_committed_dashboard_data_equals_what_the_generator_writes_from_the_csvs(regenerated, name):
    written = (regenerated / name).read_text(encoding="utf-8")
    committed = (ROOT / "assets" / name).read_text(encoding="utf-8")
    if written != committed:
        # pytest.fail, not assert: an assert would make pytest diff two files of several hundred kilobytes, which takes minutes.
        pytest.fail(f"assets/{name} no longer matches results/. Regenerate it, do not edit it by hand.")
