"use strict";
// The studio, read only, for the people who run an instance, own an agent, own or decide for
// one of its parts, or approve instances: the agents they may watch and where each runs, how
// each instance is doing, and what its runs did. They sign in with their organisation's
// identity provider; the page shows only text, only what they may see, and keeps the sign-in
// in memory alone.

const $ = (id) => document.getElementById(id);
const store = window.sessionStorage;
const PENDING = "a5s.studio";
const BACK = `${location.origin}/studio/`;
let token = null;
let current = null;  // the instance shown, if any
let older = null;  // where its next page of runs starts

const status = (text) => { $("status").textContent = text; };

function b64url(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

const random = () => b64url(crypto.getRandomValues(new Uint8Array(32)));
const sha256 = async (text) => b64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)));

function claims(jwt) {
  const part = jwt.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
  return JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(part), (c) => c.charCodeAt(0))));
}

async function signIn(signin) {
  const pending = { verifier: random(), state: random(), nonce: random() };
  store.setItem(PENDING, JSON.stringify(pending));
  const url = new URL(signin.authorization_endpoint);
  const query = {
    response_type: "code", client_id: signin.client_id, redirect_uri: BACK, scope: signin.scope,
    state: pending.state, nonce: pending.nonce, code_challenge: await sha256(pending.verifier),
    code_challenge_method: "S256",
  };
  for (const [key, value] of Object.entries(query)) url.searchParams.set(key, value);
  location.assign(url.toString());
}

async function signedIn(params) {
  history.replaceState(null, "", "/studio/");
  const pending = JSON.parse(store.getItem(PENDING) || "null");
  store.removeItem(PENDING);
  if (params.has("error")) {
    throw new Error(`Signing in didn't work: ${params.get("error_description") || params.get("error")}`);
  }
  const again = "Signing in didn't come back the way it went out. Open the studio again.";
  if (!pending || params.get("state") !== pending.state) throw new Error(again);
  const answer = await fetch("/approve/token", {  // the core passes it on to the provider
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ grant_type: "authorization_code", code: params.get("code"),
                           code_verifier: pending.verifier, redirect_uri: BACK }),
  });
  const tokens = await answer.json();
  if (!answer.ok || !tokens.id_token) {
    throw new Error(`Signing in didn't work: ${tokens.error_description || tokens.error || tokens.detail || answer.status}`);
  }
  if (claims(tokens.id_token).nonce !== pending.nonce) throw new Error(again);
  return tokens.id_token;
}

async function call(path) {
  const answer = await fetch(path, { headers: { Authorization: `Bearer ${token}` } });
  const found = await answer.json();
  if (!answer.ok) {
    throw new Error(typeof found.detail === "string" ? found.detail : `a5s said ${answer.status}.`);
  }
  return found;
}

function element(tag, text, className) {
  const found = document.createElement(tag);
  if (text !== undefined && text !== null) found.textContent = String(text);
  if (className) found.className = className;
  return found;
}

function button(text, then) {
  const found = element("button", text);
  found.type = "button";
  found.addEventListener("click", () => then().catch((error) => status(error.message)));
  return found;
}

function show(which) {  // one view at a time: all the agents, an instance, or a run
  for (const id of ["agents", "instance", "run"]) $(id).hidden = id !== which;
  $("trail").hidden = which === "agents";
  $("to-instance").hidden = which !== "run" || !current;
  if (current) $("to-instance").textContent = current;
}

const people = (n) => `${n} ${n === 1 ? "person" : "people"}`;
const share = (x) => (x === null || x === undefined ? "none yet" : `${Math.round(x * 100)}%`);
const times = (n) => `${n} ${n === 1 ? "time" : "times"}`;
const when = (at) => at.slice(0, 16).replace("T", " ");

function levels(agent) {
  const { start, max } = agent.autonomy;
  return start === max ? `level ${start}` : `levels ${start} to ${max}`;
}

function aboutInstance(inst) {
  const parts = Object.keys(inst.parts).join(", ") || "no part";
  const runners = [inst.owner, inst.deputy].filter(Boolean).join(" and ") || "nobody";
  return `${inst.status}, level ${inst.level}, in ${parts}, serving ${people(inst.people)}, `
    + `run by ${runners}` + (inst.current ? "" : `, still on release ${inst.release}`);
}

function aboutTool(tool) {
  const does = ["reads", "writes", "destructive", "sends_outside"].filter((k) => tool[k])
    .map((k) => k.replace("_", " "));
  if (tool.changes) does.push(`changes ${tool.changes}`);
  if (tool.handles.length) does.push(`hands over ${tool.handles.join(", ")} as handles`);
  if (tool.outside.length) does.push("reads outside content through a5s's reader");
  return `${tool.group}: ${tool.name} (${does.join(", ") || "reads nothing"})`;
}

async function loadAgents() {
  const now = await call("/studio/api");
  $("who").textContent = now.you;
  const into = $("agents");
  into.replaceChildren();
  for (const agent of now.agents) {
    const block = element("article");
    block.append(element("h3", `${agent.id}, release ${agent.release}`),
                 element("p", `Works for: ${agent.works_for}. ${agent.does}`, "note"),
                 element("p", `${agent.model}, at ${levels(agent)}. Owned by `
                   + `${agent.owners.join(", ") || "nobody the directory names"}.`));
    const tools = element("ul", null, "plain");
    for (const tool of agent.tools) tools.append(element("li", aboutTool(tool)));
    if (agent.a5s_tools.length) tools.append(element("li", `a5s's own: ${agent.a5s_tools.join(", ")}`));
    const where = element("ul", null, "plain");
    for (const inst of agent.instances) {
      const line = element("li");
      line.append(button(inst.id, () => openInstance(inst)), ` ${aboutInstance(inst)}`);
      where.append(line);
    }
    if (!agent.instances.length) where.append(element("li", "No instance you may watch runs it."));
    block.append(element("h4", "Tools"), tools, element("h4", "Where it runs"), where);
    into.append(block);
  }
  status(now.agents.length ? "" : "There are no agents you may watch.");
  show("agents");
}

function row(table, what, figures) {
  const line = element("tr");
  line.append(element("th", what), element("td", figures));
  table.append(line);
}

function figuresOf(found) {
  const table = $("figures");
  table.replaceChildren();
  row(table, "Runs that called a model", found.runs.map((r) => `${r.runs} on ${r.model}: `
    + `${r.tokens_per_run} tokens a run, ${share(r.cached_share)} cached`
    + (r.cost_per_run === null ? "" : `, ${r.cost_per_run} a run`)).join("; ") || "none");
  row(table, "How runs ended", found.ended.map((e) => `${e.kind} ${e.outcome}: ${e.runs}`)
    .join("; ") || "no runs");
  const o = found.obligations;
  row(table, "What fell due", o.due ? `${o.due} due: ${o.on_time} on time, ${o.late} late, `
    + `${o.open} open; ${o.chased} chased, ${o.escalated} taken up the line` : "nothing");
  const r = found.reminders;
  row(table, "Reminders", r.due ? `${r.due} due: ${r.on_time} on time, ${r.missed} missed`
    : "none fell due");
  const h = found.held;
  row(table, "Held changes", h.held ? `${h.held} held: ${h.approved} approved, ${h.rejected} `
    + `rejected, ${h.lapsed} lapsed, ${h.waiting} waiting` : "none");
  const s = found.samples;
  row(table, "Samples graded", s.graded ? `${s.graded}: ${s.right} right, ${s.wrong} wrong, `
    + `${s.critical} critical` : "none");
  row(table, "Denied", found.denied.map((d) => `${d.action}, ${times(d.times)}`
    + (d.reasons.length ? ` (${d.reasons.join(", ")})` : "")).join("; ") || "nothing");
  row(table, "Reports sent", found.reports.map((x) => `${x.source} ${x.outcome}: ${x.reports}`)
    .join("; ") || "none");
  row(table, "Came back", found.returning.map((x) => `${x.came_back} of the `
    + `${people(x.wrote_before)} who wrote to ${x.agent} before`).join("; ") || "nobody wrote before");
}

function aboutRun(run) {  // whom it acted for by name only once the officer agrees
  const named = run.acts_for.map((p) => p.name || p.id).join(", ");
  const whom = named || (run.people ? people(run.people) : "nobody");
  return `${when(run.opened_at)} ${run.trigger} for ${whom}: `
    + `${run.outcome}, ${run.tokens} tokens` + (run.read_outside ? ", read outside content" : "");
}

function runsOf(page, more) {
  const into = $("runs");
  if (!more) into.replaceChildren();
  for (const run of page.runs) {
    const line = element("li");
    line.append(button(aboutRun(run), () => openRun(run.run)));
    into.append(line);
  }
  if (!more && !page.runs.length) into.append(element("li", "No runs you may see."));
  $("runs-hidden").textContent = page.hidden
    ? `And ${page.hidden} that read records you may not see.` : "";
  older = page.before;
  $("more").hidden = !older;  // the core says when there are no more
}

async function loadInstance() {
  const id = encodeURIComponent(current);
  figuresOf(await call(`/studio/api/instances/${id}?days=${$("days").value}`));
  runsOf(await call(`/studio/api/instances/${id}/runs`), false);
}

async function openInstance(inst) {
  current = inst.id;
  $("instance-title").textContent = inst.id;
  $("instance-about").textContent = aboutInstance(inst);
  await loadInstance();
  status("");
  show("instance");
}

async function openRun(id) {
  const found = await call(`/studio/api/runs/${encodeURIComponent(id)}`);
  $("run-title").textContent = `Run ${found.run}`;
  const started = Object.entries(found.started_by)
    .map(([key, value]) => `${key} ${typeof value === "object" ? JSON.stringify(value) : value}`);
  $("run-facts").replaceChildren(
    element("li", aboutRun(found)),
    element("li", `Agent ${found.agent}, instance ${found.instance}, model `
      + `${found.model || "none"}; closed ${found.closed_at ? when(found.closed_at) : "not yet"}`),
    element("li", `Started by: ${started.join(", ")}`),
    element("li", `Records read: ${found.records.join(", ") || "none"}`));
  const calls = $("calls");
  calls.replaceChildren();
  const head = element("tr");
  for (const name of ["When", "Tool", "Decision", "Why", "How it ended"]) head.append(element("th", name));
  calls.append(head);
  for (const c of found.calls) {
    const line = element("tr");
    for (const value of [c.at.slice(11, 19), c.tool, c.decision, c.reasons.join(", "), c.outcome || ""]) {
      line.append(element("td", value));
    }
    calls.append(line);
  }
  if (!found.calls.length) {
    const line = element("tr");
    const cell = element("td", "It called no tools.");
    cell.colSpan = 5;
    line.append(cell);
    calls.append(line);
  }
  status("");
  show("run");
}

async function main() {
  try {
    if (!window.crypto || !crypto.subtle) {
      status("The studio needs HTTPS, or a page on this computer.");
      return;
    }
    $("to-agents").addEventListener("click", () => show("agents"));
    $("to-instance").addEventListener("click", () => show("instance"));
    $("days").addEventListener("change", () => loadInstance().catch((e) => status(e.message)));
    $("more").addEventListener("click", async () => {
      try {
        const id = encodeURIComponent(current);
        runsOf(await call(`/studio/api/instances/${id}/runs?before=${encodeURIComponent(older)}`), true);
      } catch (error) {
        status(error.message);
      }
    });
    const params = new URLSearchParams(location.search);
    if (params.has("code") || params.has("error")) {
      token = await signedIn(params);
      await loadAgents();
      return;
    }
    const config = await fetch("/approve/config");
    const body = await config.json();
    if (!config.ok) {
      status(typeof body.detail === "string" ? body.detail : "The studio isn't set up here.");
      return;
    }
    status("Signing you in…");
    await signIn(body.signin);
  } catch (error) {
    status(error.message);
  }
}

document.addEventListener("DOMContentLoaded", main);
