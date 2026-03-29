import type { ConfidenceBand } from "@/lib/analysis-normalize";

/**
 * UI copy that explains how conviction maps to language—honest uncertainty, no overclaiming.
 */

/** One line under the conviction meter on each signal card */
export function confidenceToneCardLine(level: ConfidenceBand): string {
  switch (level) {
    case "high":
      return "High conviction: copy reads direct when the summaries back the claim—no artificial hedging.";
    case "medium":
      return "Medium conviction: copy uses measured phrasing; a fuller slice of the business could shift the read.";
    case "low":
      return "Low conviction: copy stays careful and points to what to validate; richer cost, time, or segment data improves reliability.";
    default:
      return "Not graded: treat lines as directional until you reconcile to source rows.";
  }
}

export const CONFIDENCE_TONE_LEGEND = [
  {
    band: "high" as const,
    title: "High",
    body: "Direct language (for example: expenses outpaced revenue and are likely squeezing margin) when the numbers in the summaries clearly support it.",
  },
  {
    band: "medium",
    title: "Medium",
    body: "Measured language (for example: expenses appear to be growing faster than revenue, which may be reducing margin) when coverage, definitions, or noise leave room for doubt.",
  },
  {
    band: "low",
    title: "Low",
    body: "Careful language (for example: this may indicate expense pressure—validate with more complete cost data) and an explicit path to better data before big commitments.",
  },
] as const;
