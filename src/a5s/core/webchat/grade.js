"use strict";
// Grading samples of agents' changes. The page signs the grader in, shows the samples they
// may grade, and sends each grade once. It shows only text, and keeps the sign-in in memory.

const $ = (id) => document.getElementById(id);
const store = window.sessionStorage;
const PENDING = "a5s.grading";
const BACK = `${location.origin}/grade/`;

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
  const pending = { nonce: random(), verifier: random(), state: random() };
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
  history.replaceState(null, "", "/grade/");
  const pending = JSON.parse(store.getItem(PENDING) || "null");
  store.removeItem(PENDING);
  if (params.has("error")) {
    throw new Error(`Signing in didn't work: ${params.get("error_description") || params.get("error")}`);
  }
  const again = "Signing in didn't come back the way it went out. Open the page again.";
  if (!pending || params.get("state") !== pending.state) throw new Error(again);
  const answer = await fetch("/grade/token", {
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

async function ask(path, token, body) {
  const answer = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body || {}),
  });
  const found = await answer.json();
  if (!answer.ok) throw new Error(typeof found.detail === "string" ? found.detail : `a5s said ${answer.status}.`);
  return found;
}

function show(found, token) {
  $("who").textContent = found.you;
  for (const sample of found.samples) {
    const block = document.createElement("article");
    const title = document.createElement("h3");
    title.textContent = `${sample.agent}, ${sample.action} in ${sample.part}: ${sample.kind === "proposal"
      ? `asked for, and ${sample.decided === "approve" ? "approved" : "rejected"}` : "made at level 2"}`;
    const said = document.createElement("p");
    said.className = "said";
    said.textContent = sample.said;
    const buttons = document.createElement("p");
    for (const grade of ["right", "wrong", "critical"]) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = grade[0].toUpperCase() + grade.slice(1);
      button.addEventListener("click", async () => {
        try {
          await ask(`/grade/samples/${sample.id}`, token, { grade });
          block.remove();
          status(`Graded ${grade}.`);
        } catch (error) {
          status(error.message);
        }
      });
      buttons.append(button);
    }
    block.append(title, said, buttons);
    $("list").append(block);
  }
  $("waiting").hidden = found.samples.length === 0;
  if (!found.samples.length) status("Nothing waits for you to grade.");
}

async function main() {
  try {
    if (!window.crypto || !crypto.subtle) {
      status("Grading needs HTTPS, or a page on this computer.");
      return;
    }
    const config = await fetch("/grade/config");
    const body = await config.json();
    if (!config.ok) {
      status(typeof body.detail === "string" ? body.detail : "Grading isn't set up here.");
      return;
    }
    const params = new URLSearchParams(location.search);
    if (params.has("code") || params.has("error")) {
      const token = await signedIn(params);
      status("");
      show(await ask("/grade/review", token), token);
      return;
    }
    status("Signing you in, to show what waits for you to grade…");
    await signIn(body.signin);
  } catch (error) {
    status(error.message);
  }
}

document.addEventListener("DOMContentLoaded", main);
