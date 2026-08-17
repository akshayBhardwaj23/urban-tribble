/**
 * Single source of truth for product branding.
 * Change PRODUCT_NAME / PRODUCT_DOMAIN here to rebrand the whole app from one place.
 */
export const PRODUCT_NAME = "Snaptix";

/** Public site hostname (no protocol) */
export const PRODUCT_DOMAIN = "snaptix.ai" as const;

export const CANONICAL_SITE_URL = `https://${PRODUCT_DOMAIN}` as const;

/** Transparent brand mark (public/) */
export const LOGO_SRC = "/logo-snaptix.png";

/** Search-facing title: positioning for humans, file formats for crawlers. */
export const SEO_TITLE = `${PRODUCT_NAME} - AI analyst for founders and lean teams | Excel & CSV`;

/** Primary positioning - browser, login, hero eyebrow */
export const POSITIONING_LINE =
  "An AI analyst that shows its work, with every number traced to its source";

/** Short promise - footer, meta support, hero */
export const PRODUCT_TAGLINE = "Weeks of analysis in days. Days in hours.";

/** Browser tab + Open Graph description */
export const META_DESCRIPTION = `${PRODUCT_NAME} turns Excel and CSV data into an operator's briefing: what moved, why it matters, and what to do next, with every number computed from your file and traced to the column and date range behind it.`;

export const SEO_KEYWORDS = [
  "AI business analyst",
  "spreadsheet analytics",
  "Excel analytics",
  "CSV dashboard",
  "AI data analysis",
  "business intelligence",
  "financial analysis software",
  "automated dashboards",
  PRODUCT_NAME,
];

/** Login screen subtitle (same intent as POSITIONING_LINE; split if you want login-only copy) */
export const LOGIN_HEADLINE = POSITIONING_LINE;

/** Public support and sales inbox */
export const CONTACT_EMAIL = "hello@snaptix.ai";

export function contactMailto(subject?: string): string {
  const base = `mailto:${CONTACT_EMAIL}`;
  if (!subject?.trim()) return base;
  return `${base}?subject=${encodeURIComponent(subject.trim())}`;
}
