"use strict";
// The administrators' page: who holds each of a5s's roles, and by what, the directory or a
// group, what waits for whom, and the latest administrative acts. It only shows. People sign
// in with their organisation's identity provider; the page shows only text, and keeps the
// sign-in in memory alone.

const $ = (id) => document.getElementById(id);
const store = window.sessionStorage;
const PENDING = "a5s.admin";
const BACK = `${location.origin}/admin/`;
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
  history.replaceState(null, "", "/admin/");
  const pending = JSON.parse(store.getItem(PENDING) || "null");
  store.removeItem(PENDING);
  if (params.has("error")) {
    throw new Error(`Signing in didn't work: ${params.get("error_description") || params.get("error")}`);
  }
  const again = "Signing in didn't come back the way it went out. Open the administrators' page again.";
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

function item(text, className) {
  const li = document.createElement("li");
  li.textContent = text;
  if (className) li.className = className;
  return li;
}

function list(id, items, none) {
  const into = $(id);
  into.replaceChildren(...items);
  if (!items.length) into.append(item(none, "note"));
}

async function load() {
  const now = await call("/admin/api");
  $("who").textContent = now.you;
  list("roles", now.roles.map((row) => item(`${row.role}: ${row.held_by.map(
    (h) => `${h.name} (${h.by.join(", ")})`).join("; ") || "nobody"}`)), "No roles.");
  $("claim").textContent = now.claim
    ? `Sign-ins show their groups in the ${now.claim} claim. A role a group gives counts from someone's latest sign-in.`
    : "This deployment reads no groups from sign-ins, so the directory alone gives roles.";
  list("groups", now.groups.map((g) => item(
    `${g.group}: ${g.roles.join(", ")}, for ${g.people} ${g.people === 1 ? "person" : "people"} as their latest sign-ins showed`)),
    "None: the settings in force give no group a role.");
  const waits = [];
  for (const v of now.waiting.settings) {
    waits.push(item(`Settings, serial ${v.serial}: ${v.needs.length ? v.needs.join("; ") : "approved, for a5s to apply"}`));
  }
  for (const problem of now.waiting.release) waits.push(item(`The release: ${problem}`));
  for (const held of now.waiting.held_changes) {
    waits.push(item(`${held.waiting} held ${held.waiting === 1 ? "change" : "changes"} in ${held.part}, for ${held.deciders.join(", ") || "nobody"} to decide`));
  }
  list("waiting", waits, "Nothing waits.");
  $("latest-title").textContent = `The latest acts, over the last ${now.days} days`;
  list("latest", now.latest.map((act) => item(
    `${act.at}: ${act.by || "a5s"} ${act.what}${act.instance ? `, ${act.instance}` : ""}`)),
    "Nothing was done.");
  $("shown").hidden = false;
  status("");
}

async function main() {
  try {
    if (!window.crypto || !crypto.subtle) {
      status("The administrators' page needs HTTPS, or a page on this computer.");
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
      status(typeof body.detail === "string" ? body.detail : "The administrators' page isn't set up here.");
      return;
    }
    status("Signing you in…");
    await signIn(body.signin);
  } catch (error) {
    status(error.message);
  }
}

document.addEventListener("DOMContentLoaded", main);
