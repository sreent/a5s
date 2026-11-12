"use strict";
// Someone's own page for their tasks: each long task they asked an agent for, how it stands,
// what it waits on and what it has spent, to read and to stop. They sign in with their
// organisation's identity provider; the page shows only text, the tasks whose words name only
// records they may see, and keeps the sign-in in memory alone.

const $ = (id) => document.getElementById(id);
const store = window.sessionStorage;
const PENDING = "a5s.tasks";
const BACK = `${location.origin}/tasks/`;
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
  history.replaceState(null, "", "/tasks/");
  const pending = JSON.parse(store.getItem(PENDING) || "null");
  store.removeItem(PENDING);
  if (params.has("error")) {
    throw new Error(`Signing in didn't work: ${params.get("error_description") || params.get("error")}`);
  }
  const again = "Signing in didn't come back the way it went out. Open your tasks again.";
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

function line(text, className) {
  const p = document.createElement("p");
  p.textContent = text;
  if (className) p.className = className;
  return p;
}

async function load() {
  const now = await call("/tasks/api");
  $("who").textContent = now.you;
  const into = $("tasks");
  into.replaceChildren();
  for (const task of now.tasks) {
    const item = document.createElement("li");
    item.append(line(`${task.task}, with the ${task.agent}: ${task.status}, ${task.progress}% done`));
    if (task.withheld) {
      item.append(line("What it's for names records you may no longer see, so it isn't shown here.", "note"));
    } else {
      item.append(line(task.what));
      if (task.plan.length) {
        const steps = document.createElement("ol");
        for (const step of task.plan) {
          const each = document.createElement("li");
          each.textContent = `${step.content} (${step.status.replace("_", " ")})`;
          steps.append(each);
        }
        item.append(steps);
      }
      if (task.found !== undefined) {
        item.append(line(`What it found: ${typeof task.found === "string" ? task.found : JSON.stringify(task.found)}`));
      }
      if ((task["so far"] || []).length) {
        item.append(line(`So far: ${task["so far"].map((each) => (typeof each === "string" ? each : JSON.stringify(each))).join("; ")}`, "note"));
      }
      if (task.why) item.append(line(`Why: ${task.why}`, "note"));
      if (task.said) item.append(line(`It needed: ${task.needed || "you"}. You said: ${task.said}`, "note"));
    }
    item.append(line(`It has until ${task["has until"]}, and has spent ${task.spent}. Last changed on ${task.updated}.`, "note"));
    if (!task.ended) {
      const stop = document.createElement("button");
      stop.type = "button";
      stop.textContent = "Cancel";
      stop.addEventListener("click", async () => {
        try {
          await call(`/tasks/api/${task.task}/cancel`, "POST");
          await load();
          status(`Cancelled ${task.task}.`);
        } catch (error) {
          status(error.message);
        }
      });
      item.append(stop);
    }
    into.append(item);
  }
  const again = $("repeats");
  again.replaceChildren();
  for (const repeat of now.repeats) {
    const item = document.createElement("li");
    item.append(line(`${repeat.repeat}, with the ${repeat.agent}: ${repeat.when}, ${repeat.status}`));
    item.append(line(repeat.what));
    if (repeat["last task"]) item.append(line(`Its last task: ${repeat["last task"]}.`, "note"));
    if (repeat.status !== "stopped") {
      const stop = document.createElement("button");
      stop.type = "button";
      stop.textContent = "Stop";
      stop.addEventListener("click", async () => {
        try {
          await call(`/tasks/api/${repeat.repeat}/cancel`, "POST");
          await load();
          status(`Stopped ${repeat.repeat}.`);
        } catch (error) {
          status(error.message);
        }
      });
      item.append(stop);
    }
    again.append(item);
  }
  if (!now.repeats.length) again.append(line("None. Ask an agent to do a task every week, say, in your chat with it.", "note"));
  status(now.tasks.length ? "" : "No tasks yet. Ask an agent for one in your chat with it.");
}

async function main() {
  try {
    if (!window.crypto || !crypto.subtle) {
      status("Your tasks' page needs HTTPS, or a page on this computer.");
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
      status(typeof body.detail === "string" ? body.detail : "Your tasks' page isn't set up here.");
      return;
    }
    status("Signing you in…");
    await signIn(body.signin);
  } catch (error) {
    status(error.message);
  }
}

document.addEventListener("DOMContentLoaded", main);
