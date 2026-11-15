"use strict";
// Approving a version of a5s's settings, from the card in an approver's chat. They sign in
// afresh with their organisation's identity provider, and the sign-in's nonce commits to
// approving exactly this version, so the provider signs the decision. The page shows what
// the version changes, as the core works it out, and approves it only when they say so.
// It shows only text, and keeps the sign-in in memory alone.

const $ = (id) => document.getElementById(id);
const store = window.sessionStorage;
const PENDING = "a5s.approving";
const BACK = `${location.origin}/approve/`;

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

async function signIn(signin, version) {
  // To the identity provider, to sign in afresh for approving this version alone.
  const pending = { version, salt: random(), verifier: random(), state: random() };
  pending.nonce = await sha256(`a5s approves settings ${version} ${pending.salt}`);
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
  history.replaceState(null, "", "/approve/");
  const pending = JSON.parse(store.getItem(PENDING) || "null");
  store.removeItem(PENDING);
  if (params.has("error")) {
    throw new Error(`Signing in didn't work: ${params.get("error_description") || params.get("error")}`);
  }
  const again = "Signing in didn't come back the way it went out. Open the link on your card again.";
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
  return { version: pending.version, salt: pending.salt, token: tokens.id_token };
}

async function ask(path, signed) {
  const answer = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${signed.token}` },
    body: JSON.stringify({ salt: signed.salt }),
  });
  const body = await answer.json();
  if (!answer.ok) throw new Error(typeof body.detail === "string" ? body.detail : `a5s said ${answer.status}.`);
  return body;
}

const STANDING = {
  applied: "It's been approved and applied already.",
  superseded: "A newer version is in force, so this one can't be approved any more.",
};

function element(tag, text, className) {
  const found = document.createElement(tag);
  if (text !== undefined && text !== null) found.textContent = String(text);
  if (className) found.className = className;
  return found;
}

// A change in the words code worked out, marked where it widens what agents do
function changed(change) {
  const item = element("li", change.text);
  if (change.widens) item.append(" ", element("span", "widens what agents do", "badge changes"));
  return item;
}

// Where the version stands, on its card: a word, in the colour that means it
function standing(text, tone) {
  $("standing").textContent = text;
  $("standing").className = `badge ${tone}`;
}

const initials = (name) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");

function show(version, signed) {
  $("who").textContent = version.you;
  const when = new Date(version.proposed_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  // Who asked for it, a person, round with their initials, as on every page; or when a5s
  // proposed it, if it came from elsewhere, such as signed files
  const words = element("span");
  if (version.asked_by) {
    const mark = element("span", initials(version.asked_by), "avatar");
    mark.setAttribute("aria-hidden", "true");
    words.append(element("span", `${version.asked_by} asked for it`, "who-name"),
                 element("span", `proposed ${when}`, "who-about"));
    $("asker").replaceChildren(mark, words);
  } else {
    words.append(element("span", `Proposed ${when}`, "who-about"));
    $("asker").replaceChildren(words);
  }
  $("title").textContent = `Version ${version.serial} of the settings`;
  $("summary").textContent = version.in_force === null ? "What it sets, with nothing in force yet"
    : `What it changes from version ${version.in_force}, the one in force`;
  $("changes").replaceChildren(...version.changes.map(changed));
  $("approvals").textContent = version.approved_by.length ? version.approved_by.join(", ") : "nobody yet";
  $("needs").textContent = version.needs.join("; ");
  $("needs-row").hidden = !version.needs.length;
  $("whole").replaceChildren(...version.whole.map((line) => element("li", line)));
  $("version").hidden = false;
  if (version.status !== "waiting") {
    standing(version.status === "applied" ? "in force" : version.status === "superseded" ? "superseded" : "refused",
             version.status === "applied" ? "good" : version.status === "superseded" ? "idle" : "bad");
    status(STANDING[version.status] || `a5s couldn't apply it: ${version.status.replace(/^refused: /, "")}`);
  } else if (version.you_approved) {
    standing("you approved it", "good");
    status(version.needs.length ? `You've approved it. It goes in force once nothing more is missing: ${version.needs.join("; ")}.` : "You've approved it. a5s puts it in force within a minute, as it needs nothing more.");
  } else {
    standing("waiting for you", "warn");
    $("approve").textContent = `Approve version ${version.serial}`;
    $("decision").hidden = false;
    $("approve").addEventListener("click", async () => {
      if (!signed.token) return;
      $("approve").disabled = true;
      try {
        const done = await ask(`/approve/settings/${signed.version}`, signed);
        signed.token = null;  // it's done its one job
        $("decision").hidden = true;
        standing("you approved it", "good");
        if (done.needs.length) $("approvals").textContent = [...version.approved_by, version.you].join(", ");
        status(done.needs.length ? `You approved version ${done.serial}. It goes in force once nothing more is missing: ${done.needs.join("; ")}.` : `You approved version ${done.serial}. a5s puts it in force within a minute, as it needs nothing more.`);
      } catch (error) {
        status(error.message);
        $("approve").disabled = false;
      }
    });
  }
}

async function main() {
  try {
    const params = new URLSearchParams(location.search);
    if (params.has("code") || params.has("error")) {
      const signed = await signedIn(params);
      status("");
      show(await ask(`/approve/settings/${signed.version}/review`, signed), signed);
      return;
    }
    const version = params.get("settings") || "";
    if (!/^[0-9a-f]{64}$/.test(version)) {
      status("This link doesn't name a version of the settings. Open the one on your card.");
      return;
    }
    if (!window.crypto || !crypto.subtle) {
      status("Approving needs HTTPS, or a page on this computer.");
      return;
    }
    const config = await fetch("/approve/config");
    const body = await config.json();
    if (!config.ok) {
      status(typeof body.detail === "string" ? body.detail : "Approving isn't set up here.");
      return;
    }
    status("Signing you in again, to approve this version alone…");
    await signIn(body.signin, version);
  } catch (error) {
    status(error.message);
  }
}

document.addEventListener("DOMContentLoaded", main);
