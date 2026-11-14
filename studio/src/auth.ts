// Signing in through the organisation's identity provider, as every page of a5s does: with PKCE,
// the provider's code passed on to it by the core (/approve/token), and the sign-in kept in
// memory alone for as long as the studio is open. Where someone was going in the studio comes
// back with them, so a link to a run still opens that run.

const PENDING = "a5s.studio";
const BACK = `${location.origin}/studio/`;

type SignInConfig = { authorization_endpoint: string; client_id: string; scope: string };
type Pending = { verifier: string; state: string; nonce: string; path: string };

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
  const config = await fetch("/approve/config");
  const body = await config.json().catch(() => ({}));
  if (!config.ok) {
    throw new SignInError(typeof body.detail === "string" ? body.detail : "The studio isn't set up here.");
  }
  await start(body.signin as SignInConfig);
  return null;
}

async function start(signin: SignInConfig): Promise<void> {
  const pending: Pending = { verifier: random(), state: random(), nonce: random(),
                             path: location.pathname };
  sessionStorage.setItem(PENDING, JSON.stringify(pending));
  const url = new URL(signin.authorization_endpoint);
  const query: Record<string, string> = {
    response_type: "code", client_id: signin.client_id, redirect_uri: BACK, scope: signin.scope,
    state: pending.state, nonce: pending.nonce, code_challenge: await sha256(pending.verifier),
    code_challenge_method: "S256",
  };
  for (const [key, value] of Object.entries(query)) url.searchParams.set(key, value);
  location.assign(url.toString());
}

async function finish(params: URLSearchParams): Promise<string> {
  const pending = JSON.parse(sessionStorage.getItem(PENDING) || "null") as Pending | null;
  sessionStorage.removeItem(PENDING);
  // the code doesn't linger in the address, and they're back where they were going
  const where = pending?.path && /^\/studio\/[\w./-]*$/.test(pending.path) ? pending.path : "/studio/";
  history.replaceState(null, "", where);
  if (params.has("error")) {
    throw new SignInError(`Signing in didn't work: ${params.get("error_description") || params.get("error")}`);
  }
  const again = "Signing in didn't come back the way it went out. Open the studio again.";
  if (!pending || params.get("state") !== pending.state) throw new SignInError(again);
  const answer = await fetch("/approve/token", {  // the core passes it on to the provider
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ grant_type: "authorization_code", code: params.get("code"),
                           code_verifier: pending.verifier, redirect_uri: BACK }),
  });
  const tokens = await answer.json().catch(() => ({}));
  if (!answer.ok || !tokens.id_token) {
    throw new SignInError(`Signing in didn't work: ${tokens.error_description || tokens.error || tokens.detail || answer.status}`);
  }
  if (claims(tokens.id_token).nonce !== pending.nonce) throw new SignInError(again);
  return tokens.id_token as string;
}
