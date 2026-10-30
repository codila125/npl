"""Static-site checks: WCAG AA contrast tokens and HTML skeleton invariants.

These tests parse the committed site files (no browser, no network). The contrast
numbers come from the spec's theme-token table and use the WCAG 2.1 relative
luminance formula.
"""

import re
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"


def _parse_tokens() -> dict[str, dict[str, str]]:
    css = (SITE / "style.css").read_text()
    tokens: dict[str, dict[str, str]] = {}
    for theme in ("light", "dark"):
        marker = f"/* tokens:{theme} */"
        assert marker in css, f"missing documented token block for {theme}"
        start = css.index(marker) + len(marker)
        end = css.index("}", start)
        block = css[start:end]
        values = {}
        for name in ("bg", "fg", "muted", "line", "rule", "accent"):
            match = re.search(rf"--{name}\s*:\s*(#[0-9a-fA-F]{{3,8}})\b", block)
            assert match, f"{theme} block is missing --{name}"
            values[name] = match.group(1)
        tokens[theme] = values
    return tokens


def _channel(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(hex_color: str) -> float:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(ch * 2 for ch in hex_color)
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def _contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def test_token_contrast_ratios_both_themes():
    tokens = _parse_tokens()
    assert set(tokens) == {"light", "dark"}
    for theme, t in tokens.items():
        assert _contrast(t["fg"], t["bg"]) >= 7, theme
        assert _contrast(t["muted"], t["bg"]) >= 4.5, theme
        assert _contrast(t["accent"], t["bg"]) >= 4.5, theme
        assert _contrast(t["line"], t["bg"]) >= 3, theme


def test_index_theme_init_runs_before_stylesheet():
    html = (SITE / "index.html").read_text()
    assert '<meta name="viewport"' in html
    init = html.index("npl-theme")
    stylesheet = html.index('rel="stylesheet"')
    assert init < stylesheet, "theme-init script must precede the stylesheet link"


def test_index_landmarks_and_skip_link():
    html = (SITE / "index.html").read_text()
    assert "<header" in html
    assert '<nav aria-label="Sections"' in html
    assert "<main" in html
    assert "<footer" in html
    assert "Skip to content" in html
    assert html.index("Skip to content") < html.index("<header"), "skip link must be first"


def test_index_has_no_images_or_external_resource_origins():
    html = (SITE / "index.html").read_text()
    css = (SITE / "style.css").read_text()
    assert "<img" not in html
    assert 'src="http' not in html
    assert not re.search(r'<link[^>]+rel="stylesheet"[^>]+href="http', html), (
        "no external stylesheets"
    )
    assert "url(http" not in css
    assert "@import" not in css
