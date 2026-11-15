"""The look every page of a5s shares (docs/design.md): Ocean, from its one source, sreent/ocean,
copied into a5s at the commit ocean.json pins, with its tokens in two layers and its type, IBM
Plex. Each colour that carries text reads against what it sits on, as WCAG's AA asks, in light and
in dark, so a brand that changes the palette finds out here if it reads less well; and the copy
is Ocean's as that commit has it, never changed here."""

import hashlib
import json
import re

import httpx
from playwright.sync_api import expect

from a5s.core import web
from conftest import ROOT, accessible
from test_ui_pages import shot
from test_webchat import channels

OCEAN = ROOT / "src" / "a5s" / "core" / "webchat" / "ocean"
CSS = (OCEAN / "css" / "tokens.css").read_text()
OWN = (ROOT / "src" / "a5s" / "core" / "webchat" / "app.css").read_text()  # a5s's own, beside it
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
    *(("text", on) for on in ("page", "surface", "sunken", "you", "agent", "own-message")),
    *(("muted", on) for on in ("page", "surface", "sunken")),
    ("faint", "page"), ("faint", "surface"),
    ("accent", "page"), ("accent", "surface"), ("accent", "accent-soft"),
    ("accent-text", "accent"), ("accent-text", "accent-strong"),
    ("text", "accent-soft"), ("changes", "sunken"),  # a traced value; a change, on a decision
    ("muted", "agent-tone-soft"), ("agent-tone", "agent-tone-soft"),  # the step an agent is on
    ("surface", "bad"), ("surface", "text"),  # the danger button; a hint
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


def test_the_copy_of_ocean_is_oceans_as_its_pinned_commit_has_it():
    pinned = json.loads((OCEAN / "ocean.json").read_text())
    assert pinned["repository"] == "https://github.com/sreent/ocean"
    assert re.fullmatch(r"[0-9a-f]{40}", pinned["commit"])
    found = {str(p.relative_to(OCEAN)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in OCEAN.rglob("*") if p.is_file() and p.name != "ocean.json"}
    assert found == pinned["files"]  # changed in sreent/ocean, and taken with deploy/ocean.sh


def _selectors(text: str) -> set[str]:
    """Each selector a stylesheet styles, as it's written, whatever media it's for."""
    text = re.sub(r"@[^{;]+\{", "", re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL))
    return {" ".join(s.split()) for found in re.finditer(r"([^{}@;]+)\{", text) for s in found[1].split(",")}


def test_a5s_restyles_none_of_oceans_pieces_so_ocean_stays_the_one_source():
    """The studio's and the chat's own stylesheets compose Ocean's pieces into their pages and
    style none of them: a piece a5s needs, or a change to one, is made in sreent/ocean first."""
    ocean = _selectors((OCEAN / "css" / "components.css").read_text() + (OCEAN / "css" / "charts.css").read_text())
    for own in (ROOT / "studio" / "src" / "studio.css", ROOT / "src" / "a5s" / "core" / "webchat" / "app.css"):
        both = sorted(_selectors(own.read_text()) & ocean)
        assert both == [], f"{own.name} restyles Ocean's {both}: change them in sreent/ocean"


def test_the_pages_load_their_type_from_a5s_and_nowhere_else(stack):
    assert sorted(p for p in web.OCEAN_FILES if p.startswith("fonts/")) == [
        f"fonts/plex-{face}.woff2" for face in ("mono-400", "mono-500", "sans-400", "sans-500",
                                                "sans-600", "sans-700")]
    for css in (CSS, (OCEAN / "css" / "components.css").read_text(), OWN):
        assert "https:" not in css and "//" not in re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    with channels(stack) as url:
        font = httpx.get(f"{url}/chat/ocean/fonts/plex-sans-400.woff2")
        tokens = httpx.get(f"{url}/chat/ocean/css/tokens.css")
        assert httpx.get(f"{url}/chat/ocean/fonts/OFL-plex-sans.txt").status_code == 404
        assert httpx.get(f"{url}/chat/ocean/fonts/..%2F..%2Fapp.js").status_code == 404
        assert httpx.get(f"{url}/chat/ocean/css/ocean.json").status_code == 404
        page = httpx.get(f"{url}/chat/")
    assert font.status_code == 200 and font.headers["content-type"] == "font/woff2"
    assert font.content[:4] == b"wOF2"
    assert tokens.status_code == 200 and tokens.text == CSS
    assert "font-src 'self'" in page.headers["content-security-policy"]
    assert "default-src 'none'" in page.headers["content-security-policy"]
    assert page.text.index("/chat/ocean/css/tokens.css") < page.text.index("/chat/app.css")


# The showcase: each piece pages are made of, as pages use it

PIECES = ("colours", "type", "buttons", "people", "traced", "approval", "facts", "ladder",
          "timeline", "journey", "confirm")


def showcase(browser, url: str, errors: list[str]):
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.on("console", lambda message: message.type == "error" and errors.append(message.text))
    page.goto(f"{url}/studio/design")
    page.wait_for_selector("[data-piece=confirm]", timeout=30000)
    return page


def test_the_showcase_draws_each_piece_and_axe_finds_nothing_amiss_light_or_dark(approving,
                                                                                browser):
    errors: list[str] = []
    page = showcase(browser, approving, errors)
    assert [p for p in PIECES if page.locator(f"[data-piece={p}]").count() != 1] == []
    accessible(page)
    shot(page, "design")
    assert errors == []  # nothing the pages' policy refused, nor anything else


def test_each_piece_works_from_the_keyboard(approving, browser):
    errors: list[str] = []
    page = showcase(browser, approving, errors)
    # A traced value opens to say where it comes from, and Escape puts focus back on it
    page.locator("button.traced").focus()
    page.keyboard.press("Enter")
    trail = page.get_by_role("dialog", name="Where it comes from")
    trail.wait_for()
    assert "Q-1001" in trail.inner_text()
    page.keyboard.press("Escape")
    trail.wait_for(state="detached")
    expect(page.locator("button.traced")).to_be_focused()
    # A hint shows to whoever tabs to what it's about
    page.get_by_role("button", name="What do these mean?").focus()
    assert "Coral" in page.get_by_role("tooltip").inner_text()
    page.keyboard.press("Escape")
    # Deleting asks first, with focus on keeping it: Escape keeps it, and saying so deletes it
    page.get_by_role("button", name="Delete this draft").click()
    asking = page.get_by_role("dialog", name="Delete the draft of scout?")
    expect(asking).to_be_visible()
    expect(asking.get_by_role("button", name="Keep it")).to_be_focused()
    page.keyboard.press("Escape")
    asking.wait_for(state="hidden")
    page.get_by_role("button", name="Delete this draft").click()
    page.get_by_role("button", name="Delete it").click()
    page.get_by_text("The draft is gone.").wait_for()
    # A decision says how it went
    page.locator("[data-piece=approval]").get_by_role("button", name="Approve").click()
    page.get_by_text("You approved it.").wait_for()
    assert errors == []
