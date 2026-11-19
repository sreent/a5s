"""What a version of the settings would do differently (docs/administration.md): the tool calls
agents made in the last four weeks, each decided again, as the version in force decides it and
as the new version would, so whoever reviews or approves a version sees what it would make
alone, hold for a person or refuse that the one in force doesn't, for which instances, tools and
parts, before they sign. A change to one part can reach further than its words say: this shows
how far, in what agents really did.

Each call is decided by the gateway's own policy and its own working out of a call's level,
scope and whether it's past a limit (core/parts.py, core/counts.py), from what the ledger kept of
it: the tool, the records it named, whom its run acted for, and whether the run had read content
from outside. Whether a call was past a limit is counted from the ledger too, by core/counts.py's
rules: what the call's run, or its task, and each person it was asked for had had made or held of
its type before it, among the calls read. It's read in the channels app, which decides nothing:
it shows a5s's caps as the core sealed them (core/samples.py), and the gateway decides every call
itself, as ever.

What it can't know, it says: it decides the agents' tool calls again and nothing else, so it
names what else a version changes that it doesn't decide again, such as whom an instance serves
or which models may answer; each call is decided as the directory, the agents' releases, the
records' parts and a5s's caps stand now; and a change someone asked for of their own records
counts as theirs only where the decision recorded shows it was.

Each preview takes a few seconds of the channels app's processor, so it's worked out once for a
version, a reader and the ledger as it stands, kept a few minutes, and only so many at once.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
import threading
import time
from collections import Counter, OrderedDict, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from a5s import db
from a5s.contract import InstanceSettings, Person, Settings
from a5s.core import counts, groups, languages, memberships, parts, registry, samples, studio, words
from a5s.core.policy import OWN, Decision

log = logging.getLogger(__name__)

DAYS = 28
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
MOST = 2000  # the latest calls of the period, at most, it decides again
WORDS = {"allow": "made alone", "hold": "held for a person to decide", "deny": "refused"}
# What refuses a call apart from policy, the same under any version: never decided again. The
# gateway's own refusals, as it names them, so none it adds is missed (round 14)
NOT_POLICY = OWN
# Whom a run for nobody counts against, of the type of action's limit for each person in 30
# days: its instance, among its other runs for nobody, as core/counts.py counts them
NOBODY = "\0"
ABOUT = ("It decides again the agents' tool calls, and nothing else: not which models may "
         "answer, whom an instance serves, whom it asks or hands conversations to, or what "
         "shadows do. Each call is decided as the directory, the agents' releases, the records' "
         "parts and a5s's caps stand now. A change someone asked for of their own records counts "
         "as theirs only where the decision recorded shows it was.")
# What a version changes that it doesn't decide again, in words (round 14)
UNDECIDED = {
    "classes": ("It changes the classes of data, which decide which models may answer: it "
                "doesn't decide the agents' model calls again."),
    "serves": "It changes whom {instance} serves, which it doesn't decide again.",
    "model": "It changes which model {instance} runs on, which it doesn't decide again.",
    "asks": "It changes whom {instance} may ask, which it doesn't decide again.",
    "hands_to": "It changes whom {instance} may hand conversations to, which it doesn't decide again.",
    "shadows": "It changes what {instance} shadows, which it doesn't decide again.",
    "spending": ("It changes what agents may spend, which decides when they stop for the month: "
                 "it doesn't decide that again."),
    "choices": "It changes the data protection officer's choices, which it doesn't decide again.",
}
KEEP = 300  # seconds a preview is kept for whoever saw it, while the ledger stays as it was
KEPT_MOST = 64  # previews kept at once, the latest
AT_ONCE = 2  # previews worked out at once in each process: each takes a few seconds of it
WAIT = 30  # seconds one waits its turn, at most: past it, a review shows without it
_kept: OrderedDict[tuple[str, ...], tuple[float, dict[str, Any]]] = OrderedDict()
_keeping = threading.Lock()
_working = threading.BoundedSemaphore(AT_ONCE)


@dataclass(frozen=True)
class Call:
    """A tool call as the ledger kept it, and its run as the core kept it."""

    seq: int
    at: datetime
    instance: str
    tool: str
    keys: tuple[str, ...]  # the records it named
    decision: str  # allow, hold or deny, as it was decided then
    run: dict[str, Any]  # its run: the trigger, whom it acted for, whether it read outside


def preview(conn: db.Connection, gw: Any, before: Settings | None, after: Settings,
            approvers: list[str], now: datetime, viewer: Person | None = None) -> dict[str, Any]:
    """What `after` would decide differently from `before`, the version in force, of the tool
    calls of the last DAYS days, the latest MOST of them: each difference by instance, tool,
    parts and how each version decides it, with how many calls, and why the new decision is
    what it is, in policy's words; the levels it sets that a5s's caps hold back; and how much
    it looked at. `approvers` are who'd approve `after`, whose roles let level 2 count.

    Of the instances `viewer` may watch alone, as the studio shows them (core/studio.py): what
    others' runs did is counted against the limits each call is weighed against, as it was,
    but never decided again for them, and they hear only how many calls that leaves out."""
    calls, limited = _calls(conn, gw, now - timedelta(days=DAYS))
    watched = {i["id"] for i in studio.instances(conn) if viewer is None
               or studio.watches(i, viewer)}
    hidden = 0
    shown: dict[str, dict[tuple[str, str], int]] = {}  # each release's caps, as shown

    def caps_of(release: str) -> dict[tuple[str, str], int]:
        if release not in shown:
            shown[release] = samples.shown_caps(conn, gw.cfg.seal_keys, release)
        return shown[release]

    in_force = list(gw.approvers_in_force(conn))
    carried = [a for a in in_force if a not in approvers] if registry.narrowed(  # a version
        after, before) is not None else []  # that only narrows keeps the approvals before it
    tools = gw.scenario.tools()
    made: Counter[tuple[str, str]] = Counter()  # (piece of work, type): records made or held
    asked: dict[tuple[str, str], list[tuple[datetime, int]]] = defaultdict(list)  # (person, type)
    memo: dict[str, Decision] = {}
    shifts: Counter[tuple[str, str, tuple[str, ...], str, str]] = Counter()
    why: dict[tuple[str, str, tuple[str, ...], str, str], str] = {}
    decided = 0
    for call in calls:
        tool = tools[call.tool]
        action, weight = tool.action, max(len(call.keys), 1)
        work = counts.work({**call.run, "run": call.run["id"]})
        whom = groups.requesters(call.run) or [f"{NOBODY}{call.instance}"]
        if call.instance not in watched:  # theirs to know only as a number
            hidden += 1
            if action and call.decision in ("allow", "hold"):
                made[(work, action)] += weight
                for person in whom:
                    asked[(person, action)].append((call.at, weight))
            continue
        decisions = []
        for settings, approved in ((before, in_force), (after, [*approvers, *carried])):
            over = action is not None and _over(settings, action, weight, work, whom, call,
                                               made, asked)
            decisions.append(_decide(gw, tool, call, settings, approved, caps_of, over, memo))
        if decisions[0] is None or decisions[1] is None:
            continue
        decided += 1
        was, would = decisions[0].label, decisions[1].label
        if was != would:
            key = (call.instance, call.tool, tuple(sorted(
                {p for k in call.keys if (p := gw.scenario.part_of(k))})), was, would)
            shifts[key] += 1
            why.setdefault(key, next(iter(decisions[1].explanations), ""))
        if action and call.decision in ("allow", "hold"):  # what it counted, as it was decided
            made[(work, action)] += weight
            for person in whom:
                asked[(person, action)].append((call.at, weight))
    return {"days": DAYS, "calls": decided, "limited": limited, "about": ABOUT, "hidden": hidden,
            "beyond": [said.format(**values) for said, values in undecided(before, after)],
            "capped": capped(gw, before, after, caps_of),
            "shifts": [{"instance": i, "tool": t, "parts": list(p), "was": w, "would": n,
                        "calls": c, "why": why[(i, t, p, w, n)]}
                       for (i, t, p, w, n), c in sorted(shifts.items(),
                                                        key=lambda s: (-s[1], s[0]))]}


def undecided(before: Settings | None, after: Settings) -> list[tuple[str, dict[str, str]]]:
    """What a version changes from the one in force that the preview doesn't decide again,
    each as its words and what goes in them: such as whom an instance serves."""
    if before is None:
        return []
    found: list[tuple[str, dict[str, str]]] = []
    if (before.data_class, before.classified) != (after.data_class, after.classified):
        found.append((UNDECIDED["classes"], {}))
    was = {i.id: i for i in before.instances}
    for inst in after.instances:
        if (then := was.get(inst.id)) is None:
            continue  # a new instance has made no calls to decide again
        found += [(UNDECIDED[name], {"instance": inst.id})
                  for name in ("serves", "asks", "hands_to", "shadows", "model")
                  if getattr(then, name) != getattr(inst, name)]
    if before.spending != after.spending:
        found.append((UNDECIDED["spending"], {}))
    if before.data_protection != after.data_protection:
        found.append((UNDECIDED["choices"], {}))
    return found


def _digest(settings: Settings | None) -> str:
    if settings is None:
        return "none"
    return hashlib.sha256(settings.raw or repr(settings).encode()).hexdigest()


def shown(gw: Any, before: Settings | None, after: Settings,
          viewer: Person) -> dict[str, Any] | None:
    """The preview, for a page, as `viewer` may see it: read in its own transaction, as
    whoever'd approve `after` would see it approved; None if it can't be worked out, which a
    review still shows without, as it's what the version says that people approve. It's
    worked out once for a version, its reader and the ledger as it stands, and kept KEEP
    seconds, AT_ONCE at a time (round 14)."""
    needed = [p.id for p in registry.approvers(after, gw.scenario.holders, before,
                                               memberships.rooted(gw.scenario).holders)]
    try:
        with db.transaction(gw.url) as conn:
            language = languages.of(conn, viewer)
            head = (conn.execute("select encode(hash, 'hex') as head from ledger order by seq "
                                 "desc limit 1").fetchone() or {"head": ""})["head"]
        key = (_digest(after), _digest(before), viewer.id, language, head)
        with _keeping:
            kept = _kept.get(key)
        if kept is not None and time.monotonic() - kept[0] < KEEP:
            return copy.deepcopy(kept[1])
        if not _working.acquire(timeout=WAIT):  # as others are worked out: it shows without
            log.warning("a preview of a version waited longer for its turn than a5s gives one")
            return None
        try:
            with db.transaction(gw.url) as conn:
                found = preview(conn, gw, before, after, needed, gw.clock(), viewer)
        finally:
            _working.release()
    except Exception:  # a preview is help, never a reason to refuse a review
        log.exception("couldn't work out what a version of the settings would do")
        return None
    found["about"] = words.say(language, ABOUT)  # in the language they read, as its why
    for shift in found["shifts"]:  # is, where a5s has it in their language
        shift["why"] = words.say(language, shift["why"])
    found["beyond"] = [words.say(language, said, **values)
                       for said, values in undecided(before, after)]
    with _keeping:
        _kept[key] = (time.monotonic(), copy.deepcopy(found))
        _kept.move_to_end(key)
        while len(_kept) > KEPT_MOST:
            _kept.popitem(last=False)
    return found


def _calls(conn: db.Connection, gw: Any, since: datetime) -> tuple[list[Call], bool]:
    """The scenario's tool calls policy decided since then, the latest MOST, oldest first, and
    whether there were more. a5s's own tools aren't among them: no version decides them
    differently, as no part's data is theirs to change."""
    rows = conn.execute(  # by the ledger's index of tool calls, newest first, the latest alone
        "select seq, entry, run_id from ledger where kind = 'tool' "
        "and decision in ('allow', 'hold', 'deny') order by seq desc limit %s",
        (MOST + 1,)).fetchall()
    ids = sorted({r["run_id"] for r in rows[:MOST] if r["run_id"] and _UUID.fullmatch(r["run_id"])})
    runs = {r["id"]: r for r in conn.execute(
        "select id::text as id, trigger, acts_for, read_outside from runs where id = any(%s::uuid[])",
        (ids,))} if ids else {}
    tools = gw.scenario.tools()
    found: list[Call] = []
    for row in rows[:MOST]:
        run = runs.get(row["run_id"] or "")
        if run is None:
            continue
        entry = json.loads(row["entry"])
        at = datetime.fromisoformat(entry["at"])
        if at < since:
            break
        tool = tools.get(entry["action"])
        if tool is None or (entry["decision"] == "deny"
                            and set(entry.get("reasons") or ()) & NOT_POLICY):
            continue
        named = (entry.get("args") or {}).get(tool.record_arg) if tool.record_arg else None
        keys = [] if named in (None, "") else named if isinstance(named, list) else [named]
        if not all(isinstance(k, str) and k for k in keys):  # kept by its hash: not named
            continue
        found.append(Call(seq=row["seq"], at=at, instance=entry["instance"], tool=entry["action"],
                          keys=tuple(keys), decision=entry["decision"],
                          run={"id": run["id"], "trigger": run["trigger"] or {},
                               "acts_for": list(run["acts_for"]),
                               # its mark when it was decided, as the ledger kept it, or else
                               "read_outside": entry.get("read_outside",  # the run's as it
                                                         run["read_outside"])}))  # stands
    return found[::-1], len(rows) > MOST


def _row(gw: Any, inst: InstanceSettings, call: Call) -> dict[str, Any] | None:
    """The run as the gateway would hold it under a version: its instance's level, parts,
    types of action and whom it serves as that version sets them, with its release's grant,
    model and pins, and the run's own trigger, people and mark."""
    release = gw.definitions.get(inst.definition)
    if release is None:
        return None
    level, levels = registry.levels(inst, release)
    return {"id": inst.id, "run": call.run["id"],
            "status": "shadow" if inst.shadows else "active", "level": level,
            "parts": levels, "actions": registry.action_levels(inst, release),
            "grants": list(release.grants), "model": inst.model or release.model,
            "serves": list(inst.serves),
            "pins": dict(release.pins), "release": release.release_id,
            "trigger": call.run["trigger"], "acts_for": call.run["acts_for"],
            "read_outside": call.run["read_outside"]}


def _decide(gw: Any, tool: Any, call: Call, settings: Settings | None, approved: list[str],
            caps_of: Any, over: bool, memo: dict[str, Decision]) -> Decision | None:
    """How a version decides a call, as the gateway would: None where the version has no
    settings at all, and refused where it has no such instance. A change someone asked for of
    their own records counts as theirs where, decided as recorded, it shows it was."""
    if settings is None:
        return None
    inst = next((i for i in settings.instances if i.id == call.instance), None)
    if inst is None:
        return Decision(False, ("not-in-this-version",),
                        explanations=(f"{call.instance} isn't in this version",))
    row = _row(gw, inst, call)
    if row is None:
        return None
    entity = gw.tool_entity(call.tool, tool, row["pins"])
    about = parts.about(gw.scenario, row, list(call.keys), tool.action, approved,
                        caps_of(row["release"]))

    def deciding(for_self: bool) -> Decision:
        context = {**about, "for_self": for_self, "over_limit": over}
        key = json.dumps([row["release"], row["level"], row["grants"], row["serves"],
                          row["model"], row["read_outside"], row["acts_for"], call.tool, context],
                         sort_keys=True, default=str)
        if key not in memo:
            memo[key] = gw.decide(row, "call_tool", entity, [], **context)
        return memo[key]

    found = deciding(False)
    if tool.action and found.label != call.decision and deciding(True).label == call.decision:
        return deciding(True)  # it was their own, as its decision then shows
    return found


def _over(settings: Settings | None, action: str, weight: int, work: str, whom: list[str],
          call: Call, made: Counter, asked: dict) -> bool:
    """Whether a change was past a version's limits for its type, by core/counts.py's rules,
    as the ledger counts them: what its run, or its task, had had made or held, and each person
    it was asked for in the 30 days before it."""
    limit = (settings.limits.get(action) if settings else None) or {}
    if (most := limit.get("per_run")) is not None and made[(work, action)] + weight > most:
        return True
    if (most := limit.get("per_person_30_days")) is not None:
        since = call.at - counts.WINDOW
        return any(sum(n for at, n in asked[(person, action)] if at > since) + weight > most
                   for person in whom)
    return False


def capped(gw: Any, before: Settings | None, after: Settings, caps_of: Any) -> list[str]:
    """The types of action a version lets act on its own that a5s still holds to asking
    first, in words: where graded samples haven't earned it yet."""
    found = []
    for inst in after.instances:
        release = gw.definitions.get(inst.definition)
        was = next((i for i in (before.instances if before else ()) if i.id == inst.id), None)
        if release is None:
            continue
        for part, acts in sorted(registry.action_levels(inst, release).items()):
            earlier = registry.action_levels(was, release).get(part, {}) if was else {}
            for action, level in sorted(acts.items()):
                if level >= 2 > earlier.get(action, 0) and caps_of(release.release_id).get(
                        (part, action), 1) < 2:
                    found.append(f"{inst.id} is set to act on its own for {action} in {part}, "
                                 "but a5s holds it to asking first until graded samples show "
                                 "it's accurate enough, so it makes none on its own yet.")
    return found
