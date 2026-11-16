// Signing in through the organisation's identity provider, as every page of a5s does: with PKCE,
// the provider's code passed on to it by the core (/studio/sign-in/token), and the sign-in kept in
// memory alone for as long as the studio is open. Where someone was going in the studio comes
// back with them, so a link to a run still opens that run. For an act that counts, such as
// suspending an instance, they sign in afresh for it alone: the sign-in's nonce commits to the
// act, so the identity provider signs it, and the page they come back to carries it out.

import { leavingToSignIn } from "./unkept";

const PENDING = "a5s.studio";
const BACK = `${location.origin}/studio/`;

type SignInConfig = { authorization_endpoint: string; client_id: string; scope: string; acr_values?: string };
/** An act signed in for, and what carrying it out needs, the salt its nonce was made with
 * among it: suspending or resuming an instance, deciding held changes, grading samples, the
 * data protection officer's request, or approving a version of the settings. */
export type Act =
  | { kind: "status"; action: "suspend" | "resume"; instance: string; salt: string }
  | { kind: "decide"; proposals: string[]; decision: "approve" | "reject"; salt: string; reason: string | null }
  | { kind: "grade"; grades: Record<string, string>; salt: string }
  | { kind: "officer"; action: "export" | "erase"; person: string; salt: string }
  | { kind: "approve"; version: string; salt: string };
type Pending = { verifier: string; state: string; nonce: string; path: string; search?: string; act?: Act };

let signedFor: Act | null = null;  // the act the sign-in just made was for, until it's carried out

/** The act the last sign-in was made for, once: the page it came back to carries it out. */
export function takeAct(): Act | null {
  const act = signedFor;
  signedFor = null;
  return act;
}

export class SignInError extends Error {}

function b64url(bytes: ArrayBuffer | Uint8Array): string {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

const random = (): string => b64url(crypto.getRandomValues(new Uint8Array(32)));

async function sha256(text: string): Promise<string> {
  return b64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)));
}

function claims(jwt: string): Record<string, unknown> {
  const part = jwt.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
  return JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(part), (c) => c.charCodeAt(0))));
}

/** The sign-in, once the provider has sent someone back; or null, having sent them to it. */
export async function signIn(): Promise<string | null> {
  if (!window.crypto?.subtle) throw new SignInError("The studio needs HTTPS, or a page on this computer.");
  const params = new URLSearchParams(location.search);
  if (params.has("code") || params.has("error")) return finish(params);
  // the audit trail is read only with a second factor, where the deployment asks for one
  await start(await where(), undefined, undefined, STRONGER.test(location.pathname));
  return null;
}

const STRONGER = /^\/studio\/audit\b/;  // the pages read only at the level what counts asks for

/** Sign in again, as plainly as the first time, coming back to the page they're on: once a
 * sign-in has run out, or one for an act didn't work (round 13, C1, C3). */
export async function signInAgain(): Promise<void> {
  await start(await where());
}

/** Sign in again at the level what counts asks for, such as with a second factor, to read a
 * page that needs one, coming back to it. */
export async function signInStronger(): Promise<void> {
  await start(await where(), undefined, undefined, true);
}

async function where(): Promise<SignInConfig> {
  const config = await fetch("/studio/sign-in/config");
  const body = await config.json().catch(() => ({}));
  if (!config.ok) {
    throw new SignInError(typeof body.detail === "string" ? body.detail : "The studio isn't set up here.");
  }
  return body.signin as SignInConfig;
}

/** A salt for an act's nonce, new each time, so each sign-in for it is different. */
export const salted = random;

/** Text by its hash, as the core's nonces take it: SHA-256, base64url with no padding. */
export const hashed = sha256;

/** Sign in afresh for one act, and nothing else, at the level what counts asks for: `nonce`
 * commits to the act, as the core makes it for that act, so the identity provider signs it. */
export async function signInFor(act: Act, nonce: string): Promise<void> {
  await start(await where(), act, nonce);
}

async function start(signin: SignInConfig, act?: Act, nonce?: string, stronger = false): Promise<void> {
  const pending: Pending = { verifier: random(), state: random(), nonce: nonce ?? random(),
                             path: location.pathname, search: location.search, act };
  sessionStorage.setItem(PENDING, JSON.stringify(pending));
  const url = new URL(signin.authorization_endpoint);
  const query: Record<string, string> = {
    response_type: "code", client_id: signin.client_id, redirect_uri: BACK, scope: signin.scope,
    state: pending.state, nonce: pending.nonce, code_challenge: await sha256(pending.verifier),
    code_challenge_method: "S256",
  };
  if (act) query.max_age = "0";  // afresh, not a sign-in the browser kept
  if ((act || stronger) && signin.acr_values) query.acr_values = signin.acr_values;  // the level what counts needs
  for (const [key, value] of Object.entries(query)) url.searchParams.set(key, value);
  leavingToSignIn();  // what isn't kept yet stays in the tab, and comes back with them
  location.assign(url.toString());
}

async function finish(params: URLSearchParams): Promise<string> {
  const pending = JSON.parse(sessionStorage.getItem(PENDING) || "null") as Pending | null;
  sessionStorage.removeItem(PENDING);
  // the code doesn't linger in the address, and they're back where they were going
  const where = pending?.path && /^\/studio\/[\w./-]*$/.test(pending.path) ? pending.path : "/studio/";
  // and what it asked for, such as an agent to put to work: in plain words and commas alone
  const asked = pending?.search && /^\?[\w=&,.:@%+-]*$/.test(pending.search) ? pending.search : "";
  history.replaceState(null, "", where + asked);
  const again = "Signing in didn't come back the way it went out. Open the studio again.";
  if (!pending || params.get("state") !== pending.state) throw new SignInError(again);
  // The provider's words only for a sign-in this tab sent, so a link can't put its own on
  // the page as if they were (round 11, E-3)
  if (params.has("error")) {
    throw new SignInError(`Signing in didn't work: ${params.get("error_description") || params.get("error")}`);
  }
  const answer = await fetch("/studio/sign-in/token", {  // the core passes it on to the provider
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ grant_type: "authorization_code", code: params.get("code"),
                           code_verifier: pending.verifier, redirect_uri: BACK }),
  });
  const tokens = await answer.json().catch(() => ({}));
  if (!answer.ok || !tokens.id_token) {
    throw new SignInError(`Signing in didn't work: ${tokens.error_description || tokens.error || tokens.detail || answer.status}`);
  }
  if (claims(tokens.id_token).nonce !== pending.nonce) throw new SignInError(again);
  signedFor = pending.act ?? null;
  return tokens.id_token as string;
}
