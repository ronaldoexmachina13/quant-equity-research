"""Every local image the README shows must exist, so the page never has a broken picture."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_readme_images_exist():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    paths = re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", text)
    local = [p for p in paths if not p.startswith(("http://", "https://"))]
    assert local, "README shows no local images"
    missing = [p for p in local if not (ROOT / p).is_file()]
    assert not missing, f"README images not found: {missing}"
