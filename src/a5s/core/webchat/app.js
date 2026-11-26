"use strict";
// The web chat. A person signs in with their organisation's identity provider, or in
// development says who they are, and talks to a5s's agents through the core's local
// channel, as the command line does. It shows only text, and keeps the sign-in for
// this tab alone.

const $ = (id) => document.getElementById(id);
const store = window.sessionStorage;
const state = { config: null, agent: null, person: null, shown: new Set() };  // shown: by id
const SIGNING_IN = "signing in";

const pause = (ms) => new Promise((done) => setTimeout(done, ms));
const status = (text) => { $("status").textContent = text; };
// Why a file wasn't attached, beside the composer, where the person is looking, never only at
// the top of a long conversation; nothing, once they attach or send again
const refuse = (text) => { $("refused").textContent = text; };

// The chat's own words, in English, with what changes put in. What agents say is theirs, in the
// language they were told to answer in (core/languages.py).
const t = (text, vars) =>
  vars ? text.replace(/\{(\w+)\}/g, (all, name) => (name in vars ? String(vars[name]) : all)) : text;

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
    if (!pending || params.get("state") !== pending.state) {
      throw new Error("Signing in didn't come back the way it went out. Reload to try again.");
    }
    if (params.has("error")) {  // the provider's words, only for a sign-in this tab sent
      throw new Error(`Signing in didn't work: ${params.get("error_description") || params.get("error")}`);
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

// Showing the conversation: text only, with https links to the scenario's records and a5s's own
// pages alone, **bold** and `code`

function render(element, text) {
  const pattern = /(https:\/\/[^\s<>"'`)\]]+|\*\*[^*\n]+\*\*|`[^`\n]+`)/g;
  for (const part of text.split(pattern)) {
    if (!part) continue;
    let node;
    if (part.startsWith("https://") && (state.config.links || []).some((p) => part.startsWith(p))) {
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

// Who said it, as every page marks them (docs/design.md): an agent's rounded square, in the
// agent colour, and a5s's own shield; what people say needs no mark beside "You"
function mark(by) {
  const found = document.createElement("span");
  found.className = by === "a5s" ? "avatar own" : "avatar agent";
  found.setAttribute("aria-hidden", "true");
  if (window.a5s) found.append(window.a5s.icon(by === "a5s" ? "audit" : by === "team" ? "people" : "agent"));
  return found;
}

// When, as the time alone for today, and with the day before that
function stamp(at) {
  const today = at.toDateString() === new Date().toDateString();
  return at.toLocaleString([], today ? { timeStyle: "short" } : { dateStyle: "medium", timeStyle: "short" });
}

// Saying an agent's answer was wrong (core/feedback.py), for its owners to check: with why, in
// their words, if they say, and what its owners will see, said before they send it

function wrongOf(item, message) {
  const ask = document.createElement("button");
  ask.type = "button";
  ask.className = "link said-wrong";
  ask.textContent = t("That's wrong");
  const at = message.at ? stamp(new Date(message.at)) : "";  // which answer, to whoever hears it
  ask.setAttribute("aria-label", at ? t("That's wrong: the {agent}'s answer at {time}", { agent: message.from, time: at })
    : t("That's wrong: the {agent}'s answer", { agent: message.from }));
  ask.addEventListener("click", () => {
    const form = document.createElement("form");
    form.className = "said-wrong";
    const label = document.createElement("label");
    label.textContent = t("What was wrong? Its owners will see this answer, the run behind it and what you write here, and who you are only if the data protection officer lets them.");
    const why = document.createElement("textarea");
    why.rows = 2;
    why.maxLength = 1000;
    label.append(why);
    const send = document.createElement("button");
    send.className = "primary";
    send.textContent = t("Tell its owners");
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.textContent = t("Cancel");
    cancel.addEventListener("click", () => {
      form.replaceWith(ask);
      ask.focus();  // the keyboard back where it was, never at the page's start
    });
    const refused = document.createElement("p");  // why it didn't send, with what they wrote
    refused.className = "problem-note";  // kept beside it, to send again
    refused.setAttribute("role", "alert");
    form.append(label, send, " ", cancel, refused);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      send.disabled = true;
      refused.textContent = "";
      try {
        const answer = await api("/channels/local/feedback", {
          method: "POST", body: JSON.stringify({ message: message.id, said: why.value.trim() || null, person: state.person }),
        });
        const body = await answer.json().catch(() => ({}));
        if (!answer.ok) {
          refused.textContent = t("That didn't send. Try again.");
          send.disabled = false;
          return;
        }
        const done = document.createElement("p");
        done.className = "note said-wrong";
        done.setAttribute("role", "status");
        done.textContent = body.said;
        done.tabIndex = -1;
        form.replaceWith(done);
        done.focus();  // what a5s kept, where the form was
      } catch (error) {
        if (error.message !== SIGNING_IN) refused.textContent = t("That didn't send. Try again.");
        send.disabled = false;
      }
    });
    ask.replaceWith(form);
    why.focus();
  });
  item.append(ask);
}

function say(message) {
  if (message.id != null) {  // once, whether its conversation or its inbox gave it first
    if (state.shown.has(message.id)) return;
    state.shown.add(message.id);
  }
  $("welcome").hidden = true;
  const item = document.createElement("li");
  // Who it's by, as the server says, never by the name alone, which an agent's could match
  const by = message.by === "person" ? "you" : message.by === "a5s" ? "a5s"
    : message.by === "team" ? "team" : "agent";  // someone of a team, while it's handed over
  item.className = by === "team" ? "agent" : by;
  const who = document.createElement("strong");
  who.textContent = by === "you" ? t("You") : by === "a5s" ? "a5s" : message.from;
  const when = document.createElement("time");
  if (message.at) {
    const at = new Date(message.at);
    when.dateTime = at.toISOString();
    when.textContent = stamp(at);
  }
  const body = document.createElement("div");  // a message that was only a file, in their words
  render(body, by === "you" && message.text === "(a file, with no words)" ? t(message.text) : message.text);
  if (by !== "you") item.append(mark(message.by));
  item.append(who, " ", when, body);
  if (by === "agent" && message.id) wrongOf(item, message);  // an agent's answer, never a5s's
  $("conversation").append(item);
  // to the page's end, so the newest is above the composer, which stays at the foot, never under it
  window.scrollTo({ top: document.documentElement.scrollHeight });
}

// A conversation's first words: the agent, what it does, if it serves them, and what to do
function welcome(agent, does) {
  const name = document.createElement("p");
  name.className = "welcome-name";
  name.textContent = t("The {agent}", { agent });
  const about = document.createElement("p");
  about.textContent = does || "";
  const next = document.createElement("p");
  next.className = "note";
  next.textContent = t("Write to it below.");
  $("welcome").replaceChildren(mark("agent"), name, ...(does ? [about] : []), next);
  $("welcome").hidden = false;
}

// Files to send with the next message: text files, PDFs and images, which the agent asks a5s's
// reader about, as content from outside (core/files.py). A few to a message, a few megabytes in
// all, as the channels take them with it.

const MOST_FILES = 5;
const MOST_BYTES = 4 * 1024 * 1024;
const TAKEN = /\.(txt|csv|md|json|pdf|png|jpe?g|gif|webp)$/i;
const attached = [];

const size = (bytes) => (bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB`
  : `${(bytes / (1024 * 1024)).toFixed(1)} MB`);

function showAttached() {
  const list = $("attached");
  list.replaceChildren(...attached.map((file, i) => {
    const item = document.createElement("li");
    item.className = "chip";
    const name = document.createElement("span");
    name.textContent = `${file.name}, ${size(file.size)}`;
    const leave = document.createElement("button");
    leave.type = "button";
    leave.textContent = "×";
    leave.setAttribute("aria-label", t("Don't send {file}", { file: file.name }));
    leave.addEventListener("click", () => {
      attached.splice(i, 1);
      showAttached();
      $("text").focus();
    });
    item.append(name, leave);
    return item;
  }));
  list.hidden = !attached.length;
}

function attach(files) {
  const refused = [];
  for (const file of files) {
    if (attached.length >= MOST_FILES) {
      refused.push(t("Send at most {n} files with a message.", { n: MOST_FILES }));
      break;
    }
    if (!TAKEN.test(file.name) && !/^image\/(png|jpeg|gif|webp)$/.test(file.type)) {
      refused.push(t("{file}: a5s reads text files, PDFs and images.", { file: file.name }));
      continue;
    }
    if (attached.reduce((all, f) => all + f.size, 0) + file.size > MOST_BYTES) {
      refused.push(t("A message's files can come to {mb} MB in all here.", { mb: MOST_BYTES / (1024 * 1024) }));
      continue;
    }
    attached.push(file);
  }
  refuse(refused.join(" "));
  showAttached();
}

function base64(file) {
  return new Promise((done, failed) => {
    const reader = new FileReader();
    reader.onload = () => done(String(reader.result).split(",", 2)[1] || "");
    reader.onerror = () => failed(reader.error);
    reader.readAsDataURL(file);
  });
}

// Talking to an agent

async function open(agent) {
  state.agent = agent;
  state.shown = new Set();
  $("conversation").replaceChildren();
  $("welcome").hidden = true;
  const answer = await api(`/channels/local/conversation?agent=${encodeURIComponent(agent)}`);
  if (!answer.ok) return;
  const found = await answer.json();
  if (found.messages.length) found.messages.forEach(say);
  else welcome(agent, found.does);
}

async function send(text, files = []) {
  const agent = state.agent;
  const with_ = files.length ? t("Sent {files}", { files: files.map((f) => f.name).join(", ") }) : "";
  say({ from: "you", by: "person", text: [text, with_].filter(Boolean).join("\n"), at: new Date().toISOString() });
  const sending = await Promise.all(files.map(async (f) => ({ name: f.name, type: f.type, data: await base64(f) })));
  const sent = await api("/channels/local/messages", {
    method: "POST", body: JSON.stringify({ agent, text, person: state.person, files: sending }),
  });
  const body = await sent.json();
  if (sent.status !== 202) {
    say({ from: "a5s", by: "a5s", text: typeof body.detail === "string" ? body.detail : t("That didn't send. Try again.") });
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
  status(t("No answer yet. It'll be in your conversation when it comes."));
}

async function listen() {
  // What a5s and the agents write without being asked, such as reminders.
  for (;;) {
    try {
      const answer = await api("/channels/local/inbox?wait=25");
      if (!answer.ok) { await pause(5000); continue; }
      for (const message of (await answer.json()).messages) {
        if ((message.by === "agent" && message.from === state.agent) || message.about === state.agent) say(message);
        else say({ ...message, text: message.about ? t("(about the {agent}) {text}", { agent: message.about, text: message.text })
          : t("(about the agents) {text}", { text: message.text }) });
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
      await window.a5s?.signedIn(JSON.parse(store.getItem("a5s.tokens")).id);  // the sidebar
      $("signout").hidden = false;
      $("signout").addEventListener("click", signOut);
    } else if (state.config.development) {
      state.person = store.getItem("a5s.person") || await askName();
      $("who").textContent = `${state.person}, in development`;
    } else {
      status("The web chat needs sign-in, which isn't set up here yet: see A5S_WEBCHAT_CLIENT_ID.");
      return;
    }
    const serving = await api("/channels/local/agents");
    const listed = await serving.json().catch(() => ({}));
    if (!serving.ok) {  // such as someone the directory doesn't know: why, in the core's words
      status(listed.detail || t("The agents here can't be listed just now: try again in a minute."));
      if (state.config.development && serving.status === 403) {  // and another name to try
        store.removeItem("a5s.person");
        $("rename").hidden = false;
        $("rename").addEventListener("click", () => location.reload());
      }
      return;
    }
    const agents = listed.agents || [];
    if (!agents.length) {  // the studio lists those they may know of, and ask for
      status(listed.at_work === false  // only in development: none is at work here at all
        ? t("No agent is at work here yet: apply the settings first, with `a5s apply`, then reload this page.")
        : t("No agent serves you here yet. The studio's Agents page, at /studio/agents, lists those you may ask for; if it lists none, ask your manager, or whoever runs a5s in your organisation, which agent would serve you."));
      return;
    }
    for (const agent of agents) {
      const option = document.createElement("option");
      option.value = agent;
      option.textContent = agent;
      $("agent").append(option);
    }
    $("agent").addEventListener("change", (event) => open(event.target.value));
    $("compose").hidden = false;
    if (window.a5s) $("attach").append(window.a5s.icon("attach"));
    $("attach").addEventListener("click", () => $("files").click());
    $("files").addEventListener("change", (event) => {
      attach([...event.target.files]);
      event.target.value = "";  // so the same file can be chosen again
    });
    $("text").addEventListener("paste", (event) => {  // a screenshot, pasted
      const data = event.clipboardData;
      if (data && data.files.length && !data.types.includes("text/plain")) {
        event.preventDefault();
        attach([...data.files]);
      }
    });
    $("compose").addEventListener("dragover", (event) => {
      if (event.dataTransfer && event.dataTransfer.types.includes("Files")) event.preventDefault();
    });
    $("compose").addEventListener("drop", (event) => {
      if (event.dataTransfer && event.dataTransfer.files.length) {
        event.preventDefault();
        attach([...event.dataTransfer.files]);
      }
    });
    $("compose").addEventListener("submit", (event) => {
      event.preventDefault();
      const text = $("text").value.trim();
      if (!text && !attached.length) return;
      const files = attached.splice(0);
      showAttached();
      refuse("");
      $("text").value = "";
      send(text, files).catch((error) => { if (error.message !== SIGNING_IN) status(error.message); });
    });
    $("text").addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        $("compose").requestSubmit();
      }
    });
    await open(agents[0]);
    listen();
  } catch (error) {
    if (error.message !== SIGNING_IN) status(error.message);
  }
}

document.addEventListener("DOMContentLoaded", main);
