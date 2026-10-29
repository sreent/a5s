"use strict";
// The web chat. A person signs in with their organisation's identity provider, or in
// development says who they are, and talks to a5s's agents through the core's local
// channel, as the command line does. It shows only text, and keeps the sign-in for
// this tab alone.

const $ = (id) => document.getElementById(id);
const store = window.sessionStorage;
const state = { config: null, agent: null, person: null };
const SIGNING_IN = "signing in";

const pause = (ms) => new Promise((done) => setTimeout(done, ms));
const status = (text) => { $("status").textContent = text; };

// Signing in, with the authorization code flow and PKCE

function b64url(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

const random = () => b64url(crypto.getRandomValues(new Uint8Array(32)));

function claims(jwt) {
  const part = jwt.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
  return JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(part), (c) => c.charCodeAt(0))));
}

async function exchange(body) {
  // The core passes this on to the identity provider, so the page needn't reach it.
  const answer = await fetch("/chat/token", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const tokens = await answer.json();
  if (!answer.ok || !tokens.id_token) {
    throw new Error(`Signing in didn't work: ${tokens.error_description || tokens.error || tokens.detail || answer.status}`);
  }
  return tokens;
}

function keep(tokens) {
  const before = JSON.parse(store.getItem("a5s.tokens") || "{}");
  store.setItem("a5s.tokens", JSON.stringify({ id: tokens.id_token, refresh: tokens.refresh_token || before.refresh }));
}

async function signIn() {
  // True once signed in. Otherwise it goes to the identity provider, which comes back here.
  const signin = state.config.signin;
  const back = `${location.origin}/chat/`;
  const params = new URLSearchParams(location.search);
  if (params.has("code") || params.has("error")) {
    history.replaceState(null, "", "/chat/");
    const pending = JSON.parse(store.getItem("a5s.pending") || "null");
    store.removeItem("a5s.pending");
    if (params.has("error")) {
      throw new Error(`Signing in didn't work: ${params.get("error_description") || params.get("error")}`);
    }
    if (!pending || params.get("state") !== pending.state) {
      throw new Error("Signing in didn't come back the way it went out. Reload to try again.");
    }
    const tokens = await exchange({
      grant_type: "authorization_code", code: params.get("code"),
      code_verifier: pending.verifier, redirect_uri: back,
    });
    if (claims(tokens.id_token).nonce !== pending.nonce) {
      throw new Error("Signing in didn't come back the way it went out. Reload to try again.");
    }
    keep(tokens);
    return true;
  }
  if (store.getItem("a5s.tokens")) return true;
  if (!window.crypto || !crypto.subtle) {
    throw new Error("Signing in needs HTTPS, or a page on this computer.");
  }
  const pending = { verifier: random(), state: random(), nonce: random() };
  store.setItem("a5s.pending", JSON.stringify(pending));
  const challenge = b64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(pending.verifier)));
  const url = new URL(signin.authorization_endpoint);
  const query = {
    response_type: "code", client_id: signin.client_id, redirect_uri: back, scope: signin.scope,
    state: pending.state, nonce: pending.nonce, code_challenge: challenge, code_challenge_method: "S256",
  };
  for (const [key, value] of Object.entries(query)) url.searchParams.set(key, value);
  location.assign(url.toString());
  return false;
}

async function bearer() {
  // A sign-in that's still good for half a minute, refreshed if need be.
  const tokens = JSON.parse(store.getItem("a5s.tokens") || "null");
  if (!tokens) return null;
  if (claims(tokens.id).exp * 1000 - Date.now() > 30000) return tokens.id;
  if (tokens.refresh) {
    try {
      keep(await exchange({ grant_type: "refresh_token", refresh_token: tokens.refresh }));
      return JSON.parse(store.getItem("a5s.tokens")).id;
    } catch {
      // sign in again
    }
  }
  store.removeItem("a5s.tokens");
  return null;
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json" };
  let url = path;
  if (state.config.signin) {
    const token = await bearer();
    if (!token) { await signIn(); throw new Error(SIGNING_IN); }
    headers.Authorization = `Bearer ${token}`;
  } else {
    url += `${url.includes("?") ? "&" : "?"}person=${encodeURIComponent(state.person)}`;
  }
  const answer = await fetch(url, { ...options, headers });
  if (answer.status === 401 && state.config.signin) {
    store.removeItem("a5s.tokens");
    await signIn();
    throw new Error(SIGNING_IN);
  }
  return answer;
}

// Showing the conversation: text only, with https links, **bold** and `code`

function render(element, text) {
  const pattern = /(https:\/\/[^\s<>"'`)\]]+|\*\*[^*\n]+\*\*|`[^`\n]+`)/g;
  for (const part of text.split(pattern)) {
    if (!part) continue;
    let node;
    if (part.startsWith("https://")) {
      node = document.createElement("a");
      node.href = part;
      node.rel = "noopener noreferrer";
      node.target = "_blank";
      node.textContent = part;
    } else if (part.length > 4 && part.startsWith("**") && part.endsWith("**")) {
      node = document.createElement("strong");
      node.textContent = part.slice(2, -2);
    } else if (part.length > 2 && part.startsWith("`") && part.endsWith("`")) {
      node = document.createElement("code");
      node.textContent = part.slice(1, -1);
    } else {
      node = document.createTextNode(part);
    }
    element.append(node);
  }
}

function say(message) {
  const item = document.createElement("li");
  item.className = message.from === "you" ? "you" : message.from === "a5s" ? "a5s" : "agent";
  const who = document.createElement("strong");
  who.textContent = message.from === "you" ? "You" : message.from;
  const when = document.createElement("time");
  if (message.at) {
    const at = new Date(message.at);
    when.dateTime = at.toISOString();
    when.textContent = at.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  }
  const body = document.createElement("div");
  render(body, message.text);
  item.append(who, " ", when, body);
  $("conversation").append(item);
  item.scrollIntoView({ block: "end" });
}

// Talking to an agent

async function open(agent) {
  state.agent = agent;
  $("conversation").replaceChildren();
  const answer = await api(`/channels/local/conversation?agent=${encodeURIComponent(agent)}`);
  if (answer.ok) (await answer.json()).messages.forEach(say);
}

async function send(text) {
  const agent = state.agent;
  say({ from: "you", text, at: new Date().toISOString() });
  const sent = await api("/channels/local/messages", {
    method: "POST", body: JSON.stringify({ agent, text, person: state.person }),
  });
  const body = await sent.json();
  if (sent.status !== 202) {
    say({ from: "a5s", text: typeof body.detail === "string" ? body.detail : "That didn't send. Try again." });
    return;
  }
  for (let tries = 0; tries < 24; tries += 1) {  // ten minutes
    const answer = await api(`/channels/local/messages/${body.message}?wait=25`);
    const said = answer.ok ? (await answer.json()).messages : [];
    if (said.length) {
      if (state.agent === agent) said.forEach(say);
      return;
    }
  }
  status("No answer yet. It'll be in your conversation when it comes.");
}

async function listen() {
  // What a5s and the agents write without being asked, such as reminders.
  for (;;) {
    try {
      const answer = await api("/channels/local/inbox?wait=25");
      if (!answer.ok) { await pause(5000); continue; }
      for (const message of (await answer.json()).messages) {
        if (message.from === state.agent || message.about === state.agent) say(message);
        else say({ ...message, text: `(about the ${message.about || "agents"}) ${message.text}` });
      }
    } catch (error) {
      if (error.message === SIGNING_IN) return;
      await pause(5000);
    }
  }
}

function askName() {
  return new Promise((done) => {
    const form = $("name");
    form.hidden = false;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const person = $("person").value.trim();
      if (!person) return;
      form.hidden = true;
      store.setItem("a5s.person", person);
      done(person);
    });
  });
}

function signOut() {
  const tokens = JSON.parse(store.getItem("a5s.tokens") || "null");
  store.clear();
  const end = state.config.signin && state.config.signin.end_session_endpoint;
  if (end && tokens) {
    const url = new URL(end);
    url.searchParams.set("id_token_hint", tokens.id);
    url.searchParams.set("client_id", state.config.signin.client_id);
    url.searchParams.set("post_logout_redirect_uri", `${location.origin}/chat/`);
    location.assign(url.toString());
  } else {
    location.reload();
  }
}

async function main() {
  try {
    state.config = await (await fetch("/chat/config")).json();
    if (state.config.signin) {
      if (!(await signIn())) return;  // gone to the identity provider
      const who = claims(JSON.parse(store.getItem("a5s.tokens")).id);
      $("who").textContent = who.name || who.preferred_username || "";
      $("signout").hidden = false;
      $("signout").addEventListener("click", signOut);
    } else if (state.config.development) {
      state.person = store.getItem("a5s.person") || await askName();
      $("who").textContent = `${state.person}, in development`;
    } else {
      status("The web chat needs sign-in, which isn't set up here yet: see A5S_WEBCHAT_CLIENT_ID.");
      return;
    }
    for (const agent of state.config.agents) {
      const option = document.createElement("option");
      option.value = agent;
      option.textContent = agent;
      $("agent").append(option);
    }
    $("agent").addEventListener("change", (event) => open(event.target.value));
    $("compose").hidden = false;
    $("compose").addEventListener("submit", (event) => {
      event.preventDefault();
      const text = $("text").value.trim();
      if (!text) return;
      $("text").value = "";
      send(text).catch((error) => { if (error.message !== SIGNING_IN) status(error.message); });
    });
    $("text").addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        $("compose").requestSubmit();
      }
    });
    await open(state.config.agents[0]);
    listen();
  } catch (error) {
    if (error.message !== SIGNING_IN) status(error.message);
  }
}

document.addEventListener("DOMContentLoaded", main);
