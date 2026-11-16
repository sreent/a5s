// What someone has changed that a5s hasn't kept yet, such as a draft's files, the settings'
// forms or the grades they've chosen, kept in this tab alone until a5s has it: so signing in
// again, when a sign-in runs out, or a reload, gives it back (round 13, C1). Never a sign-in,
// only what they typed or chose; and the tab forgets it once it's closed.

const PREFIX = "a5s.unkept.";
let leaving = false;  // on the way to the identity provider, which brings them back

export function keepUnkept(key: string, value: unknown): void {
  try {
    sessionStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // the tab won't keep it, so it's in memory alone, as it was
  }
}

export function unkept<T>(key: string): T | null {
  try {
    const found = sessionStorage.getItem(PREFIX + key);
    return found ? (JSON.parse(found) as T) : null;
  } catch {
    return null;
  }
}

/** a5s has it now: the tab needn't keep it any more. */
export function keptNow(key: string): void {
  try {
    sessionStorage.removeItem(PREFIX + key);
  } catch {
    // nothing kept to forget
  }
}

function anyUnkept(): boolean {
  try {
    return Object.keys(sessionStorage).some((key) => key.startsWith(PREFIX));
  } catch {
    return false;
  }
}

/** Leaving for the identity provider, which brings them back to it: nothing to warn of. */
export function leavingToSignIn(): void {
  leaving = true;
}

// Before the tab closes on something not yet kept, the browser asks first, as it does, since
// a closed tab forgets it
window.addEventListener("beforeunload", (event) => {
  if (!leaving && anyUnkept()) event.preventDefault();
});
