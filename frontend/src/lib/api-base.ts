/** Shared API origin resolution for browser and NextAuth server code. */

export function resolveApiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (configured) return configured.replace(/\/$/, "");
  if (process.env.NODE_ENV === "production") {
    throw new Error(
      "NEXT_PUBLIC_API_URL is not set. Set it to your API origin before building for production."
    );
  }
  return "http://localhost:8000";
}
