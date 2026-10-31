"use strict";
// Deciding the changes agents asked for, from the card in a decider's chat. The page signs
// them in to show what waits for them, then afresh to decide: that sign-in's nonce commits to
// approving or rejecting exactly the changes they chose, so the identity provider signs the
// decision. It shows only text, and keeps each sign-in in memory alone.

const $ = (id) => document.getElementById(id);
const store = window.sessionStorage;
const PENDING = "a5s.deciding";
const BACK = `${location.origin}/decide/`;

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
  // To the identity provider: to see what waits, or afresh, to decide.
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
  // Back from the identity provider: the sign-in, if it's the one this page asked for.
  history.replaceState(null, "", "/decide/");
  const pending = JSON.parse(store.getItem(PENDING) || "null");
  store.removeItem(PENDING);
  if (params.has("error")) {
    throw new Error(`Signing in didn't work: ${params.get("error_description") || params.get("error")}`);
  }
  const again = "Signing in didn't come back the way it went out. Open the link on your card again.";
  if (!pending || params.get("state") !== pending.state) throw new Error(again);
  const answer = await fetch("/decide/token", {  // the core passes it on to the provider
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

async function decide(digests, decision) {
  // Sign in afresh, with a nonce that commits to this decision on exactly these changes.
  const pending = { kind: "decide", proposals: [...digests].sort(), decision, salt: random() };
  pending.nonce = await sha256(`a5s ${decision}s proposals ${pending.proposals.join(",")} ${pending.salt}`);
  status(`Signing you in again, to ${decision} ${digests.length === 1 ? "this change" : "these changes"} alone…`);
  await signIn(signinConfig, pending, true);
}

function show(found, named) {
  $("who").textContent = found.you;
  const waiting = found.proposals.filter((p) => p.status === "waiting" && !p.yours);
  const decided = found.proposals.filter((p) => p.status !== "waiting" || p.yours);
  waiting.sort((a, b) => (b.digest === named) - (a.digest === named));
  for (const proposal of waiting) {
    const block = document.createElement("article");
    const title = document.createElement("h3");
    title.textContent = proposal.key + (proposal.sensitive ? ": decided on its own" : "");
    const said = document.createElement("p");
    said.className = "said";
    said.textContent = proposal.said;
    block.append(title, said);
    if (proposal.flags.length) {
      const flags = document.createElement("ul");
      flags.className = "flags";
      for (const flag of proposal.flags) {
        const item = document.createElement("li");
        item.textContent = flag;
        flags.append(item);
      }
      block.append(flags);
    }
    const when = document.createElement("p");
    when.className = "note";
    when.textContent = `It lapses on ${new Date(proposal.lapses_at).toLocaleDateString([], { dateStyle: "medium" })} unless someone decides it.`;
    const buttons = document.createElement("p");
    for (const decision of ["approve", "reject"]) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = decision === "approve" ? "Approve" : "Reject";
      button.addEventListener("click", () => decide([proposal.digest], decision).catch((e) => status(e.message)));
      buttons.append(button);
    }
    if (!proposal.sensitive) {
      const tick = document.createElement("input");
      tick.type = "checkbox";
      tick.className = "tick";
      tick.value = proposal.digest;
      tick.setAttribute("aria-label", `Decide ${proposal.key} with the others ticked`);
      buttons.append(tick);
    }
    block.append(when, buttons);
    $("list").append(block);
  }
  $("waiting").hidden = waiting.length === 0;
  $("together").hidden = waiting.filter((p) => !p.sensitive).length < 2;
  for (const decision of ["approve", "reject"]) {
    $(`${decision}-ticked`).addEventListener("click", () => {
      const ticked = [...document.querySelectorAll(".tick:checked")].map((t) => t.value);
      if (ticked.length) decide(ticked, decision).catch((e) => status(e.message));
    });
  }
  for (const proposal of decided) {
    const item = document.createElement("li");
    item.textContent = proposal.outcome || `${proposal.key}: you've decided it, and a5s acts on it within a minute.`;
    $("decided").append(item);
  }
  $("earlier").hidden = decided.length === 0;
  if (!waiting.length) status("Nothing waits for your decision.");
}

async function main() {
  try {
    const params = new URLSearchParams(location.search);
    if (!window.crypto || !crypto.subtle) {
      status("Deciding needs HTTPS, or a page on this computer.");
      return;
    }
    const config = await fetch("/decide/config");
    const body = await config.json();
    if (!config.ok) {
      status(typeof body.detail === "string" ? body.detail : "Deciding isn't set up here.");
      return;
    }
    signinConfig = body.signin;
    if (params.has("code") || params.has("error")) {
      const { pending, token } = await signedIn(params);
      if (pending.kind === "decide") {
        const done = await ask("/decide/proposals", token,
                               { proposals: pending.proposals, decision: pending.decision, salt: pending.salt });
        const what = done.decided.join(", ");
        status(done.decision === "approve"
          ? `You approved ${what}. a5s makes each change within a minute, if its records haven't changed.`
          : `You rejected ${what}. a5s tells whoever asked for it.`);
        return;
      }
      status("");
      show(await ask("/decide/review", token), pending.named);
      return;
    }
    const named = params.get("proposal") || "";
    status("Signing you in, to show what waits for your decision…");
    await signIn(signinConfig, { kind: "review", named, nonce: random() }, false);
  } catch (error) {
    status(error.message);
  }
}

document.addEventListener("DOMContentLoaded", main);
