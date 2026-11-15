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
  if (signin.acr_values) query.acr_values = signin.acr_values;  // the level what counts needs
  for (const [key, value] of Object.entries(query)) url.searchParams.set(key, value);
  location.assign(url.toString());
}

async function signedIn(params) {
  history.replaceState(null, "", "/grade/");
  const pending = JSON.parse(store.getItem(PENDING) || "null");
  store.removeItem(PENDING);
  const again = "Signing in didn't come back the way it went out. Open the page again.";
  if (!pending || params.get("state") !== pending.state) throw new Error(again);
  // The provider's words only for a sign-in this tab sent, so a link can't put its own on
  // the page as if they were (round 11, E-3)
  if (params.has("error")) {
    throw new Error(`Signing in didn't work: ${params.get("error_description") || params.get("error")}`);
  }
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

function element(tag, text, className) {
  const found = document.createElement(tag);
  if (text !== undefined && text !== null) found.textContent = String(text);
  if (className) found.className = className;
  return found;
}

const day = (at) => new Date(at).toLocaleDateString([], { day: "numeric", month: "short" });

// How it went, in the colour that means it: a person's yes or no, or the agent's own change
const OUTCOMES = { approve: ["approved", "good"], reject: ["rejected", "bad"] };

function grades(sample, what) {
  // Right, wrong or critical: the one chosen shows in its colour, and choosing it again
  // takes it back
  const group = element("div", null, "grades");
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", `Your grade for: ${what}`);
  for (const grade of ["right", "wrong", "critical"]) {
    const button = element("button", grade[0].toUpperCase() + grade.slice(1), grade);
    button.type = "button";
    button.setAttribute("aria-pressed", "false");
    button.addEventListener("click", () => {
      const again = chosen.get(sample.id) === grade;
      if (again) chosen.delete(sample.id);
      else chosen.set(sample.id, grade);
      for (const other of group.querySelectorAll("button")) other.setAttribute("aria-pressed", "false");
      button.setAttribute("aria-pressed", again ? "false" : "true");
      status(chosen.size ? `${chosen.size} chosen: send them when you're ready.` : "");
    });
    group.append(button);
  }
  return group;
}

function card(sample) {
  // A sample on the card decisions are made on (docs/design.md): who did it, what it did in
  // the words code worked out, never the agent's own, how it went, what code flagged, and
  // the grader's grade
  const [what, ...rest] = sample.said.split("\n");
  const asked = sample.kind === "proposal";
  const block = element("section", null, "approval sample");
  block.dataset.sample = sample.id;
  block.setAttribute("aria-labelledby", `title-${sample.id}`);
  const body = element("div", null, "approval-body");
  block.append(element("div", null, "approval-stripe"), body);

  const who = element("div", null, "who");
  const mark = element("span", null, "avatar agent");
  mark.setAttribute("aria-hidden", "true");
  if (window.a5s) mark.append(window.a5s.icon("agent"));
  const names = element("span");
  names.append(element("span", asked ? `The ${sample.agent} asked` : `The ${sample.agent} acted on its own`, "who-name"),
               element("span", `${sample.action} in ${sample.part} · sampled ${day(sample.drawn_at)}`, "who-about"));
  who.append(mark, names);
  const title = element("h2", what, "approval-title");
  title.id = `title-${sample.id}`;
  body.append(who, title);
  if (rest.length) body.append(element("p", rest.join("\n"), "said"));
  const [outcome, tone] = asked ? (OUTCOMES[sample.decided] || [sample.decided, "idle"]) : ["made at level 2", "changes"];
  const how = element("p");
  how.append(element("span", outcome, `badge ${tone}`));
  body.append(how);
  if (sample.flags.length) {
    const box = element("div", null, "approval-know");
    const flags = element("ul");
    flags.append(...sample.flags.map((flag) => element("li", flag)));
    box.append(element("p", "What code flagged", "label"), flags);
    body.append(box);
  }
  for (const [key, record] of Object.entries(sample.records || {})) {
    if (!record || !/^https?:\/\//i.test(record.link || "")) continue;  // a web page, and nothing else
    const open = element("a", `Open ${key}`);
    open.href = record.link;
    open.rel = "noopener noreferrer";
    open.target = "_blank";
    const line = element("p");
    line.append(open);
    body.append(line);
  }
  body.append(grades(sample, what));
  return block;
}

function show(found) {
  $("who").textContent = found.you;
  chosen.clear();
  $("list").replaceChildren(...found.samples.map(card));
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
      window.a5s?.signedIn(token);  // the sidebar, of the pages they may use
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
