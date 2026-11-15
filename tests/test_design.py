"""The look every page of a5s shares (docs/design.md): Ocean's tokens, in two layers, and its
type, IBM Plex, which a5s bundles. Each colour that carries text reads against what it sits
on, as WCAG's AA asks, in light and in dark, so a brand that changes the palette finds out here
if it reads less well."""

import re

import httpx

from a5s.core import web
from conftest import ROOT
from test_webchat import channels

CSS = (ROOT / "src" / "a5s" / "core" / "webchat" / "app.css").read_text()
DECLARED = re.compile(r"--([\w-]+):\s*([^;]+);")
DARK = "@media (prefers-color-scheme: dark)"


def _tokens(text: str) -> dict[str, str]:
    return dict(DECLARED.findall(text))


def themes() -> dict[str, dict[str, str]]:
    primitives = _tokens(CSS[CSS.index("/* Primitives"):CSS.index("/* Meanings")])
    light = {**primitives, **_tokens(CSS[CSS.index("/* Meanings"):CSS.index(DARK)])}
    dark = CSS.index(DARK)
    return {"light": light, "dark": {**light, **_tokens(CSS[dark:CSS.index("\n}\n", dark)])}}


def colour(theme: dict[str, str], name: str) -> str:
    value = theme[name].strip()
    while found := re.fullmatch(r"var\(--([\w-]+)\)", value):
        value = theme[found[1]].strip()
    assert re.fullmatch(r"#[0-9a-f]{6}", value), f"--{name} is {value}, not a colour"
    return value


def contrast(a: str, b: str) -> float:
    def luminance(hex_colour: str) -> float:
        def channel(c: float) -> float:
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
        return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


TEXT = [  # text, and what it's on: 4.5 to 1
    *(("text", on) for on in ("page", "surface", "sunken", "you", "agent", "a5s")),
    *(("muted", on) for on in ("page", "surface", "sunken")),
    ("faint", "page"), ("faint", "surface"),
    ("accent", "page"), ("accent", "surface"), ("accent", "accent-soft"),
    ("accent-text", "accent"), ("accent-text", "accent-strong"),
    *((tone, f"{tone}-bg") for tone in ("reads", "writes", "changes", "outside", "own",
                                         "good", "warn", "bad", "idle")),
]
MARKS = [("focus", "surface"), ("agent-tone", "surface"), ("surface", "agent-tone")]  # 3 to 1


def test_every_colour_that_carries_text_reads_against_what_it_is_on_in_light_and_dark():
    short = [f"{name}: {fg} on {on} is {ratio:.2f}"
             for name, theme in themes().items()
             for pairs, least in ((TEXT, 4.5), (MARKS, 3.0))
             for fg, on in pairs
             if (ratio := contrast(colour(theme, fg), colour(theme, on))) < least]
    assert short == []


def test_the_meanings_name_only_primitives_so_a_brand_changes_the_primitives_alone():
    light = _tokens(CSS[CSS.index("/* Meanings"):CSS.index(DARK)])
    dark = CSS.index(DARK)
    colours = [v for v in (*light.values(), *_tokens(CSS[dark:CSS.index("\n}\n", dark)]).values())
               if "#" in v]
    assert colours == []  # every hex value is a primitive's


def test_the_pages_load_their_type_from_a5s_and_nowhere_else(stack):
    assert web.FONTS == ("plex-mono-400.woff2", "plex-mono-500.woff2", "plex-sans-400.woff2",
                         "plex-sans-500.woff2", "plex-sans-600.woff2", "plex-sans-700.woff2")
    assert "https:" not in CSS and "//" not in re.sub(r"/\*.*?\*/", "", CSS, flags=re.DOTALL)
    with channels(stack) as url:
        font = httpx.get(f"{url}/chat/fonts/plex-sans-400.woff2")
        assert httpx.get(f"{url}/chat/fonts/OFL-plex-sans.txt").status_code == 404
        assert httpx.get(f"{url}/chat/fonts/..%2Fapp.js").status_code == 404
        page = httpx.get(f"{url}/chat/")
    assert font.status_code == 200 and font.headers["content-type"] == "font/woff2"
    assert font.content[:4] == b"wOF2"
    assert "font-src 'self'" in page.headers["content-security-policy"]
    assert "default-src 'none'" in page.headers["content-security-policy"]
