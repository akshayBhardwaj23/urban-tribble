/**
 * Which integrations are offered to users, and how they are described.
 *
 * Availability is not decided here. The backend catalog is the single source of
 * truth: each provider reports its connection modes and whether each one is
 * `available`, and this module only interprets that. A provider that is
 * disabled server-side therefore cannot be connected by editing the client, and
 * the two can never disagree about what is live.
 *
 * `WAVE_ONE` is presentation only. It marks the providers we actively invite
 * people to connect so the rest of the catalog can stay visible as a roadmap
 * without implying it is ready.
 */

import type { IntegrationConnectionMode, IntegrationProvider } from "@/lib/api";

/** Providers we actively promote today. Everything else reads as roadmap. */
export const WAVE_ONE = new Set(["excel_onedrive", "google_sheets"]);

export function isModeAvailable(mode: IntegrationConnectionMode): boolean {
  // The backend omits `available` when it means true.
  return mode.available !== false;
}

export function availableModes(
  provider: IntegrationProvider,
): IntegrationConnectionMode[] {
  return provider.connection_modes.filter(isModeAvailable);
}

export function isProviderConnectable(provider: IntegrationProvider): boolean {
  return availableModes(provider).length > 0;
}

/** The mode to select by default: recommended first, else the first available. */
export function preferredMode(
  provider: IntegrationProvider,
): IntegrationConnectionMode | undefined {
  const modes = availableModes(provider);
  return modes.find((m) => m.recommended) ?? modes[0];
}

/** OAuth providers hand off to the provider's own sign-in rather than a form. */
export function isOauthMode(mode: IntegrationConnectionMode | undefined): boolean {
  return mode?.id === "oauth";
}

/**
 * Google returns several files from one sign-in and its completion endpoint
 * takes a list, so its picker is multi-select. Microsoft's takes a single id.
 */
export function supportsMultiFileConnect(providerId: string): boolean {
  return providerId === "google_sheets";
}

export function isWaveOne(providerId: string): boolean {
  return WAVE_ONE.has(providerId);
}
