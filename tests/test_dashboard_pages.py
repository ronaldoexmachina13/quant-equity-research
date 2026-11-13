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
        theme = re.findall(r'src="assets/theme\.js\?v=(\d+)"', html)
        assert len(css) == 1 and len(js) == 1 and len(theme) == 1, f"{page}.html: stylesheet {css}, dashboard.js {js}, theme.js {theme}"
        versions[page] = (css[0], js[0], theme[0])
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


def test_interval_markers_are_hollow_or_filled_not_ringed():
    for name in ["index.html", "signals.html", "portfolios.html", "assets/dashboard.js"]:
        assert "ringed" not in read(name)


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


def test_summary_return_risk_cost_table_is_populated_by_script():
    src = read("index.html")
    assert 'id="rrcBody"' in src and 'getElementById("rrcBody").innerHTML' in src


def _light_block():
    return _css().split(':root[data-theme="light"] {')[1].split("}")[0]


def _dark_tokens():
    return set(re.findall(r"(--[a-z0-9-]+):", _css().split(":root {")[1].split("}")[0]))


def test_theme_default_is_a_one_line_change_and_loads_before_the_stylesheet():
    theme = read("assets/theme.js")
    assert re.search(r'^const DEFAULT_THEME = "(dark|light)";$', theme, re.M)
    for page in PAGES:
        html = read(page + ".html")
        assert html.index("assets/theme.js") < html.index("assets/styles.css"), page


def test_both_themes_define_every_colour_token():
    # dark is :root, light is :root[data-theme="light"]; every colour token the charts read must exist in both
    light = set(re.findall(r"(--[a-z0-9-]+):", _light_block()))
    colour = {t for t in _dark_tokens() if t not in {"--mono", "--sans", "--serif", "--panel-border", "--text-primary", "--text-secondary", "--text-muted"}}
    assert colour <= light, sorted(colour - light)


def _hex_tokens(block):
    return {k: v for k, v in re.findall(r"(--[a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})", block)}


def _lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _ratio(a, b):
    hi, lo = sorted([_lum(a), _lum(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_palette_is_near_monochrome_with_one_warm_accent():
    # chalk on slate: every colour token is a warm grey except the single ochre accent and the muted sign colours
    allowed = {"--amber", "--combined", "--combined-text", "--oos", "--pos", "--neg"}
    dark = _hex_tokens(_css().split(":root {")[1].split("\n}\n")[0])
    light = _hex_tokens(_light_block())
    for tokens in (dark, light):
        for name, hexv in tokens.items():
            spread = max(int(hexv[i:i + 2], 16) for i in (1, 3, 5)) - min(int(hexv[i:i + 2], 16) for i in (1, 3, 5))
            assert spread <= 45 or name in allowed, (name, hexv)


def test_dark_ground_is_warm_near_black():
    dark = _hex_tokens(_css().split(":root {")[1].split("\n}\n")[0])
    assert 13 <= int(dark["--bg"][1:3], 16) <= 20 and dark["--bg"][1:3] >= dark["--bg"][5:7]  # near-black, red at least blue: warm


def test_text_colours_reach_4_5_to_1_on_their_ground_in_both_themes():
    dark = _hex_tokens(_css().split(":root {")[1].split("\n}\n")[0])
    light = _hex_tokens(_light_block())
    for tokens in (dark, light):
        for name in ("--text", "--text-strong", "--muted", "--dim", "--momentum-text", "--value-text", "--combined-text", "--amber"):
            assert _ratio(tokens[name], tokens["--bg"]) >= 4.5, (name, tokens[name])


def test_toggle_exists_and_system_setting_no_longer_decides_the_theme():
    js = read("assets/dashboard.js")
    assert 'id="themeToggle"' in js and "qer-theme" in js
    assert "prefers-color-scheme" not in js and "prefers-color-scheme" not in _css()


def test_serif_is_self_hosted_with_the_licence_and_used_for_prose():
    css = _css()
    for f in ("eb-garamond-latin-400-normal.woff2", "eb-garamond-latin-400-italic.woff2", "eb-garamond-latin-600-normal.woff2", "LICENSE-EB-Garamond.txt"):
        assert (ROOT / "assets/fonts" / f).exists(), f
    assert re.search(r"\.hero h1[^{]*\{[^}]*var\(--serif\)", css) and re.search(r"\.caption[^{]*\{[^}]*var\(--serif\)", css)
    assert re.search(r"\.num[^{]*\{[^}]*var\(--mono\)", css)


def test_formulas_are_typeset_on_method_and_under_the_key_exhibits():
    method = read("method.html")
    assert method.count("<math") >= 6
    for name in ("Rank IC", "Quintile spread", "Sharpe difference", "Newey-West variance", "Four-factor regression", "Survivorship scenario adjustment"):
        assert name in method, name
    for page in ("index.html", "signals.html", "portfolios.html", "universe.html"):
        assert "<math" in read(page), page
    assert "katex" not in method.lower()  # MathML only, no script or CDN


def test_no_tiles_no_cards():
    css = _css()
    assert not re.search(r"\.mini-stats\s*\{[^}]*grid-template-columns:\s*repeat", css.split("dark academic-editorial layer")[1])
    for name in ("index.html", "portfolios.html"):
        assert "mini-stats" not in read(name)


def test_no_shadows_and_no_dual_axes():
    css = _css()
    assert "box-shadow" not in css and "text-shadow" not in css
    for name in ["assets/dashboard.js"] + [p + ".html" for p in PAGES]:
        assert "yAxisID" not in read(name), name


def test_summary_leads_with_forest_plots_not_tiles_or_a_finding_box():
    index = read("index.html")
    for ident in ("f1Forest", "f2Forest", "f3Forest"):
        assert f'id="{ident}"' in index
    assert index.index('id="f1Forest"') < index.index('id="mdeTable"')
    assert "familyForest(" in index
    for gone in ("mini-stats", 'id="keyfig"', "hero-finding", 'id="matrix"', 'id="tape"'):
        assert gone not in index, gone
    assert "Specification" not in index and "Specification" in read("method.html")


def test_forest_markers_are_not_coloured_by_significance():
    js = read("assets/dashboard.js")
    body = js.split("function familyForest")[1].split("/* ---------- 1. signal tests")[0]
    assert "excl ? c : cssVar" in body  # fill differs (filled or hollow); the colour is the signal's own
    assert "--pos" not in body and "--neg" not in body


def test_plan_log_sentence_is_on_method_not_in_the_header_strip():
    js, method = read("assets/dashboard.js"), read("method.html")
    chrome = js.split("function renderChrome")[1].split("renderExhibits();")[0]
    assert "planLog" not in chrome and "plan log" not in chrome
    assert "planLogSentence()" in method and 'id="planLogLine"' in method


def test_portfolios_leads_with_the_sharpe_table_and_stacks_drawdown_under_growth():
    html = read("portfolios.html")
    assert html.index('id="leadTable"') < html.index('id="pageTabs"')
    assert 'id="pKeys"' not in html and "mini-stats" not in html and 'id="reading"' not in html
    pane = html.split('id="pane-perf"')[1].split('id="pane-risk"')[0]
    assert 'id="growthChart"' in pane and 'id="ddChart"' in pane and pane.index("growthChart") < pane.index("ddChart")
    assert "portLegend" not in html and "legend-row" not in pane
    assert "afterFit" in html  # shared value-axis width, so the dates line up


def test_monthly_return_heatmap_is_gone():
    for name in ["portfolios.html", "assets/dashboard.js", "assets/styles.css"]:
        text = read(name)
        assert "monthlyHeatmap" not in text and "heatmap" not in text, name


def test_quintile_ladders_share_one_scale_with_spread_strips():
    html = read("signals.html")
    for sig in ("Momentum", "Value", "Combined"):
        assert f'id="qsp{sig}"' in html
    assert "min: yMin, max: yMax" in html and "h: half" in html
