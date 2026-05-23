/**
 * Dashboard chart colors aligned with globals.css `--chart-*` tokens.
 * Light mode: neutral grays. Dark mode: restrained warm accents.
 */

export const CHART_GRID = "var(--border)";
export const CHART_MUTED = "var(--muted-foreground)";
export const CHART_TRACK =
  "color-mix(in oklch, var(--muted-foreground) 18%, transparent)";

/** Primary series (bars, lines, pie base). */
export const CHART_SERIES = "var(--chart-2)";
export const CHART_SERIES_MID = "var(--chart-3)";
export const CHART_COMPARE = "var(--chart-4)";
export const CHART_COMPARE_MID = "var(--chart-5)";

export function seriesPalette() {
  return {
    primary: CHART_SERIES,
    primaryMid: CHART_SERIES_MID,
    primaryStroke: CHART_SERIES,
    compare: CHART_COMPARE,
    compareMid: CHART_COMPARE_MID,
    compareStroke: CHART_COMPARE,
  };
}

/** Pie / multi-segment: same hue, stepped lightness (not rainbow). */
export function pieSegmentFill(index: number, total: number): string {
  if (total <= 1) return CHART_SERIES;
  const t = index / Math.max(total - 1, 1);
  const mix = Math.round(42 + t * 38);
  return `color-mix(in oklch, ${CHART_SERIES} ${mix}%, var(--card))`;
}
