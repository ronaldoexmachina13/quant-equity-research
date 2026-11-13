"""Capture the README images from the dashboard pages.

Each image is one panel of the live site, rendered in the site's own dark theme
at 1280 px width and 2x scale, so the README pictures match the dashboard.

Usage (from the repository root, with Playwright installed):
  python scripts/capture_readme_images.py            # writes docs/img/*.png
Optional arguments: ROOT OUT CHROME_PATH FILE_NAMES (comma-separated, to redo only those images).
The pages are opened from the local files, so no network is needed.
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "docs" / "img"
CHROME = sys.argv[3] if len(sys.argv) > 3 else None
ONLY = set(sys.argv[4].split(",")) if len(sys.argv) > 4 else None  # optional: only these file names

# (file name, page, URL hash, heading text that identifies the panel[, extra CSS for that image])
# The first image shows the chart only: the page's caption paragraph and source line are hidden,
# because the README explains the exhibit in its own text.
SHOTS = [
    ("01-registered-tests.png", "index.html", "", "No registered signal test", "#f1Caption, .src { display: none !important; }"),
    ("02-detectable-effect.png", "index.html", "", "What could the test have detected?"),
    ("03-sharpe-differences.png", "portfolios.html", "", "#leadTitle"),
    ("04-growth-and-drawdown.png", "portfolios.html", "", "#growthTitle"),
    ("05-plan-log.png", "method.html", "#log", "#tlTitle"),
    ("06-return-by-group.png", "signals.html", "", "Is the relation monotonic?"),
]


def panel_for(page, heading_text):
    """Return the visible .panel whose h2 contains the heading text."""
    # A heading given as "#id" is matched by id (some headings are filled in by the page's script).
    inner = page.locator(heading_text) if heading_text.startswith("#") else page.locator("h2", has_text=heading_text)
    panels = page.locator(".panel", has=inner)
    for i in range(panels.count()):
        if panels.nth(i).is_visible():
            return panels.nth(i)
    raise RuntimeError(f"No visible panel with heading containing {heading_text!r}")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        launch = {"executable_path": CHROME} if CHROME else {}
        browser = p.chromium.launch(**launch)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=2)
        # The site defaults to dark; set it explicitly so a saved choice cannot change the output.
        ctx.add_init_script("try { localStorage.setItem('qer-theme', 'dark'); } catch (e) {}")
        for name, html, frag, heading, *extra in SHOTS:
            if ONLY and name not in ONLY:
                continue
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto((ROOT / html).resolve().as_uri() + frag)
            page.wait_for_timeout(1200)  # charts animate in
            panel = panel_for(page, heading)
            panel.scroll_into_view_if_needed()
            page.wait_for_timeout(600)
            # The README pictures leave out the formula boxes (the page keeps them) and add a margin of the page ground colour.
            page.add_style_tag(content=".formula { display: none !important; }" + (extra[0] if extra else ""))
            page.wait_for_timeout(300)
            page.evaluate("window.scrollTo(0, 0)")  # sticky bars then sit at the top of the page, not over the panel
            page.wait_for_timeout(300)
            box = panel.bounding_box()  # with the window at the top, window and page coordinates agree
            pad = 28
            # No margin above the panel (it would show the end of the previous section); margin on the other sides.
            clip = {"x": max(box["x"] - pad, 0), "y": box["y"],
                    "width": box["width"] + 2 * pad, "height": box["height"] + pad}
            page.screenshot(path=str(OUT / name), clip=clip, full_page=True)
            print("wrote", OUT / name, "errors:", errors or "none")
            page.close()
        browser.close()


if __name__ == "__main__":
    main()
