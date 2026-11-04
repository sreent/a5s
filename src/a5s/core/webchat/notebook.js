"use strict";
// The notebook, for the people who own an agent or run one of its instances: what the agents
// noted from records, with the records each note comes from, to read and remove. They sign in
// with their organisation's identity provider; the page shows only text, the notes whose
// records they may see, and keeps the sign-in in memory alone.

const $ = (id) => document.getElementById(id);
const store = window.sessionStorage;
const PENDING = "a5s.notebook";
const BACK = `${location.origin}/notebook/`;
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
  history.replaceState(null, "", "/notebook/");
  const pending = JSON.parse(store.getItem(PENDING) || "null");
  store.removeItem(PENDING);
  if (params.has("error")) {
    throw new Error(`Signing in didn't work: ${params.get("error_description") || params.get("error")}`);
  }
  const again = "Signing in didn't come back the way it went out. Open the notebook again.";
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

async function call(path, method = "GET") {
  const answer = await fetch(path, { method, headers: { Authorization: `Bearer ${token}` } });
  const found = await answer.json();
  if (!answer.ok) {
    throw new Error(typeof found.detail === "string" ? found.detail : `a5s said ${answer.status}.`);
  }
  return found;
}

async function load() {
  const now = await call("/notebook/api");
  $("who").textContent = now.you;
  const into = $("entries");
  into.replaceChildren();
  for (const entry of now.entries) {
    const line = document.createElement("li");
    const words = document.createElement("p");
    words.textContent = entry.text;
    const about = document.createElement("p");
    about.className = "note";
    about.append(`${entry.entry}, ${entry.instance}, from `);
    entry.sources.forEach((source, n) => {  // each record it comes from, linked where it has one
      if (n) about.append(", ");
      const safe = source.link && /^https:\/\//.test(source.link);
      const named = document.createElement(safe ? "a" : "span");
      named.textContent = source.key;
      if (safe) { named.href = source.link; named.rel = "noopener noreferrer"; }
      about.append(named);
    });
    about.append(`. Noted on ${entry.noted}; its records last checked on ${entry.checked}.`);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Remove";
    remove.addEventListener("click", async () => {
      try {
        await call(`/notebook/api/${entry.entry}/remove`, "POST");
        await load();
        status(`Removed ${entry.entry}.`);
      } catch (error) {
        status(error.message);
      }
    });
    line.append(words, about, remove);
    into.append(line);
  }
  status(now.entries.length ? "" : `Nothing noted yet for ${now.instances.join(", ")}.`);
  const who = now.others.length ? `: ${now.others.join(" or ")}, who run its instances, may be able to` : "";
  $("hidden").textContent = now.hidden
    ? `And ${now.hidden} more from records you may not see, which someone who may see them can remove${who}.` : "";
}

async function main() {
  try {
    if (!window.crypto || !crypto.subtle) {
      status("The notebook needs HTTPS, or a page on this computer.");
      return;
    }
    const params = new URLSearchParams(location.search);
    if (params.has("code") || params.has("error")) {
      token = await signedIn(params);
      await load();
      return;
    }
    const config = await fetch("/approve/config");
    const body = await config.json();
    if (!config.ok) {
      status(typeof body.detail === "string" ? body.detail : "The notebook isn't set up here.");
      return;
    }
    status("Signing you in…");
    await signIn(body.signin);
  } catch (error) {
    status(error.message);
  }
}

document.addEventListener("DOMContentLoaded", main);
