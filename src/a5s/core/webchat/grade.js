"use strict";
// Grading samples of agents' changes. The page signs the grader in to show the samples they
// may grade. They choose a grade for each they grade, and send them together, signing in
// afresh: that sign-in's nonce commits to exactly those grades of exactly those samples, so
// the identity provider signs them. It shows only text, and keeps each sign-in in memory alone.

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

async function signIn(signin, pending, fresh) {
  // To the identity provider: to see what waits, or afresh, to grade.
  Object.assign(pending, { verifier: random(), state: random() });
  store.setItem(PENDING, JSON.stringify(pending));
  const url = new URL(signin.authorization_endpoint);
  const query = {
    response_type: "code", client_id: signin.client_id, redirect_uri: BACK, scope: signin.scope,
    state: pending.state, nonce: pending.nonce, code_challenge: await sha256(pending.verifier),
    code_challenge_method: "S256",
  };
  if (fresh) query.max_age = "0";
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
  return { pending, token: tokens.id_token };
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

let signinConfig = null;
const chosen = new Map();  // each sample's id, and the grade chosen for it

async function send() {
  // Sign in afresh, with a nonce that commits to exactly these grades of these samples.
  const grades = [...chosen.entries()].sort((a, b) => a[0] - b[0]);
  if (!grades.length) {
    status("Choose a grade for a sample first.");
    return;
  }
  const pending = { kind: "grade", grades: Object.fromEntries(grades), salt: random() };
  pending.nonce = await sha256(`a5s grades samples ${grades.map(([s, g]) => `${s}:${g}`).join(",")} ${pending.salt}`);
  status(`Signing you in again, to give ${grades.length === 1 ? "this grade" : "these grades"} alone…`);
  await signIn(signinConfig, pending, true);
}

function show(found) {
  $("who").textContent = found.you;
  $("list").replaceChildren();
  chosen.clear();
  for (const sample of found.samples) {
    const block = document.createElement("article");
    const title = document.createElement("h3");
    title.textContent = `${sample.agent}, ${sample.action} in ${sample.part}: ${sample.kind === "proposal"
      ? `asked for, and ${sample.decided === "approve" ? "approved" : "rejected"}` : "made at level 2"}`;
    const said = document.createElement("p");
    said.className = "said";
    said.textContent = sample.said;
    block.append(title, said);
    if (sample.flags.length) {
      const flags = document.createElement("ul");
      flags.className = "flags";
      for (const flag of sample.flags) {
        const item = document.createElement("li");
        item.textContent = flag;
        flags.append(item);
      }
      block.append(flags);
    }
    const buttons = document.createElement("p");
    for (const grade of ["right", "wrong", "critical"]) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = grade[0].toUpperCase() + grade.slice(1);
      button.setAttribute("aria-pressed", "false");
      button.addEventListener("click", () => {
        const again = chosen.get(sample.id) === grade;
        if (again) chosen.delete(sample.id);
        else chosen.set(sample.id, grade);
        for (const other of buttons.querySelectorAll("button")) other.setAttribute("aria-pressed", "false");
        button.setAttribute("aria-pressed", again ? "false" : "true");
        status(`${chosen.size} chosen: send them when you're ready.`);
      });
      buttons.append(button);
    }
    block.append(buttons);
    $("list").append(block);
  }
  $("waiting").hidden = found.samples.length === 0;
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
    signinConfig = body.signin;
    $("send").addEventListener("click", () => send().catch((e) => status(e.message)));
    const params = new URLSearchParams(location.search);
    if (params.has("code") || params.has("error")) {
      const { pending, token } = await signedIn(params);
      let done = "";
      if (pending.kind === "grade") {
        const graded = await ask("/grade/samples", token, { grades: pending.grades, salt: pending.salt });
        const given = Object.values(graded.grades);
        done = given.length === 1 ? `Graded ${given[0]}. ` : `Graded ${given.length} samples. `;
      }
      const found = await ask("/grade/review", token);
      show(found);
      status(done + (found.samples.length ? "" : "Nothing else waits for you to grade."));
      return;
    }
    status("Signing you in, to show what waits for you to grade…");
    await signIn(signinConfig, { kind: "review", nonce: random() }, false);
  } catch (error) {
    status(error.message);
  }
}

document.addEventListener("DOMContentLoaded", main);
