"use strict";
// The settings app, for the people who approve instances: each part's owner, and the
// instance approvers. They sign in with their organisation's identity provider, see the whole
// version in force in words, and the versions waiting for approval, and can ask for a change.
// Asking changes nothing: a5s proposes the new version to everyone who must approve it, and
// they approve it on its own page, signing in afresh. The page shows only text, and keeps the
// sign-in in memory alone.
//
// A change is written in forms, for what people change most: an instance's level, the types of
// change it makes on its own at level 2, whom it serves and who runs it, each type of change's
// limits, and the accuracy each part needs for level 2. Or in the whole text, for anything else.
// The forms send the version as JSON, which a5s reads as the YAML it is, and the review says in
// words what it would change, either way.

const $ = (id) => document.getElementById(id);
const store = window.sessionStorage;
const PENDING = "a5s.settings";
const BACK = `${location.origin}/settings/`;
let token = null;
let inForce = null;  // the version in force, as it was
let working = null;  // and as the forms change it
let names = {};  // the people the settings name, by their names
let actions = [];  // the types of change this deployment's tools make
let releases = {};  // the levels each release starts at and allows
let mode = "forms";
let reviewed = null;  // the version as written that was reviewed, which is what Send asks for
let me = null;  // whoever signed in, by their id
let adding = null;  // a new instance, as its form has it so far
const ADDING = "a5s.settings.add";  // an agent to put to work, chosen before signing in

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
  history.replaceState(null, "", "/settings/");
  const pending = JSON.parse(store.getItem(PENDING) || "null");
  store.removeItem(PENDING);
  if (params.has("error")) {
    throw new Error(`Signing in didn't work: ${params.get("error_description") || params.get("error")}`);
  }
  const again = "Signing in didn't come back the way it went out. Open the settings again.";
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

async function call(path, body) {
  const answer = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const found = await answer.json();
  if (!answer.ok) {
    const detail = found.detail;
    if (detail && Array.isArray(detail.problems)) throw new Error(detail.problems.join(" "));
    throw new Error(typeof detail === "string" ? detail : `a5s said ${answer.status}.`);
  }
  return found;
}

// A change in the words code worked out, marked where it widens what agents do, as the page
// that approves it marks it
function changed(change) {
  const line = document.createElement("li");
  line.textContent = typeof change === "string" ? change : change.text;
  if (change.widens) {
    const badge = document.createElement("span");
    badge.className = "badge changes";
    badge.textContent = "widens what agents do";
    line.append(" ", badge);
  }
  return line;
}

function list(id, items, mark) {
  const into = $(id);
  into.replaceChildren();
  for (const item of items) {
    const line = changed(item);
    if (mark) line.classList.add(mark);
    into.append(line);
  }
}

function showWaiting(waiting) {
  const into = $("waiting");
  into.replaceChildren();
  for (const version of waiting) {
    const title = document.createElement("p");
    const link = document.createElement("a");
    link.href = version.link;
    link.textContent = `Version ${version.serial}`;
    title.append(link, version.approved_by.length
      ? `, approved so far by ${version.approved_by.join(", ")}.` : ", which nobody has approved yet.");
    const changes = document.createElement("ul");
    changes.className = "plain";
    into.append(title, changes);
    changes.append(...version.changes.map(changed));
    if (version.needs.length) {
      const needs = document.createElement("p");
      needs.className = "note";
      needs.textContent = `It still waits because ${version.needs.join("; ")}.`;
      into.append(needs);
    }
  }
  $("waiting-section").hidden = waiting.length === 0;
}

function showRequests(requests) {
  list("requests", requests.map((r) => {
    const when = new Date(r.asked_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
    return `Version ${r.serial}, asked for ${when}: ${r.outcome}.`;
  }));
  $("requests-section").hidden = requests.length === 0;
}

function element(tag, text, className) {
  const found = document.createElement(tag);
  if (text !== undefined && text !== null) found.textContent = String(text);
  if (className) found.className = className;
  return found;
}

// A box or button beside its words, which wrap beside it
function choice(type, group, checked, label, changed) {
  const box = element("label", null, "choice");
  const input = element("input");
  input.type = type;
  input.name = group;
  input.checked = checked;
  input.addEventListener("change", () => changed(input));
  box.append(input, element("span", label));
  return box;
}

// A choice that can't be made, and why
function because(box, why) {
  box.querySelector("input").disabled = true;
  box.querySelector("span").append(element("span", `: ${why}`, "faint"));
}

// A value, with its words before it, and any after it
function setting(words, control, after) {
  const box = element("label", null, "setting");
  box.append(element("span", words), control);
  if (after) box.append(element("span", after));
  return box;
}

const LEVELS = { 0: "level 0, suggests: it reads and drafts, and people do the rest",
                 1: "level 1, asks: its changes wait for a person's yes" };

// Someone an instance serves, by name, or a group, as the directory decides who is in it
function whom(who) {
  if (who.startsWith("team:")) return `everyone in the ${who.slice(5)} team`;
  if (who.startsWith("role:")) return `everyone who holds the ${who.slice(5)} role`;
  return names[who] || who;
}

const partsOf = (instance) => {
  const parts = instance?.parts || [];
  return Array.isArray(parts) ? parts : Object.keys(parts);
};

function entryOf(instance, part) {  // a part's entry: null, a level, or {level, actions}
  const parts = instance?.parts;
  return parts && !Array.isArray(parts) ? (parts[part] ?? null) : null;
}

function partLevel(instance, part) {
  const entry = entryOf(instance, part);
  if (typeof entry === "number") return entry;
  return entry && typeof entry.level === "number" ? entry.level : null;
}

function actionLevel(instance, part, action) {
  const entry = entryOf(instance, part);
  const level = entry && typeof entry === "object" && entry.actions ? entry.actions[action] : undefined;
  return typeof level === "number" ? level : undefined;
}

function changePart(instance, part, change) {
  // A part's own levels need the parts as a mapping, which keeps each part's as it was
  if (!instance.parts || Array.isArray(instance.parts)) {
    instance.parts = Object.fromEntries((instance.parts || []).map((each) => [each, null]));
  }
  const was = instance.parts[part];
  const entry = was && typeof was === "object" ? { ...was, actions: { ...(was.actions || {}) } }
    : { ...(typeof was === "number" ? { level: was } : {}), actions: {} };
  change(entry);
  if (!Object.keys(entry.actions).length) delete entry.actions;
  instance.parts[part] = Object.keys(entry).length ? entry : null;
}

function setPartLevel(instance, part, level) {
  changePart(instance, part, (entry) => {
    if (level === null) delete entry.level;
    else entry.level = level;
  });
}

function setActionLevel(instance, part, action, level) {
  changePart(instance, part, (entry) => {
    if (level === undefined) delete entry.actions[action];
    else entry.actions[action] = level;
  });
}

function levelsOf(id, instance) {
  const release = releases[instance.definition];
  const fragment = [element("p", "It works at", "lead")];
  const levels = element("div", null, "choices");
  const options = [[0, LEVELS[0]], [1, LEVELS[1]], [null, release
    ? `whatever level its release starts at, now level ${release.starts}` : "whatever level its release starts at"]];
  if (instance.level === 2) {
    options.push([2, "level 2, as written: a5s holds it at level 1 in a part, and gives level 2 only to a type of change, below"]);
  }
  for (const [n, about] of options) {
    const box = choice("radio", `level-${id}`, (instance.level ?? null) === n, about, () => {
      if (n === null) delete instance.level;
      else instance.level = n;
    });
    if (release && n !== null && n > release.most && instance.level !== n) {
      because(box, `its release allows level ${release.most} at most`);
    }
    levels.append(box);
  }
  fragment.push(levels);
  // A part with a level of its own, which the level above doesn't change
  const was = inForce?.instances?.[id];
  for (const part of partsOf(instance)) {
    const own = partLevel(instance, part);
    if (own === null && partLevel(was, part) === null) continue;
    const pick = element("select");
    pick.setAttribute("aria-label", `${id}'s level in ${part}`);
    pick.append(new Option("the level above", ""));
    for (const n of own === 2 ? [0, 1, 2] : [0, 1]) pick.append(new Option(LEVELS[n] || `level ${n}`, String(n)));
    pick.value = own === null ? "" : String(own);
    pick.addEventListener("change", () => setPartLevel(instance, part, pick.value === "" ? null : Number(pick.value)));
    fragment.push(setting(`In ${part}, it works at`, pick));
  }
  return fragment;
}

function ownChanges(id, instance) {
  const release = releases[instance.definition];
  const kinds = release ? release.actions : actions;  // the types of change its tools make
  const parts = partsOf(instance);
  if (!kinds.length || !parts.length) return [];
  const allowed = !release || release.most >= 2;
  const own = element("div", null, "choices");
  for (const part of parts) {
    const earns = working.thresholds?.[part] !== undefined;
    for (const action of kinds) {
      const box = choice("checkbox", `own-${id}`, actionLevel(instance, part, action) === 2,
                         `${action} in ${part}`, (input) => {
        // Unticked, it goes back to the level the version in force sets it, if not 2
        const was = actionLevel(inForce?.instances?.[id], part, action);
        setActionLevel(instance, part, action, input.checked ? 2 : (was === 2 ? undefined : was));
      });
      const why = !allowed ? `its release, ${instance.definition}, allows level ${release.most} at most`
        : !earns ? `${part} needs no accuracy below, so it never earns level 2` : null;
      if (why && actionLevel(instance, part, action) !== 2) because(box, why);
      own.append(box);
    }
  }
  return [element("p", "It makes these changes on its own, at level 2", "lead"), own,
          element("p", "Each within its limits, below. a5s holds it at level 1 until graded samples of its work show the accuracy its part needs.", "note")];
}

function servesOf(id, instance) {
  const serves = element("div", null, "choices");
  const everyone = [...new Set([...(instance.serves || []), ...Object.keys(names)])];
  for (const who of everyone) {
    serves.append(choice("checkbox", `serves-${id}`, (instance.serves || []).includes(who), whom(who), (input) => {
      const now = new Set(instance.serves || []);
      if (input.checked) now.add(who);
      else now.delete(who);
      instance.serves = everyone.filter((each) => now.has(each));
    }));
  }
  const adding = element("div", null, "add-someone");
  const someone = element("input");
  someone.type = "text";
  someone.dataset.adds = id;
  someone.placeholder = "an id, team:… or role:…";
  someone.setAttribute("aria-label", `Someone else ${id} serves`);
  const add = element("button", "Add");
  add.type = "button";
  const adds = () => {
    const who = someone.value.trim();
    if (!who) return;
    instance.serves = [...new Set([...(instance.serves || []), who])];
    names = { [who]: who, ...names };  // the review says who they are, if the directory knows them
    stale();
    render();
    $("forms").querySelector(`input[data-adds="${CSS.escape(id)}"]`)?.focus();
  };
  add.addEventListener("click", adds);
  someone.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      adds();
    }
  });
  adding.append(someone, add);
  return [element("p", "It serves", "lead"), serves, adding];
}

function runsOf(id, instance) {
  const runs = element("div", null, "choices");
  for (const [role, label] of [["owner", "Owner"], ["deputy", "Deputy"]]) {
    const pick = element("select");
    pick.setAttribute("aria-label", `${label} of ${id}`);
    pick.append(new Option("nobody", ""));
    for (const who of Object.keys(names).filter((each) => !each.includes(":"))) {
      pick.append(new Option(names[who], who));
    }
    pick.value = instance[role] || "";
    pick.addEventListener("change", () => {
      if (pick.value) instance[role] = pick.value;
      else delete instance[role];
    });
    runs.append(setting(label, pick));
  }
  return [element("p", "Who runs it here", "lead"), runs];
}

function instanceForm(id, instance) {
  const set = element("fieldset", null, "form-card");
  set.dataset.instance = id;
  set.tabIndex = -1;  // where focus goes once it's added
  set.append(element("legend", `${id}, the ${instance.definition}`), ...levelsOf(id, instance),
             ...ownChanges(id, instance), ...servesOf(id, instance), ...runsOf(id, instance));
  return set;
}

// Putting an agent to work: a new instance of it, for a few people first, at level 0 or 1

const ID = /^[a-z0-9][a-z0-9-]{0,62}$/;

function suggested() {
  // A name for the new instance, the agent's and then its part's, unused
  const base = `${adding.agent}-${adding.part || "new"}`.slice(0, 60);
  let id = base;
  for (let n = 2; working.instances?.[id]; n += 1) id = `${base}-${n}`;
  return id;
}

function freshAdding(agent, before = null) {
  // What its form starts with: it starts as low as its release does, at level 1 at most,
  // serving whoever's adding it, run by them; or, for another agent, what they'd chosen
  return { agent, id: null, part: before?.part ?? "", level: Math.min(releases[agent]?.starts ?? 1, 1),
           serves: before?.serves ?? new Set(me ? [me] : []), owner: before?.owner ?? (me || ""),
           deputy: before?.deputy ?? "" };
}

function addForm(parts) {
  const agents = Object.keys(releases);
  if (!agents.length) return null;
  adding ||= freshAdding(agents[0]);
  const release = releases[adding.agent];
  const set = element("fieldset", null, "form-card adding");
  set.id = "add-instance";
  set.append(element("legend", "Put an agent to work"),
             element("p", "A new instance of an agent, for a few people first, at level 0 or 1, so it suggests, or asks before each change. Its part's owner approves it, as any change there; with no part, someone who approves instances does.", "note"));

  const which = element("div", null, "choices");
  const agent = element("select");
  agent.id = "add-agent";
  for (const name of agents) agent.append(new Option(name, name));
  agent.value = adding.agent;
  agent.addEventListener("change", () => {
    adding = freshAdding(agent.value, adding);
    render();
    $("add-agent").focus();
  });
  const part = element("select");
  part.id = "add-part";
  part.append(new Option("no part's records", ""));
  for (const each of parts) part.append(new Option(each, each));
  part.value = adding.part;
  const name = element("input");
  name.type = "text";
  name.id = "add-id";
  name.value = adding.id ?? suggested();
  name.addEventListener("input", () => { adding.id = name.value; });
  part.addEventListener("change", () => {
    adding.part = part.value;
    if (adding.id === null) name.value = suggested();  // what it's called follows, unless they named it
  });
  which.append(setting("Agent", agent), setting("Works in", part), setting("Its name here", name));
  set.append(which);

  set.append(element("p", "It starts at", "lead"));
  const levels = element("div", null, "choices");
  for (const n of [0, 1]) {
    const box = choice("radio", "add-level", adding.level === n, LEVELS[n], () => { adding.level = n; });
    if (release && n > release.most) because(box, `its release allows level ${release.most} at most`);
    levels.append(box);
  }
  set.append(levels);

  set.append(element("p", "It serves", "lead"));
  const serves = element("div", null, "choices");
  for (const who of Object.keys(names)) {
    serves.append(choice("checkbox", "add-serves", adding.serves.has(who), whom(who), (input) => {
      if (input.checked) adding.serves.add(who);
      else adding.serves.delete(who);
    }));
  }
  set.append(serves);

  set.append(element("p", "Who runs it here", "lead"));
  const runs = element("div", null, "choices");
  for (const [role, label] of [["owner", "Owner"], ["deputy", "Deputy"]]) {
    const pick = element("select");
    pick.setAttribute("aria-label", `${label} of the new instance`);
    pick.append(new Option("nobody", ""));
    for (const who of Object.keys(names).filter((each) => !each.includes(":"))) pick.append(new Option(names[who], who));
    pick.value = adding[role];
    pick.addEventListener("change", () => { adding[role] = pick.value; });
    runs.append(setting(label, pick));
  }
  set.append(runs);

  const problem = element("p", null, "problem-note");
  problem.setAttribute("role", "alert");
  const add = element("button", "Add it to the settings");
  add.type = "button";
  add.id = "add-it";
  add.addEventListener("click", () => {
    const id = (adding.id ?? suggested()).trim();
    const wrong = !ID.test(id) ? "Its name is lowercase letters, digits and hyphens, starting with a letter or a digit."
      : working.instances?.[id] ? `There's an instance called ${id} already: give it another name.`
      : !adding.serves.size ? "Choose whom it serves: a few people first."
      : null;
    if (wrong) {
      problem.textContent = wrong;
      return;
    }
    working.instances ||= {};
    working.instances[id] = { definition: adding.agent, serves: [...adding.serves], level: adding.level,
                              ...(adding.owner ? { owner: adding.owner } : {}),
                              ...(adding.deputy ? { deputy: adding.deputy } : {}),
                              parts: adding.part ? [adding.part] : [] };
    adding = null;
    stale();
    render();
    const made = $("forms").querySelector(`fieldset[data-instance="${CSS.escape(id)}"]`);
    made?.scrollIntoView({ block: "start" });
    made?.focus();
    status(`${id} is in the forms: review it, with any other change, and ask its approvers.`);
  });
  const doing = element("div", null, "add-someone");
  doing.append(add);
  set.append(doing, problem);
  return set;
}

// An agent someone chose to put to work, on its page in the studio, kept through signing in
function offerAdding() {
  const agent = store.getItem(ADDING);
  store.removeItem(ADDING);
  if (!agent || !releases[agent] || !working) return;
  adding = freshAdding(agent);
  render();
  $("add-instance").scrollIntoView({ block: "start" });
  $("add-agent").focus();
}

function limitsForm() {
  const set = element("fieldset", null, "form-card");
  set.append(element("legend", "Each type of change's limits"),
             element("p", "How many one run may make, and how many for each person in 30 days. Past either, a change waits for a person to decide it, whatever the level. Empty means no limit.", "note"));
  for (const action of [...new Set([...actions, ...Object.keys(working.limits || {})])]) {
    const row = element("div", null, "limit");
    row.append(element("p", action, "limit-name"));
    for (const [field, words] of [["per_run", "In one run"], ["per_person_30_days", "For each person, in 30 days"]]) {
      const input = element("input");
      input.type = "number";
      input.min = "1";
      input.max = "100000";
      input.value = working.limits?.[action]?.[field] ?? "";
      input.setAttribute("aria-label", `${action}, ${words.toLowerCase()}`);
      input.addEventListener("input", () => {
        const limits = (working.limits ||= {});
        const limit = (limits[action] ||= {});
        const n = Number(input.value);
        if (input.value !== "" && Number.isInteger(n)) limit[field] = n;
        else delete limit[field];
        if (!Object.keys(limit).length) delete limits[action];
      });
      row.append(setting(words, input));
    }
    set.append(row);
  }
  return set;
}

function thresholdsForm(parts) {
  const set = element("fieldset", null, "form-card");
  set.append(element("legend", "The accuracy level 2 needs"),
             element("p", "How accurate an agent's changes in a part must be, as graded samples show, before a5s raises its cap there to level 2. Empty means it never does.", "note"));
  const choices = element("div", null, "choices");
  for (const part of parts) {
    const share = working.thresholds?.[part];
    const input = element("input");
    input.type = "number";
    input.min = "50";
    input.max = "99.9";
    input.step = "0.1";
    input.value = share === undefined ? "" : String(Math.round(share * 1000) / 10);
    input.setAttribute("aria-label", `The accuracy ${part} needs, in percent`);
    input.addEventListener("input", () => {
      const thresholds = (working.thresholds ||= {});
      const n = Number(input.value);
      if (input.value !== "" && Number.isFinite(n)) thresholds[part] = Math.round(n * 10) / 1000;
      else delete thresholds[part];
    });
    choices.append(setting(part, input, "%"));
  }
  set.append(choices);
  return set;
}

function render() {
  if (!working) return;
  const parts = [...new Set([...Object.keys(working.thresholds || {}),
                             ...Object.values(working.instances || {}).flatMap(partsOf)])];
  const add = addForm([...new Set([...parts].sort())]);
  $("forms").replaceChildren(
    ...Object.entries(working.instances || {}).map(([id, instance]) => instanceForm(id, instance)),
    ...(add ? [add] : []),
    ...(actions.length || Object.keys(working.limits || {}).length ? [limitsForm()] : []),
    ...(parts.length ? [thresholdsForm(parts)] : []));
}

function useMode(chosen) {
  mode = chosen;
  $("by-forms").setAttribute("aria-pressed", String(chosen === "forms"));
  $("by-text").setAttribute("aria-pressed", String(chosen === "text"));
  $("forms").hidden = chosen !== "forms";
  $("as-text").hidden = chosen !== "text";
  $("reviewed").hidden = true;
}

// The version as written: the forms' as JSON, which a5s reads as YAML, or the text
const draft = () => (mode === "text" ? $("text").value : JSON.stringify(working));

async function load() {
  const now = await call("/settings/api");
  $("who").textContent = now.you;
  if (now.in_force) {
    $("in-force-title").textContent = `In force: version ${now.in_force.serial}`;
    list("whole", now.in_force.whole);
    $("in-force").hidden = false;
    if (!$("text").value) $("text").value = now.in_force.text;
    inForce = now.in_force.data;
    if (!working) working = structuredClone(inForce);
    names = { ...names, ...now.names };
    actions = now.actions;
    releases = now.releases;
    me = now.me;
    render();
  } else {
    status("No settings are in force yet.");
    $("modes").hidden = true;  // the forms change a version in force: with none, there's the text
    useMode("text");
  }
  showWaiting(now.waiting);
  showRequests(now.requests);
  $("edit").hidden = false;
}

// A change after a review needs a review of its own before anyone asks for it
const stale = () => { $("reviewed").hidden = true; };

async function review() {
  stale();
  const text = draft();
  const found = await call("/settings/api/review", { text });
  list("problems", found.problems || [], "problem");
  if (found.serial === undefined) {
    $("reviewed-summary").textContent = "a5s can't propose this:";
    $("reviewed").hidden = false;
    $("send").hidden = true;
    return;
  }
  $("reviewed-summary").textContent = found.problems.length
    ? `As version ${found.serial}, a5s can't propose this:` : `As version ${found.serial}, it:`;
  list("reviewed-changes", found.changes);
  $("reviewed-approvers").textContent = found.approvers.length
    ? `It needs the approval of ${found.approvers.join(", ")}.` : "Nobody in the directory can approve it.";
  list("reviewed-whole", found.whole);
  $("send").hidden = found.problems.length > 0;
  reviewed = text;
  $("reviewed").hidden = false;
}

async function send() {
  $("send").disabled = true;
  try {
    const asked = await call("/settings/api/requests", { text: reviewed });
    $("reviewed").hidden = true;
    working = null;  // the forms start again from what's in force
    status(`You asked for version ${asked.serial}. a5s asks its approvers within a minute, and puts it in force once they've all approved it.`);
    await load();
  } finally {
    $("send").disabled = false;
  }
}

async function main() {
  try {
    if (!window.crypto || !crypto.subtle) {
      status("The settings app needs HTTPS, or a page on this computer.");
      return;
    }
    const params = new URLSearchParams(location.search);
    const put = params.get("add");  // an agent to put to work, from its page in the studio
    if (put && ID.test(put)) store.setItem(ADDING, put);
    if (params.has("code") || params.has("error")) {
      token = await signedIn(params);
      window.a5s?.signedIn(token);  // the sidebar, of the pages they may use
      await load();
      offerAdding();
      $("review").addEventListener("click", () => review().catch((e) => status(e.message)));
      $("by-forms").addEventListener("click", () => useMode("forms"));
      $("by-text").addEventListener("click", () => useMode("text"));
      for (const event of ["input", "change"]) {
        $("forms").addEventListener(event, stale);
        $("text").addEventListener(event, stale);
      }
      $("send").addEventListener("click", () => send().catch((e) => status(e.message)));
      return;
    }
    const config = await fetch("/approve/config");
    const body = await config.json();
    if (!config.ok) {
      status(typeof body.detail === "string" ? body.detail : "The settings app isn't set up here.");
      return;
    }
    status("Signing you in…");
    await signIn(body.signin);
  } catch (error) {
    status(error.message);
  }
}

document.addEventListener("DOMContentLoaded", main);
