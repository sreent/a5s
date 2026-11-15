"""The notebook's page in the channels app (docs/architecture.md): what agents learned from
records, for the people who keep each instance's notebook to read and remove (core/notebook.py).

Every route of its API is behind the router's own check of who's signed in: someone who owns
an agent, or runs one of its instances, as its owner or deputy.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response

from a5s import db
from a5s.contract import Person
from a5s.core import ledger, notebook, web

Keeper = tuple[Person, list[dict]]  # who signed in, and the instances whose notebooks they keep


def kept(gw: Any, person: Person) -> list[dict]:
    """The instances whose notebooks someone keeps: those of an agent they own, or that they
    run, as its owner or deputy."""
    owns = {r.removeprefix("agent-owner:") for r in person.roles if r.startswith("agent-owner:")}
    with db.transaction(gw.url) as conn:
        return [i for i in conn.execute("select id, definition, owner, deputy, parts from instances "
                                        "where status <> 'retired' order by id")
                if i["definition"] in owns or person.id in (i["owner"], i["deputy"])]


def named(instance: dict) -> str:
    """An instance as people say it: its agent, and where it works, such as "the assistant in
    billing"."""
    parts = sorted(instance["parts"] or {})
    return f"the {instance['definition']}" + (f" in {' and '.join(parts)}" if parts else "")


def router(gw: Any) -> APIRouter:
    """The notebook's page and its API, for the channels app to include."""

    def available() -> None:
        web.approving(gw)

    def keeping(authorization: str | None = Header(default=None)) -> Keeper:
        """Who signed in to the notebook, and the instances whose entries they keep."""
        person = web.known(gw, authorization)
        if not (instances := kept(gw, person)):
            raise HTTPException(403, "the notebook is for the people who own an agent, or run one "
                                     "of its instances")
        return person, instances

    pages = APIRouter(dependencies=[Depends(available)])  # the page alone, which holds no data
    api = APIRouter(dependencies=[Depends(available), Depends(keeping)])

    def may_see(person: Person, row: dict) -> bool:
        """Whether someone may see a note: every record its run read, as it reached runs."""
        return all(gw.scenario.sees(person.id, k) for k in row["read_records"] or row["sources"])

    @pages.get("/notebook/", include_in_schema=False)
    def notebook_page() -> Response:
        return web.page(gw, "notebook.html")

    @pages.get("/notebook/notebook.js", include_in_schema=False)
    def notebook_script() -> Response:
        return web.page(gw, "notebook.js")

    @api.get("/notebook/api")
    def notebook_now(keeper: Annotated[Keeper, Depends(keeping)]) -> dict:
        """The entries of the instances someone keeps, those whose every record they may see,
        each with links to its records, and who else keeps the ones they may not see."""
        person, instances = keeper
        with db.transaction(gw.url) as conn:
            rows = conn.execute("select * from notebook where instance_id = any(%s) "
                                "order by instance_id, written_at desc, id desc",
                                ([i["id"] for i in instances],)).fetchall()
        shown = [r for r in rows if may_see(person, r)]
        hidden = {r["instance_id"] for r in rows if not may_see(person, r)}
        others = sorted({p.name for i in instances if i["id"] in hidden
                         for k in (i["owner"], i["deputy"])
                         if k and k != person.id and (p := gw.scenario.person(k))})
        return {"you": person.name, "instances": [i["id"] for i in instances],
                "names": {i["id"]: named(i) for i in instances},
                "entries": [{"entry": f"N-{r['id']}", "instance": r["instance_id"],
                             "text": r["text"],
                             "sources": [{"key": k, "link": (r["links"] or {}).get(k)}
                                         for k in r["sources"]],
                             "noted": r["written_at"].date().isoformat(),
                             "checked": r["checked_at"].date().isoformat()} for r in shown],
                "hidden": len(rows) - len(shown), "others": others}

    @api.post("/notebook/api/{entry}/remove")
    def notebook_remove(entry: str, keeper: Annotated[Keeper, Depends(keeping)]) -> dict:
        """Remove an entry, as someone who keeps its instance's notebook and may see its records."""
        person, instances = keeper
        number = entry.removeprefix("N-")
        if not number.isdigit():
            raise HTTPException(404, "no such entry")
        with db.transaction(gw.url) as conn:
            row = conn.execute("delete from notebook where id = %s and instance_id = any(%s) "
                               "returning *",
                               (int(number), [i["id"] for i in instances])).fetchone()
            if row is None or not may_see(person, row):
                raise HTTPException(404, "no such entry in a notebook you keep")
            ledger.append(conn, notebook.entry(row, "remove", "its keeper removed it", person.id))
        return {"removed": f"N-{row['id']}"}

    pages.include_router(api)
    return pages
