"""The health page (docs/model-execution.md): each model's day, measured — its calls,
failures, stalls, mean time, whether its SLO gates it, and its canary scores — for the
engineers and the release approver, whose evidence a model change or a restore is."""
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException

from a5s import db
from a5s.contract import RELEASE_APPROVER, Person
from a5s.core import canaries, health, suspension, web
from a5s.core import studio_models as shapes
from a5s.core.releases import engineer


def reads(person: Person, team: str) -> bool:
    """Whether someone may read the models' health: the release approver, who puts a stopped
    model back, and the engineers, anyone in the team that runs a5s, as a release counts them.
    The sidebar asks the same, so it lists the page exactly where it opens (round 17, C3)."""
    return RELEASE_APPROVER in person.roles or engineer(person, team)


def health_now(gw: Any, days: int = 1, person: Person | None = None) -> dict:
    """The page's data: each model's day from the ledger, and its canaries' latest day; and, for
    a stopped model, whom putting it back would reach, said before they do to whoever may put it
    back, the release approver from outside the team that runs a5s, as the core lets them: which
    instances run on it, and whom they serve, are theirs to weigh, not every engineer's to read."""
    rows = health.report(gw.url, gw.scenario.name, days=days)
    reaches: dict[str, str] = {}
    if person is not None and suspension.lifts(person, gw.cfg.team) and any(
            row["gated_at"] for row in rows):
        with db.transaction(gw.url) as conn:
            reaches = {row["model"]: health.reached(*health.reach(conn, gw.scenario, row["model"]))
                       for row in rows if row["gated_at"]}
    scores = canaries.scorecard(gw.url, gw.scenario.name, days=days)
    by_model: dict[str, dict[str, int]] = {}
    for row in scores:
        found = by_model.setdefault(row["model"], {"passed": 0, "failed": 0})
        found["passed" if row["passed"] else "failed"] += 1
    return {
        "days": days,
        "models": [{
            "model": row["model"], "calls": row["calls"], "failed": row["failed"],
            "stalls": row["stalls"], "mean_seconds": row["mean_seconds"],
            "gated_at": row["gated_at"].isoformat() if row["gated_at"] else None,
            "canary_passed": by_model.get(row["model"], {}).get("passed", 0),
            "canary_failed": by_model.get(row["model"], {}).get("failed", 0),
            **({"reaches": reaches[row["model"]]} if row["model"] in reaches else {}),
        } for row in rows],
    }


def router(gw: Any) -> APIRouter:
    """The health page and its API, for the channels app to include."""

    def someone(authorization: str | None = Header(default=None)) -> Person:
        person = web.known(gw, authorization)
        if not reads(person, gw.cfg.team):
            raise HTTPException(403, "the health page is for the team that runs a5s and the "
                                     "release approver")
        return person

    api = APIRouter()

    @api.get("/health/api", **shapes.answers(shapes.HealthNow))
    def health_page(person: Annotated[Person, Depends(someone)]) -> dict:
        return health_now(gw, person=person)

    return api
