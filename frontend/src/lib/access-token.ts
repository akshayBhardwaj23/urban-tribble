/** Expiry helpers for the FastAPI access token.
 *
 * The token is an unsigned-to-us HS256 JWT: we read `exp` only to decide when
 * to re-mint it and which of two tokens is newer. The backend stays the sole
 * authority on whether a token is actually valid.
 */

function decodeBase64Url(segment: string): string | null {
  const padded = segment.replace(/-/g, "+").replace(/_/g, "/");
  const pad = padded.length % 4 === 0 ? "" : "=".repeat(4 - (padded.length % 4));
  try {
    return atob(padded + pad);
  } catch {
    return null;
  }
}

/** Epoch milliseconds at which `token` expires, or null if it cannot be read. */
export function accessTokenExpiresAt(
  token: string | null | undefined
): number | null {
  if (!token) return null;
  const parts = token.split(".");
  if (parts.length !== 3) return null;

  const json = decodeBase64Url(parts[1]);
  if (!json) return null;

  try {
    const payload = JSON.parse(json) as { exp?: unknown };
    return typeof payload.exp === "number" ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}
