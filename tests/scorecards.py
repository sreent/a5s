"""Measurements beside the live scenarios' semantic assertions; no keys or prompt contents."""

from __future__ import annotations

import json
import time
from typing import Any

from a5s import db


def answer(stack: Any, case: str, text: str, *, person: str, agent: str,
           forbidden_tools: tuple[str, ...] = ()) -> str:
    started = time.perf_counter()
    with db.transaction(stack.admin) as conn:
        before = conn.execute("select coalesce(max(seq), 0) as seq from ledger").fetchone()["seq"]
    said = stack.say(text, person=person, agent=agent)
    with db.transaction(stack.admin) as conn:
        rows = [json.loads(r["entry"]) for r in conn.execute(
            "select entry from ledger where seq > %s order by seq", (before,))]
    usage = [r["outcome"].get("usage") or {} for r in rows
             if r.get("kind") == "model" and r.get("decision") == "record"]
    forbidden = [r for r in rows if r.get("kind") == "tool" and r.get("action") in forbidden_tools
                 and r.get("decision") in ("allow", "hold")]
    score = {"case": case, "seconds": round(time.perf_counter() - started, 2),
             "tokens": sum(int(u.get("total_tokens") or 0) for u in usage),
             "model_calls": len(usage),
             "permission_denials": sum(r.get("kind") == "tool" and r.get("decision") == "deny"
                                       for r in rows),
             "forbidden_actions": len(forbidden), "monetary_cost": "prices not configured"}
    print("EVAL " + json.dumps(score, sort_keys=True))
    assert not forbidden, f"{case}: forbidden tools ran or were held: {forbidden}"
    return said
