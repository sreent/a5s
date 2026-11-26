"""Which deployment this is, as a band across the top of every page says (Ocean's
EnvironmentBand): production, a staging, a test, or someone's own machine for development, with
the name whoever runs it gives it. The classic mistake isn't made on an administrator's page:
it's doing in production what was meant for a test, on whichever page, so every page says it,
whoever's signed in and before anyone is.

A deployment nobody named is taken as production until someone does: its band says to treat
what's done there as real, and `a5s doctor` says to name it (A5S_ENVIRONMENT)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from a5s import config

# The scenarios a5s ships, whose people's private keys are in a5s's repository beside their
# public keys, so anyone with it can sign as them: fine for a test with made-up records, never
# where a deployment says it's production or staging (round 17, D3)
SHIPPED = ("sample", "master-data", "service-desk", "software-delivery", "procure-to-pay")
REAL = ("production", "staging")

# What each kind of deployment means for whoever's on its pages, as its band says it
ABOUT = {
    "production": "Real people and records: what you do here reaches them.",
    "staging": "Before production, for the people and records it's set up with.",
    "test": "A test, for test accounts and made-up records.",
    "development": "On this machine, for development: a5s takes people's word for who they are.",
}
UNNAMED = "Unnamed deployment"
UNNAMED_ABOUT = ("Treat what you do here as real: whoever runs a5s hasn't named this deployment "
                 "yet (A5S_ENVIRONMENT).")


def here(development: bool) -> dict[str, Any]:
    """This deployment, as every page's band says it: its kind, its name and what that means,
    and whether anyone named it. Beside `a5s dev`, development, unless it's named otherwise."""
    kind = config.ENVIRONMENT.read() or ("development" if development else None)
    if kind is None:  # taken as production, which is what a mistake would cost most in
        return {"kind": "production", "name": UNNAMED, "about": UNNAMED_ABOUT, "named": False}
    return {"kind": kind, "name": config.ENVIRONMENT_NAME.read() or kind.capitalize(),
            "about": ABOUT[kind], "named": True}


def published_keys_in(scenario_dir: Path, root: Path) -> list[str]:
    """Whom the directory gives a key a5s publishes with its own scenarios, by their ids:
    anyone with a5s's repository holds the private key, so could sign as them."""
    shipped = {key.read_text(encoding="utf-8").strip() for name in SHIPPED
               for key in (root / "scenarios" / name / "keys").glob("*.pub")}
    return sorted(key.stem for key in (scenario_dir / "keys").glob("*.pub")
                  if key.read_text(encoding="utf-8").strip() in shipped)


def published_refused(scenario_dir: Path, root: Path) -> str | None:
    """Why a deployment that says it's production or staging can't run on the keys its
    directory gives, if it can't: some are keys a5s publishes."""
    kind = config.ENVIRONMENT.read()
    if kind not in REAL or not (published := published_keys_in(scenario_dir, root)):
        return None
    named = ", ".join(published[:5]) + (f" and {len(published) - 5} more" if len(published) > 5
                                         else "")
    return (f"this deployment says it's {kind}, and its directory gives {named} keys a5s "
            "publishes with its own scenarios, whose private keys anyone with a5s's repository "
            "holds, so anyone could approve, decide and sign releases as them: give each a key "
            "of their own, made with `a5s keygen`, or name the deployment a test "
            "(A5S_ENVIRONMENT; docs/first-day.md)")
