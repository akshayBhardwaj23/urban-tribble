/** User-facing copy when the app cannot reach the API (no dev URLs in production). */

const IS_DEV = process.env.NODE_ENV === "development";

export const API_UNAVAILABLE_TITLE = IS_DEV
  ? "Can't reach the API"
  : "Service temporarily unavailable";

export const API_UNAVAILABLE_DESCRIPTION = IS_DEV
  ? "The app could not load your account. Start the backend (usually port 8000), confirm NEXT_PUBLIC_API_URL in frontend/.env.local matches that server, then retry."
  : "We couldn't load your account right now. Please wait a moment and try again.";

export const API_RETRY_HINT = IS_DEV
  ? "Check that the API is running and you are still signed in. If you switched workspaces, try once more."
  : "If this keeps happening, sign out and sign back in, or try again in a few minutes.";

const NETWORK_ERROR_RE =
  /failed to fetch|networkerror|network request failed|load failed|econnrefused|err_connection/i;

const DEV_LEAK_RE =
  /localhost|127\.0\.0\.1|0\.0\.0\.0|next_public|\.env\.local|port \d{4}|start the api/i;

function isLikelyNetworkError(error: unknown): boolean {
  if (error instanceof Error && error.name === "AbortError") return true;
  if (error instanceof TypeError) return true;
  const msg =
    error instanceof Error ? error.message : String(error ?? "");
  return NETWORK_ERROR_RE.test(msg);
}

/** Strip or replace messages that expose dev setup (production only). */
export function sanitizeApiErrorMessage(message: string): string {
  if (IS_DEV) return message;
  if (!message.trim()) {
    return "Something went wrong. Please try again.";
  }
  if (NETWORK_ERROR_RE.test(message) || DEV_LEAK_RE.test(message)) {
    return "We couldn't reach the server. Please check your connection and try again.";
  }
  return message;
}

/** Format any thrown API/client error for display in the UI. */
export function formatUserFacingApiError(error: unknown): string {
  if (isLikelyNetworkError(error)) {
    return IS_DEV
      ? "Can't reach the API. Start the backend and confirm NEXT_PUBLIC_API_URL matches."
      : "We couldn't reach the server. Please check your connection and try again.";
  }
  if (error instanceof Error) {
    return sanitizeApiErrorMessage(error.message);
  }
  return IS_DEV ? "Request failed" : "Something went wrong. Please try again.";
}
