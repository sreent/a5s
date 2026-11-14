"use strict";
// The auditors' page: the ledger as an auditor reads it, read only. They sign in with their
// organisation's identity provider, as an auditor or assurance; the page shows only text, and
// keeps the sign-in in memory alone. Whoever acted in one of a5s's roles shows as themselves,
// and whom agents acted for as a stand-in, until the data protection officer agrees to names.

const $ = (id) => document.getElementById(id);
const store = window.sessionStorage;
const PENDING = "a5s.audit";
const BACK = `${location.origin}/audit/`;
let token = null;
let asked = new URLSearchParams();  // the search on show
let next = null;  // where its next page starts

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
  if (signin.acr_values) query.acr_values = signin.acr_values;  // the level what counts needs
  for (const [key, value] of Object.entries(query)) url.searchParams.set(key, value);
  location.assign(url.toString());
}

async function signedIn(params) {
  history.replaceState(null, "", "/audit/");
  const pending = JSON.parse(store.getItem(PENDING) || "null");
  store.removeItem(PENDING);
  if (params.has("error")) {
    throw new Error(`Signing in didn't work: ${params.get("error_description") || params.get("error")}`);
  }
  const again = "Signing in didn't come back the way it went out. Open the audit trail again.";
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

function line(text, className) {
  const p = document.createElement("p");
  p.textContent = text;
  if (className) p.className = className;
  return p;
}

function utc(id) {  // the page's times are UTC's, as the ledger's are
  const value = $(id).value;
  if (!value) return null;
  return value.length === 16 ? `${value}:00Z` : `${value}Z`;
}

function period() {
  const query = new URLSearchParams();
  for (const [name, id] of [["since", "since"], ["until", "until"]]) {
    const at = utc(id);
    if (at) query.set(name, at);
  }
  return query;
}

function filters() {
  const query = period();
  for (const name of ["kind", "action", "decision", "instance", "for", "by"]) {
    const value = $(name).value.trim();
    if (value) query.set(name, value);
  }
  return query;
}

function finding(name, value) {  // a person on show, to find their other entries with
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = value;
  button.addEventListener("click", () => {
    for (const other of ["for", "by"]) $(other).value = other === name ? value : "";
    run(() => search(false));
  });
  return button;
}

function people(label, name, values) {
  const p = document.createElement("p");
  p.className = "note";
  p.append(`${label} `);
  values.forEach((value, i) => {
    if (i) p.append(", ");
    p.append(finding(name, String(value)));
  });
  return p;
}

const ACTORS = ["admin", "audit", "proposal"];  // entries whose `by` acted in one of a5s's roles

function shown(entry) {
  const item = document.createElement("li");
  const where = entry.instance ? `, ${entry.instance}` : "";
  item.append(line(`#${entry.seq}, ${entry.at}: ${entry.kind} ${entry.action}, ${entry.decision}${where}`));
  if ((entry.acts_for || []).length) item.append(people("For", "for", entry.acts_for));
  const args = entry.args || {};
  if (ACTORS.includes(entry.kind) && args.by) {
    item.append(people("By", "by", Array.isArray(args.by) ? args.by : [args.by]));
  }
  if ((entry.reasons || []).length) item.append(line(`Why: ${entry.reasons.join(", ")}`, "note"));
  if (Object.keys(args).length) {
    const pre = document.createElement("pre");
    pre.className = "entries";
    pre.textContent = JSON.stringify(args, null, 1);
    item.append(pre);
  }
  return item;
}

async function search(more) {
  if (!more) {
    asked = filters();
    next = null;
    $("entries").replaceChildren();
    $("roles").hidden = true;
  }
  const query = new URLSearchParams(asked);
  if (more && next) query.set("after", next);
  const found = await call(`/audit/api/entries?${query}`);
  for (const entry of found.entries) $("entries").append(shown(entry));
  next = found.next;
  $("more").hidden = !next;
  status(found.entries.length || more ? "" : "No entries in that period, as asked.");
}

async function report() {
  const found = await call(`/audit/api/report?${period()}`);
  const holders = $("holders");
  holders.replaceChildren();
  for (const row of found.roles) {
    holders.append(line(`${row.role}: ${row.held_by.join(", ") || "nobody"}`));
  }
  const acts = $("acts");
  acts.replaceChildren();
  for (const act of found.acts) {
    const item = document.createElement("li");
    const where = act.instance ? `, ${act.instance}` : "";
    item.append(line(`${act.at}: ${act.by || "a5s"} ${act.what}${where}`));
    if (Object.keys(act.about || {}).length) {
      const pre = document.createElement("pre");
      pre.className = "entries";
      pre.textContent = JSON.stringify(act.about, null, 1);
      item.append(pre);
    }
    acts.append(item);
  }
  if (!found.acts.length) acts.append(line("Nothing was done in the period.", "note"));
  $("roles").hidden = false;
  status("");
}

async function exported() {  // the period exactly as the ledger holds it, a page at a time
  const lines = [];
  let after = null;
  let bounds = null;  // what the last page says of the period, and the entries either side
  do {
    const query = period();
    if (after) query.set("after", after);
    const page = await call(`/audit/api/export?${query}`);
    for (const entry of page.entries) lines.push(JSON.stringify(entry));
    after = page.next;
    bounds = { ...page.bounds, head: page.head };
  } while (after);
  lines.unshift(JSON.stringify({ export: bounds }));
  const file = new Blob([lines.map((each) => `${each}\n`).join("")], { type: "application/x-ndjson" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(file);
  link.download = "a5s-audit.jsonl";
  link.click();
  URL.revokeObjectURL(link.href);
  status(`Exported ${lines.length - 1} entries. Check them yourself, against the ledger's locked copies, with: a5s audit verify a5s-audit.jsonl`);
}

async function run(work) {
  try {
    status("Reading the ledger…");
    await work();
  } catch (error) {
    status(error.message);
  }
}

async function load() {
  const now = await call("/audit/api");
  $("who").textContent = now.you;
  $("naming").textContent = now.names
    ? "Whom agents acted for shows by name, as the data protection officer agreed."
    : "Whom agents acted for, told or asked about shows as a stand-in, the same one each time, until the data protection officer agrees to names.";
  for (const kind of now.kinds) {
    const option = document.createElement("option");
    option.textContent = kind;
    $("kind").append(option);
  }
  $("export").hidden = !now.exports;
  $("find").hidden = false;
  $("search").addEventListener("click", () => run(() => search(false)));
  $("more").addEventListener("click", () => run(() => search(true)));
  $("report").addEventListener("click", () => run(report));
  $("export").addEventListener("click", () => run(exported));
  status("");
}

async function main() {
  try {
    if (!window.crypto || !crypto.subtle) {
      status("The audit trail's page needs HTTPS, or a page on this computer.");
      return;
    }
    const params = new URLSearchParams(location.search);
    if (params.has("code") || params.has("error")) {
      token = await signedIn(params);
      window.a5s?.signedIn(token);  // the sidebar, of the pages they may use
      await load();
      return;
    }
    const config = await fetch("/approve/config");
    const body = await config.json();
    if (!config.ok) {
      status(typeof body.detail === "string" ? body.detail : "The audit trail's page isn't set up here.");
      return;
    }
    status("Signing you in…");
    await signIn(body.signin);
  } catch (error) {
    status(error.message);
  }
}

document.addEventListener("DOMContentLoaded", main);
