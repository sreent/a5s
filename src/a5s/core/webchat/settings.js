"use strict";
// The settings app, for the people who approve instances: each part's owner, and the
// instance approvers. They sign in with their organisation's identity provider, see the whole
// version in force in words, and the versions waiting for approval, and can ask for a change.
// Asking changes nothing: a5s proposes the new version to everyone who must approve it, and
// they approve it on its own page, signing in afresh. The page shows only text, and keeps the
// sign-in in memory alone.

const $ = (id) => document.getElementById(id);
const store = window.sessionStorage;
const PENDING = "a5s.settings";
const BACK = `${location.origin}/settings/`;
let token = null;

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
  history.replaceState(null, "", "/settings/");
  const pending = JSON.parse(store.getItem(PENDING) || "null");
  store.removeItem(PENDING);
  if (params.has("error")) {
    throw new Error(`Signing in didn't work: ${params.get("error_description") || params.get("error")}`);
  }
  const again = "Signing in didn't come back the way it went out. Open the settings again.";
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

async function call(path, body) {
  const answer = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const found = await answer.json();
  if (!answer.ok) {
    const detail = found.detail;
    if (detail && Array.isArray(detail.problems)) throw new Error(detail.problems.join(" "));
    throw new Error(typeof detail === "string" ? detail : `a5s said ${answer.status}.`);
  }
  return found;
}

function list(id, items, mark) {
  const into = $(id);
  into.replaceChildren();
  for (const item of items) {
    const line = document.createElement("li");
    const text = typeof item === "string" ? item : item.text;
    line.textContent = item.widens ? `${text} This widens what agents do.` : text;
    if (item.widens) line.className = "widens";
    if (mark) line.classList.add(mark);
    into.append(line);
  }
}

function showWaiting(waiting) {
  const into = $("waiting");
  into.replaceChildren();
  for (const version of waiting) {
    const title = document.createElement("p");
    const link = document.createElement("a");
    link.href = version.link;
    link.textContent = `Serial ${version.serial}`;
    title.append(link, version.approved_by.length
      ? `, approved so far by ${version.approved_by.join(", ")}.` : ", which nobody has approved yet.");
    const changes = document.createElement("ul");
    changes.className = "plain";
    into.append(title, changes);
    for (const change of version.changes) {
      const line = document.createElement("li");
      line.textContent = change.widens ? `${change.text} This widens what agents do.` : change.text;
      if (change.widens) line.className = "widens";
      changes.append(line);
    }
    if (version.needs.length) {
      const needs = document.createElement("p");
      needs.className = "note";
      needs.textContent = `It still waits because ${version.needs.join("; ")}.`;
      into.append(needs);
    }
  }
  $("waiting-section").hidden = waiting.length === 0;
}

function showRequests(requests) {
  list("requests", requests.map((r) => {
    const when = new Date(r.asked_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
    return `Serial ${r.serial}, asked for ${when}: ${r.outcome}.`;
  }));
  $("requests-section").hidden = requests.length === 0;
}

async function load() {
  const now = await call("/settings/api");
  $("who").textContent = now.you;
  if (now.in_force) {
    $("in-force-title").textContent = `In force: serial ${now.in_force.serial}`;
    list("whole", now.in_force.whole);
    $("in-force").hidden = false;
    if (!$("text").value) $("text").value = now.in_force.text;
  } else {
    status("No settings are in force yet.");
  }
  showWaiting(now.waiting);
  showRequests(now.requests);
  $("edit").hidden = false;
}

async function review() {
  $("reviewed").hidden = true;
  const found = await call("/settings/api/review", { text: $("text").value });
  list("problems", found.problems || [], "widens");
  if (found.serial === undefined) {
    $("reviewed-summary").textContent = "a5s can't propose this:";
    $("reviewed").hidden = false;
    $("send").hidden = true;
    return;
  }
  $("reviewed-summary").textContent = found.problems.length
    ? `As serial ${found.serial}, a5s can't propose this:` : `As serial ${found.serial}, it:`;
  list("reviewed-changes", found.changes);
  $("reviewed-approvers").textContent = found.approvers.length
    ? `It needs the approval of ${found.approvers.join(", ")}.` : "Nobody in the directory can approve it.";
  list("reviewed-whole", found.whole);
  $("send").hidden = found.problems.length > 0;
  $("reviewed").hidden = false;
}

async function send() {
  $("send").disabled = true;
  try {
    const asked = await call("/settings/api/requests", { text: $("text").value });
    $("reviewed").hidden = true;
    status(`You asked for serial ${asked.serial}. a5s asks its approvers within a minute, and puts it in force once they've all approved it.`);
    await load();
  } finally {
    $("send").disabled = false;
  }
}

async function main() {
  try {
    if (!window.crypto || !crypto.subtle) {
      status("The settings app needs HTTPS, or a page on this computer.");
      return;
    }
    const params = new URLSearchParams(location.search);
    if (params.has("code") || params.has("error")) {
      token = await signedIn(params);
      await load();
      $("review").addEventListener("click", () => review().catch((e) => status(e.message)));
      $("send").addEventListener("click", () => send().catch((e) => status(e.message)));
      return;
    }
    const config = await fetch("/approve/config");
    const body = await config.json();
    if (!config.ok) {
      status(typeof body.detail === "string" ? body.detail : "The settings app isn't set up here.");
      return;
    }
    status("Signing you in…");
    await signIn(body.signin);
  } catch (error) {
    status(error.message);
  }
}

document.addEventListener("DOMContentLoaded", main);
