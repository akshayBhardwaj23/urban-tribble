/**
 * Single source of truth for product branding.
 * Change PRODUCT_NAME / PRODUCT_DOMAIN here to rebrand the whole app from one place.
 */
export const PRODUCT_NAME = "Snaptix";

/** Public site hostname (no protocol) */
export const PRODUCT_DOMAIN = "snaptix.ai" as const;

export const CANONICAL_SITE_URL = `https://${PRODUCT_DOMAIN}` as const;

/** Primary positioning — browser, login, hero eyebrow */
export const POSITIONING_LINE =
  "AI analyst for revenue, cost, and the tradeoffs between them";

/** Short promise — footer, meta support, hero */
export const PRODUCT_TAGLINE =
  "Turn spreadsheet noise into a briefing you can act on.";

/** Browser tab + Open Graph description */
export const META_DESCRIPTION = `${PRODUCT_NAME} helps operators read revenue, cost, and ops data: upload spreadsheets, get a calm briefing on what moved and what to verify, then decide with clearer tradeoffs.`;

/** Login screen subtitle (same intent as POSITIONING_LINE; split if you want login-only copy) */
export const LOGIN_HEADLINE = POSITIONING_LINE;
