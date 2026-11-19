"""The health page (docs/model-execution.md): each model's day, measured — its calls,
failures, stalls, mean time, whether its SLO gates it, and its canary scores — for the
engineers and the release approver, whose evidence a model change or a restore is."""
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException

from a5s.contract import RELEASE_APPROVER, Person
from a5s.core import canaries, health, web
from a5s.core import studio_models as shapes
from a5s.core.releases import ENGINEER


def health_now(gw: Any, days: int = 1) -> dict:
    """The page's data: each model's day from the ledger, and its canaries' latest day."""
    rows = health.report(gw.url, gw.scenario.name, days=days)
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
        } for row in rows],
    }


def router(gw: Any) -> APIRouter:
    """The health page and its API, for the channels app to include."""

    def someone(authorization: str | None = Header(default=None)) -> Person:
        person = web.known(gw, authorization)
        if not ({RELEASE_APPROVER, ENGINEER} & set(person.roles)) and not any(
                role.startswith(ENGINEER + ":") for role in person.roles):
            raise HTTPException(403, "the health page is for the engineers and the "
                                     "release approver")
        return person

    api = APIRouter()

    @api.get("/health/api", **shapes.answers(shapes.HealthNow))
    def health_page(person: Annotated[Person, Depends(someone)]) -> dict:
        return health_now(gw)

    return api
