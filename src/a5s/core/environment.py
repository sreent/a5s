"""Which deployment this is, as a band across the top of every page says (Ocean's
EnvironmentBand): production, a staging, a test, or someone's own machine for development, with
the name whoever runs it gives it. The classic mistake isn't made on an administrator's page:
it's doing in production what was meant for a test, on whichever page, so every page says it,
whoever's signed in and before anyone is.

A deployment nobody named is taken as production until someone does: its band says to treat
what's done there as real, and `a5s doctor` says to name it (A5S_ENVIRONMENT)."""

from __future__ import annotations

from typing import Any

from a5s import config

# What each kind of deployment means for whoever's on its pages, as its band says it
ABOUT = {
    "production": "Real people and records: what you do here reaches them.",
    "staging": "Before production: what you do here reaches the people and records it's set up "
               "with alone.",
    "test": "A test: what you do here reaches its test accounts and made-up records alone.",
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
