"""Static-site checks: WCAG AA contrast tokens, table layout and HTML invariants.

These tests parse the committed site files (no browser, no network). The contrast
numbers come from the spec's theme-token table and use the WCAG 2.1 relative
luminance formula. The table rules are checked because `body` wraps anywhere for
long URLs, which must not reach the tables: cells break at word boundaries only
and the `div.table-wrap` scrolls instead (AC-8).
"""

import functools
import re
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"

COMMENT = re.compile(r"/\*.*?\*/", re.S)
CELL_SELECTOR = re.compile(r"(?:^|[\s>+~])(?:table|thead|tbody|tfoot|tr|th|td)$")
UNSAFE_WRAP = {"overflow-wrap": {"anywhere", "break-word"},
               "word-break": {"break-all", "break-word"}}


@functools.cache
def _css_rules() -> tuple[tuple[str, dict[str, str]], ...]:
    """Flatten style.css into (selector group, declarations) pairs.

    At-rule wrappers such as `@media` are dropped, leaving the rules they
    contain in document order (no rule in this stylesheet needs the media
    condition to be evaluated to check its declarations).
    """
    text = COMMENT.sub("", (SITE / "style.css").read_text())
    rules: list[tuple[str, dict[str, str]]] = []
    stack: list[str] = []
    buffer = ""
    for char in text:
        if char == "{":
            stack.append(buffer.strip())
            buffer = ""
        elif char == "}":
            prelude = stack.pop() if stack else ""
            if prelude and not prelude.startswith("@"):
                rules.append((prelude, _declarations(buffer)))
            buffer = ""
        else:
            buffer += char
    return tuple(rules)


def _declarations(body: str) -> dict[str, str]:
    declarations: dict[str, str] = {}
    for chunk in body.split(";"):
        name, separator, value = chunk.partition(":")
        if separator:
            declarations[name.strip().lower()] = value.strip()
    return declarations


def _parts(selector_group: str) -> list[str]:
    return [part.strip() for part in selector_group.split(",")]


def _decls(selector_group: str, parts: tuple[str, ...] | None = None) -> dict[str, str]:
    """Merged declarations of every rule whose selector group contains `parts`.

    With `parts` omitted, every rule whose selector subject is a table, row or
    cell is collected, i.e. what actually reaches a `td`/`th` box.
    """
    merged: dict[str, str] = {}
    for selector_group, declarations in _css_rules():
        selected = _parts(selector_group)
        if parts is None:
            matches = any(CELL_SELECTOR.search(part) for part in selected)
        else:
            matches = any(part in parts for part in selected)
        if matches:
            merged.update(declarations)
    return merged


def test_table_cells_break_words_at_boundaries_only():
    cells = _decls(None)
    assert cells.get("overflow-wrap") == "normal"
    assert cells.get("word-break") == "normal"
    assert cells.get("hyphens") == "none"
    for selector_group, declarations in _css_rules():
        if not any(CELL_SELECTOR.search(part) for part in _parts(selector_group)):
            continue
        for prop, unsafe in UNSAFE_WRAP.items():
            assert declarations.get(prop) not in unsafe, (
                f"{selector_group!r} sets {prop}: {declarations[prop]}"
            )
    # Long URLs in the subscribe list still wrap: body keeps `anywhere`.
    assert _decls(None, ("body",)).get("overflow-wrap") == "anywhere"


def test_table_headers_and_short_cells_do_not_wrap():
    assert _decls(None, ("thead th",)).get("white-space") == "nowrap"
    assert _decls(None, ("#standings tbody th", "#standings tbody td")).get(
        "white-space"
    ) == "nowrap"
    for column in (1, 2, 3):
        selector = f"#schedule tbody td:nth-child({column})"
        assert _decls(None, (selector,)).get("white-space") == "nowrap", selector


def test_tables_scroll_inside_their_wrapper():
    assert _decls(None, ("table",)).get("width") == "100%"
    assert _decls(None, ("#standings table",)).get("min-width") == "max-content"
    # Schedule long-text columns wrap, so they get a width floor (long names
    # never squeeze a column into one letter per line).
    for column in (4, 5, 6):
        selector = f"#schedule tbody td:nth-child({column})"
        floor = _decls(None, (selector,)).get("min-width", "")
        assert re.fullmatch(r"\d+(?:\.\d+)?rem", floor), (selector, floor)


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
    assert "<footer" not in html, "footer was removed on purpose"
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
