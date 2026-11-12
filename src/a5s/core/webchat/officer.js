"use strict";
// The data protection officer's requests: to export, or erase, all a5s keeps about someone.
// They sign in afresh with their organisation's identity provider, and the sign-in's nonce
// commits to exactly this request, so the provider signs it. Someone from the team that runs
// a5s then carries it out, once, within ten minutes. The page shows only text, and keeps the
// sign-in in memory alone.

const $ = (id) => document.getElementById(id);
const store = window.sessionStorage;
const PENDING = "a5s.asking";
const BACK = `${location.origin}/officer/`;

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

async function signIn(signin, action, person) {
  // To the identity provider, to sign in afresh for this request alone.
  const pending = { action, person, salt: random(), verifier: random(), state: random() };
  pending.nonce = await sha256(`a5s officer ${action} ${person} ${pending.salt}`);
  store.setItem(PENDING, JSON.stringify(pending));
  const url = new URL(signin.authorization_endpoint);
  const query = {
    response_type: "code", client_id: signin.client_id, redirect_uri: BACK, scope: signin.scope,
    state: pending.state, nonce: pending.nonce, code_challenge: await sha256(pending.verifier),
    code_challenge_method: "S256", max_age: "0",
  };
  if (signin.acr_values) query.acr_values = signin.acr_values;  // the level what counts needs
  for (const [key, value] of Object.entries(query)) url.searchParams.set(key, value);
  location.assign(url.toString());
}

async function signedIn(params) {
  // Back from the identity provider: the sign-in, if it's the one this page asked for.
  history.replaceState(null, "", "/officer/");
  const pending = JSON.parse(store.getItem(PENDING) || "null");
  store.removeItem(PENDING);
  if (params.has("error")) {
    throw new Error(`Signing in didn't work: ${params.get("error_description") || params.get("error")}`);
  }
  const again = "Signing in didn't come back the way it went out. Ask again.";
  if (!pending || params.get("state") !== pending.state) throw new Error(again);
  const answer = await fetch("/officer/token", {  // the core passes it on to the provider
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ grant_type: "authorization_code", code: params.get("code"),
                           code_verifier: pending.verifier, redirect_uri: BACK }),
  });
  const tokens = await answer.json();
  if (!answer.ok || !tokens.id_token) {
    throw new Error(`Signing in didn't work: ${tokens.error_description || tokens.error || tokens.detail || answer.status}`);
  }
  if (claims(tokens.id_token).nonce !== pending.nonce) throw new Error(again);
  return { action: pending.action, person: pending.person, salt: pending.salt, token: tokens.id_token };
}

async function ask(signed) {
  const answer = await fetch("/officer/requests", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${signed.token}` },
    body: JSON.stringify({ action: signed.action, person: signed.person, salt: signed.salt }),
  });
  const body = await answer.json();
  if (!answer.ok) throw new Error(typeof body.detail === "string" ? body.detail : `a5s said ${answer.status}.`);
  return body;
}

async function main() {
  try {
    const params = new URLSearchParams(location.search);
    if (params.has("code") || params.has("error")) {
      const asked = await ask(await signedIn(params));  // its one job done, it's let go
      const whom = asked.name ? `${asked.name} (${asked.person})` : asked.person;
      status(`You asked to ${asked.asked} all a5s keeps about ${whom}. Someone from the team ` +
             `that runs a5s carries it out, once, within ${asked.lasts}: ${asked.command}`);
      return;
    }
    const answer = await fetch("/officer/config");
    const config = await answer.json();
    if (!answer.ok) throw new Error(typeof config.detail === "string" ? config.detail : `a5s said ${answer.status}.`);
    $("action").addEventListener("change", () => { $("again").hidden = $("action").value !== "erase"; });
    $("ask").addEventListener("submit", async (event) => {
      event.preventDefault();
      const action = $("action").value;
      const person = $("person").value.trim();
      if (!person) {
        status("Name the person, by their id in the directory, or an archive's name.");
      } else if (action === "erase" && $("confirm").value.trim() !== person) {
        status("Type their id again, the same, to confirm it: an erasure can't be undone.");
      } else {
        await signIn(config.signin, action, person);
      }
    });
    $("ask").hidden = false;
  } catch (error) {
    status(error.message);
  }
}

main();
