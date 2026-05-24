/**
 * Dashboard chart colors aligned with globals.css `--chart-*` tokens.
 * Light mode: neutral grays for series. Dark mode: champagne + warm stone.
 * Pie charts use `--pie-*` categorical hues (see globals.css).
 */

export const CHART_GRID = "var(--border)";
export const CHART_MUTED = "var(--muted-foreground)";
export const CHART_TRACK =
  "color-mix(in oklch, var(--muted-foreground) 18%, transparent)";

/** Primary series (bars, lines). */
export const CHART_SERIES = "var(--chart-2)";
export const CHART_SERIES_MID = "var(--chart-3)";
export const CHART_COMPARE = "var(--chart-4)";
export const CHART_COMPARE_MID = "var(--chart-5)";

/** Distinct donut/pie fills — cycles when there are more slices than slots. */
export const PIE_SEGMENT_COUNT = 8;

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

export function pieSegmentFill(index: number, _total?: number): string {
  const slot = (index % PIE_SEGMENT_COUNT) + 1;
  return `var(--pie-${slot})`;
}
