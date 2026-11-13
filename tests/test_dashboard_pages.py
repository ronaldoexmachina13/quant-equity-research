"""
Structural checks on the static dashboard pages. They read the HTML and the
shared script as text, so they need no browser. They guard the design rules
that are easy to break by accident: no external scripts, labelled charts,
a readable type floor, no em dashes, working internal links, and a source
line source for every numbered exhibit.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGES = ["index", "signals", "portfolios", "universe", "method"]
EM_DASH = "—"


def read(name):
    return (ROOT / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("page", PAGES)
def test_no_external_scripts(page):
    scripts = re.findall(r'<script[^>]+src="([^"]+)"', read(page + ".html"))
    assert scripts, "page loads no scripts"
    assert all(not s.startswith(("http:", "https:", "//")) for s in scripts)


@pytest.mark.parametrize("page", PAGES)
def test_every_canvas_has_a_description(page):
    html = read(page + ".html")
    for tag in re.findall(r"<canvas\b[^>]*>", html):
        assert 'role="img"' in tag and "aria-label=" in tag, tag


@pytest.mark.parametrize("page", PAGES)
def test_local_assets_and_links_exist(page):
    html = read(page + ".html")
    for ref in re.findall(r'(?:src|href)="([^"#?:]+\.(?:js|css|html|svg))', html):
        assert (ROOT / ref).exists(), ref


@pytest.mark.parametrize("page", PAGES)
def test_exhibit_sources_are_committed_csvs(page):
    html = read(page + ".html")
    for attr in re.findall(r'data-src="([^"]+)"', html):
        for path in attr.split("; "):
            if "*" in path:
                assert list((ROOT / "results").glob(Path(path).name)), path
            else:
                assert (ROOT / path).exists(), path


@pytest.mark.parametrize("name", [p + ".html" for p in PAGES] + ["assets/dashboard.js", "assets/styles.css"])
def test_no_em_dashes(name):
    assert EM_DASH not in read(name)


def test_stylesheet_and_dashboard_script_carry_one_cache_version_on_every_page():
    # The version in ?v= makes returning visitors fetch a changed file instead of a cached copy.
    # The stylesheet and the shared script change together, so every page must ask for the same version of both.
    versions = {}
    for page in PAGES:
        html = read(page + ".html")
        css = re.findall(r'href="assets/styles\.css\?v=(\d+)"', html)
        js = re.findall(r'src="assets/dashboard\.js\?v=(\d+)"', html)
        assert len(css) == 1 and len(js) == 1, f"{page}.html: stylesheet {css}, dashboard.js {js}"
        versions[page] = (css[0], js[0])
    assert len({v for pair in versions.values() for v in pair}) == 1, versions


def test_type_floor_is_eleven_pixels():
    css = read("assets/styles.css")
    for value, unit in re.findall(r"font-size:\s*([0-9.]+)(px|rem)", css):
        px = float(value) * (16 if unit == "rem" else 1)
        assert px >= 10.9, f"font-size {value}{unit} is below 11 px"


def test_animation_is_off():
    assert "Chart.defaults.animation = false" in read("assets/dashboard.js")


def test_uppercase_only_on_table_heads():
    css = read("assets/styles.css")
    for selector, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", css):
        if "text-transform: uppercase" in body:
            assert re.search(r"\bth\b", selector), selector.strip()


def test_heatmap_uses_one_hue_and_no_red_green():
    js = read("assets/dashboard.js")
    assert "rgba(229,99,107" not in js and "rgba(79,191,139" not in js
    assert "--hm-rgb" in read("assets/styles.css")


def test_interval_markers_are_hollow_or_filled_not_ringed():
    for name in ["index.html", "signals.html", "portfolios.html", "assets/dashboard.js"]:
        assert "ringed" not in read(name)


def test_summary_is_restructured():
    index, method = read("index.html"), read("method.html")
    assert "mini-stats" not in index and 'id="keyfig"' in index
    assert "Specification" not in index and "Specification" in method
    assert 'id="tape"' not in index
    assert "Newey-West t" in index


def test_summary_counts_are_not_typed_into_the_html():
    # the headline counts are computed from the data blocks at run time
    index = read("index.html")
    for typed in ["0 of 33", "2 of 18", "158 of 294"]:
        assert typed not in index.split("<script>")[0]


@pytest.mark.parametrize("name", [p + ".html" for p in PAGES] + ["assets/dashboard.js"])
def test_copy_rules(name):
    text = read(name)
    assert "It does not show" not in text
    assert "if independent" not in text
    assert " and agree" not in text and " agree with" not in text


def test_method_has_glossary_and_build_note():
    method = read("method.html")
    assert 'id="glossary"' in method and "How this was built" in method


def _css():
    return (ROOT / "assets" / "styles.css").read_text(encoding="utf-8")


def test_light_theme_follows_system_setting_and_defines_every_token():
    css = _css()
    dark = css.split("@media (prefers-color-scheme: light)")[0]
    light = css.split("@media (prefers-color-scheme: light)")[1].split("* { box-sizing")[0]
    tokens = set(re.findall(r"(--[a-z0-9-]+):", dark.split(":root {")[1].split("}")[0]))
    needed = {"--bg", "--text", "--muted", "--grid", "--zero", "--combined", "--value", "--momentum", "--amber", "--tip-bg", "--hm-rgb"}
    assert needed <= tokens
    for t in needed:
        assert t + ":" in light, f"light theme lacks {t}"


def test_light_palette_matches_validated_values():
    # the three series colours passed the colour-blind validator on white (light_palette_validation.txt)
    css = _css()
    light = css.split("@media (prefers-color-scheme: light)")[1]
    for hexv in ("#0F8B7A", "#3B5FC0", "#C4501F"):
        assert hexv in light


def test_print_block_uses_light_tokens_and_shows_every_tab():
    css = _css()
    pr = css.split("@media print")[1]
    assert "--bg: #FFFFFF" in pr and ".tabpane[hidden] { display: block" in pr


@pytest.mark.parametrize("name", ["assets/dashboard.js", "index.html", "signals.html", "portfolios.html", "universe.html", "method.html"])
def test_charts_read_colours_from_tokens(name):
    src = (ROOT / name).read_text(encoding="utf-8")
    assert not re.search(r"(?:[Cc]olor|fill|stroke|background)\s*[:=]\s*[\"']#[0-9A-Fa-f]{6}", src), name


def test_summary_has_plain_contents_list_not_cards():
    src = read("index.html")
    assert 'class="contents"' in src and "Open &rarr;" not in src and "index-row" not in src


def test_empty_cells_say_n_a_not_a_dash():
    for name in ("index.html", "portfolios.html", "signals.html", "method.html"):
        assert '"–"' not in read(name) and "<td class=\"cell\">&ndash;</td>" not in read(name), name


def test_amber_is_not_used_for_the_logo_or_series_text():
    js = (ROOT / "assets" / "dashboard.js").read_text(encoding="utf-8")
    logo = js.split('class="logo"')[1].split("</svg>")[0]
    assert "amber" not in logo and "F0A83A" not in logo


def test_light_series_text_reaches_4_5_to_1_on_white():
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    css = (ROOT / "assets" / "styles.css").read_text(encoding="utf-8")
    light = css.split("@media (prefers-color-scheme: light)")[1].split("* { box-sizing")[0]
    for name in ("momentum", "value", "combined"):
        hexv = re.search(rf"--{name}-text: (#[0-9A-Fa-f]{{6}})", light).group(1)
        assert (1.05) / (lum(hexv) + 0.05) >= 4.5, name


def test_summary_return_risk_cost_table_is_populated_by_script():
    src = read("index.html")
    assert 'id="rrcBody"' in src and 'getElementById("rrcBody").innerHTML' in src
