"use client";

import type { CSSProperties, ReactElement } from "react";
import {
  Area,
  AreaChart,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  Label,
  LabelList,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  formatChartAxisDate,
  formatChartTooltipDate,
} from "@/lib/chart-dates";
import {
  type PeriodComparison,
  addDaysYmd,
  dayInRange,
  daysBetweenYmd,
  eachDayInRange,
  seriesLabelsFromComparison,
} from "@/lib/chart-period-comparison";
import {
  CHART_COMPARE,
  CHART_GRID,
  CHART_MUTED,
  CHART_SERIES,
  CHART_TRACK,
  pieSegmentFill,
  seriesPalette,
} from "@/lib/chart-theme";
import { ChartFrame } from "@/components/charts/chart-frame";

const SAAS_GRID = CHART_GRID;
const TRACK_FILL = CHART_TRACK;

const tickStyle = {
  fill: CHART_MUTED,
  fontSize: 11,
  fontWeight: 500,
};

export interface ChartConfig {
  id: string;
  title: string;
  type: "line" | "bar" | "pie" | "area";
  data: Record<string, unknown>[];
  x_label?: string;
  y_label?: string;
}

/** Cap after daily merge — keeps charts readable; backend also aggregates by day. */
const MAX_LINE_AREA_POINTS = 480;
const MAX_BAR_POINTS = 120;
const MAX_PIE_SLICES = 24;

type DualPoint = { x: string; y: number | null; yPrev: number | null };

type BarDatum = { name: string; nameFull: string; value: number };

const BAR_LABEL_MAX_CHARS = 30;

function truncateCategoryStart(text: string, maxChars = BAR_LABEL_MAX_CHARS): string {
  const t = text.trim();
  if (t.length <= maxChars) return t;
  return `${t.slice(0, Math.max(1, maxChars - 1))}…`;
}

function barCategoryAxisWidth(data: BarDatum[]): number {
  const longest = data.reduce((m, d) => Math.max(m, d.name.length), 8);
  return Math.min(240, Math.max(108, Math.ceil(longest * 6.8) + 16));
}

function makeCategoryYAxisTick(data: BarDatum[]) {
  const fullByLabel = new Map(data.map((d) => [d.name, d.nameFull]));
  return function CategoryYAxisTick(props: {
    x?: number | string;
    y?: number | string;
    payload?: { value?: string };
  }): ReactElement {
    const x = Number(props.x ?? 0);
    const y = Number(props.y ?? 0);
    const label = String(props.payload?.value ?? "");
    const full = fullByLabel.get(label) ?? label;
    return (
      <g transform={`translate(${x},${y})`}>
        <text
          x={-8}
          y={0}
          dy={4}
          textAnchor="end"
          fill={CHART_MUTED}
          fontSize={11}
          fontWeight={500}
        >
          <title>{full}</title>
          {label}
        </text>
      </g>
    );
  };
}

function downsampleOrdered<T>(points: T[], max: number): T[] {
  if (points.length <= max) return points;
  const out: T[] = [];
  for (let i = 0; i < max; i++) {
    const idx = Math.floor((i / (max - 1)) * (points.length - 1));
    out.push(points[idx]);
  }
  return out;
}

function dayKeyForX(x: string): string {
  const t = Date.parse(x);
  if (Number.isFinite(t)) {
    return new Date(t).toISOString().slice(0, 10);
  }
  return x;
}

/** One point per calendar day — sums y when timestamps fall on the same day. */
function mergePointsByDay(points: { x: string; y: number }[]): { x: string; y: number }[] {
  const acc = new Map<string, number>();
  for (const { x, y } of points) {
    const key = dayKeyForX(x);
    acc.set(key, (acc.get(key) ?? 0) + y);
  }
  return [...acc.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([kx, v]) => ({ x: kx, y: v }));
}

function sortByXAsc(points: { x: string; y: number }[]): { x: string; y: number }[] {
  return [...points].sort((a, b) => {
    const da = Date.parse(a.x);
    const db = Date.parse(b.x);
    if (Number.isFinite(da) && Number.isFinite(db)) return da - db;
    return a.x.localeCompare(b.x);
  });
}

/** 3-point rolling median — dampens single-point spikes (display only). */
function smoothMedian3(values: number[]): number[] {
  const n = values.length;
  if (n < 3) return values.map((v) => v);
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const lo = Math.max(0, i - 1);
    const hi = Math.min(n, i + 2);
    const chunk = values.slice(lo, hi).sort((a, b) => a - b);
    out.push(chunk[Math.floor(chunk.length / 2)]!);
  }
  return out;
}

function sanitizeLineAreaData(
  raw: Record<string, unknown>[]
): { x: string; y: number }[] {
  const rows = raw
    .map((row) => {
      const x = row.x != null ? String(row.x) : "";
      const y = Number(row.y);
      return { x, y };
    })
    .filter((r) => r.x !== "" && Number.isFinite(r.y));
  const merged = mergePointsByDay(rows);
  const sorted = sortByXAsc(merged);
  const ys = smoothMedian3(sorted.map((r) => r.y));
  const smoothed = sorted.map((r, i) => ({ x: r.x, y: ys[i]! }));
  return downsampleOrdered(smoothed, MAX_LINE_AREA_POINTS);
}

/**
 * Current vs prior window on the **same x-axis** (current period dates).
 * Each point's previous value is the aligned day in the prior window
 * (e.g. May 15 vs Apr 15 when both periods are 30 days).
 */
function buildCalendarDualPeriod(
  points: { x: string; y: number }[],
  pc: PeriodComparison
): DualPoint[] {
  const cur = pc.current!;
  const prev = pc.previous!;
  const byDay = new Map<string, number>();
  for (const p of mergePointsByDay(points)) {
    byDay.set(p.x, (byDay.get(p.x) ?? 0) + p.y);
  }
  const curDays = eachDayInRange(cur.start, cur.end);
  return curDays.map((day) => {
    const offset = daysBetweenYmd(cur.start, day);
    const prevDay = addDaysYmd(prev.start, offset);
    const prevAligned =
      dayInRange(prevDay, prev.start, prev.end) && prevDay <= prev.end;
    return {
      x: day,
      y: byDay.get(day) ?? 0,
      yPrev: prevAligned ? (byDay.get(prevDay) ?? 0) : null,
    };
  });
}

function hasPreviousSeries(data: DualPoint[]): boolean {
  return data.some((d) => d.yPrev != null && Number.isFinite(d.yPrev));
}

function maxBarLabelChars(axisWidth: number): number {
  return Math.max(12, Math.min(42, Math.floor((axisWidth - 20) / 6.5)));
}

function sanitizeBarData(raw: Record<string, unknown>[]): BarDatum[] {
  const rows = raw
    .map((row) => ({
      name: row.name != null ? String(row.name) : "",
      value: Number(row.value),
    }))
    .filter((r) => r.name !== "" && Number.isFinite(r.value))
    .slice(0, MAX_BAR_POINTS);
  const axisWidth = barCategoryAxisWidth(
    rows.map((r) => ({
      name: truncateCategoryStart(r.name, BAR_LABEL_MAX_CHARS),
      nameFull: r.name,
      value: r.value,
    }))
  );
  const maxChars = maxBarLabelChars(axisWidth);
  return rows.map((r) => ({
    nameFull: r.name,
    name: truncateCategoryStart(r.name, maxChars),
    value: r.value,
  }));
}

function sanitizePieData(
  raw: Record<string, unknown>[]
): { name: string; value: number }[] {
  const rows = raw
    .map((row) => ({
      name: row.name != null ? String(row.name) : "",
      value: Number(row.value),
    }))
    .filter(
      (r) => r.name !== "" && Number.isFinite(r.value) && r.value >= 0
    );
  return rows.slice(0, MAX_PIE_SLICES);
}

type PreparedChart =
  | { type: "line"; data: DualPoint[] }
  | { type: "area"; data: DualPoint[] }
  | { type: "bar"; data: BarDatum[] }
  | { type: "pie"; data: { name: string; value: number }[] };

function titleCaseWords(s: string): string {
  return s
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

/** Display name for insight sentences (prefer Y axis / metric column). */
function humanizeMetricLabel(chart: ChartConfig): string {
  if (chart.y_label?.trim()) {
    return titleCaseWords(chart.y_label.replace(/_/g, " "));
  }
  let t = (chart.title || "This metric").replace(/_/g, " ");
  t = t.replace(/\s+over\s+time\s*$/i, "").trim();
  return titleCaseWords(t || "This metric");
}

function mean(nums: number[]): number {
  if (!nums.length) return NaN;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

function formatInsightMetric(value: number): string {
  if (!Number.isFinite(value)) return "—";
  return value.toLocaleString(undefined, {
    notation: "standard",
    maximumFractionDigits: 2,
  });
}

type ChartInsightLines = { line1: string; line2?: string };

/** Sum in each calendar window when period comparison is available. */
function lineAreaPeriodInsight(
  data: DualPoint[],
  chart: ChartConfig,
  periodComparison?: PeriodComparison | null,
  seriesLabels?: { current: string; previous: string } | null
): ChartInsightLines {
  const label = humanizeMetricLabel(chart);
  const curVals = data
    .map((d) => d.y)
    .filter((v): v is number => v != null && Number.isFinite(v));
  const prevVals = data
    .map((d) => d.yPrev)
    .filter((v): v is number => v != null && Number.isFinite(v));

  if (curVals.length < 1) {
    return {
      line1: `Not enough history to chart ${label} for the selected period.`,
    };
  }

  const curTotal = curVals.reduce((a, b) => a + b, 0);
  const prevTotal =
    prevVals.length > 0 ? prevVals.reduce((a, b) => a + b, 0) : NaN;

  const eps = 1e-9 * Math.max(1, Math.abs(curTotal), Math.abs(prevTotal));

  let line1: string;
  if (!Number.isFinite(prevTotal) || prevVals.length === 0) {
    line1 = `${label} in the selected period totals ${formatInsightMetric(curTotal)}.`;
    const line2 = periodComparison?.description
      ? `Comparison: ${periodComparison.description}.`
      : undefined;
    return { line1, line2 };
  }

  if (Math.abs(prevTotal) < eps && Math.abs(curTotal) < eps) {
    line1 = `${label} is effectively flat between the two periods.`;
  } else if (Math.abs(prevTotal) < eps) {
    line1 = `${label} rose versus a very small prior-period total.`;
  } else {
    const pct = ((curTotal - prevTotal) / Math.abs(prevTotal)) * 100;
    if (Math.abs(pct) < 0.5) {
      line1 = `${label} is nearly unchanged between the two periods (under 1%).`;
    } else if (pct > 0) {
      line1 = `${label} increased by ${pct.toFixed(0)}% versus the prior period.`;
    } else {
      line1 = `${label} decreased by ${Math.abs(pct).toFixed(0)}% versus the prior period.`;
    }
  }

  const line2 = seriesLabels
    ? `${seriesLabels.current}: ${formatInsightMetric(curTotal)} total · ${seriesLabels.previous}: ${formatInsightMetric(prevTotal)} total`
    : periodComparison?.description
      ? periodComparison.description
      : `Current total ${formatInsightMetric(curTotal)} vs prior ${formatInsightMetric(prevTotal)}.`;

  return { line1, line2 };
}

function barOrPieInsight(
  data: { name: string; nameFull?: string; value: number }[],
  chart: ChartConfig,
  kind: "bar" | "pie"
): ChartInsightLines {
  const label = humanizeMetricLabel(chart);
  if (!data.length) {
    return { line1: `No categories to summarize for ${label}.` };
  }
  const sorted = [...data].sort((a, b) => b.value - a.value);
  const total = sorted.reduce((s, d) => s + d.value, 0);
  const top = sorted[0]!;
  const topShare = total > 0 ? (top.value / total) * 100 : 0;
  const topName = String(top.nameFull ?? top.name);

  let line1: string;
  if (kind === "pie") {
    line1 =
      total > 0
        ? `"${topName}" is the largest slice at ${topShare.toFixed(0)}% of ${label}.`
        : `"${topName}" is the largest slice in this breakdown.`;
  } else {
    line1 =
      total > 0
        ? `"${topName}" leads with ${topShare.toFixed(0)}% of total ${label.toLowerCase()}.`
        : `"${topName}" is the top category in this view.`;
  }

  let line2: string | undefined;
  if (sorted.length >= 2) {
    const second = sorted[1]!;
    const secondName = String(second.nameFull ?? second.name);
    if (second.value > 0) {
      const vsPrev = ((top.value - second.value) / second.value) * 100;
      if (Math.abs(vsPrev) < 0.5) {
        line2 = `Nearly tied with "${secondName}" — less than 1% apart.`;
      } else {
        line2 = `${vsPrev.toFixed(0)}% ahead of "${secondName}".`;
      }
    } else {
      line2 = `Next listed category is "${secondName}".`;
    }
  }

  return { line1, line2 };
}

function insightForPrepared(
  prepared: PreparedChart,
  chart: ChartConfig,
  periodComparison?: PeriodComparison | null,
  seriesLabels?: { current: string; previous: string } | null
): ChartInsightLines {
  switch (prepared.type) {
    case "line":
    case "area":
      return lineAreaPeriodInsight(
        prepared.data,
        chart,
        periodComparison,
        seriesLabels
      );
    case "bar":
      return barOrPieInsight(prepared.data, chart, "bar");
    case "pie":
      return barOrPieInsight(prepared.data, chart, "pie");
    default:
      return { line1: "" };
  }
}

function prepareChart(
  chart: ChartConfig,
  periodComparison?: PeriodComparison | null
): PreparedChart | null {
  switch (chart.type) {
    case "line":
    case "area": {
      const raw = sanitizeLineAreaData(chart.data);
      if (!raw.length) return null;
      const data =
        periodComparison?.available &&
        periodComparison.current &&
        periodComparison.previous
          ? buildCalendarDualPeriod(raw, periodComparison)
          : raw.map((d) => ({ x: d.x, y: d.y, yPrev: null }));
      return { type: chart.type, data };
    }
    case "bar": {
      const data = sanitizeBarData(chart.data);
      return data.length ? { type: "bar", data } : null;
    }
    case "pie": {
      const data = sanitizePieData(chart.data);
      return data.length ? { type: "pie", data } : null;
    }
    default:
      return null;
  }
}

function getSaaSPalette(_accentIndex: number, _kind: "line" | "area") {
  return seriesPalette();
}

function LegendPills({
  payload,
}: {
  payload?: ReadonlyArray<{ value?: string | number; color?: string }>;
}) {
  if (!payload?.length) return null;
  return (
    <ul className="flex list-none flex-wrap justify-center gap-2 px-2 pt-2">
      {payload.map((entry, i) => (
        <li
          key={i}
          className="inline-flex items-center gap-2 rounded-full border border-border bg-card/90 px-3 py-1 text-[11px] font-medium text-muted-foreground shadow-sm"
        >
          <span
            className="inline-block h-2.5 w-2.5 rounded-full"
            style={{ backgroundColor: entry.color ?? "#64748b" }}
          />
          {entry.value}
        </li>
      ))}
    </ul>
  );
}

function tooltipShell(): CSSProperties {
  return {
    borderRadius: 16,
    border: "1px solid color-mix(in oklch, var(--border) 88%, transparent)",
    boxShadow:
      "0 24px 60px -20px color-mix(in oklch, var(--foreground) 12%, transparent)",
    background: "color-mix(in oklch, var(--card) 94%, transparent)",
    backdropFilter: "blur(12px)",
    padding: "13px 15px",
    minWidth: 160,
    color: "var(--foreground)",
  };
}

function SaaSTooltip({
  active,
  payload,
  label,
  seriesLabels,
}: {
  active?: boolean;
  payload?: ReadonlyArray<{
    payload?: DualPoint;
    dataKey?: string | number;
    color?: string;
    value?: number;
  }>;
  label?: string;
  seriesLabels?: { current: string; previous: string } | null;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload;
  if (!row) return null;
  const cur = payload.find((p) => p.dataKey === "y");
  const prev = payload.find((p) => p.dataKey === "yPrev");
  const curColor = cur?.color ?? CHART_SERIES;
  const prevColor = prev?.color ?? CHART_COMPARE;
  const curLabel = seriesLabels?.current ?? "Current period";
  const prevLabel = seriesLabels?.previous ?? "Previous period";
  const showCur = row.y != null && Number.isFinite(row.y);
  const showPrev = row.yPrev != null && Number.isFinite(row.yPrev);
  return (
    <div style={tooltipShell()}>
      <p
        style={{
          margin: 0,
          fontSize: 11,
          fontWeight: 600,
          color: "var(--muted-foreground)",
          textTransform: "uppercase",
          letterSpacing: "0.04em",
        }}
      >
        {formatChartTooltipDate(label)}
      </p>
      <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
        {showCur ? (
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
            <span style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11, color: "var(--muted-foreground)", maxWidth: 160 }}>
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: 9999,
                  background: "var(--card)",
                  border: `2px solid ${curColor}`,
                  boxSizing: "border-box",
                  flexShrink: 0,
                }}
              />
              <span>{curLabel}</span>
            </span>
            <span style={{ fontSize: 13, fontWeight: 650, fontFeatureSettings: '"tnum"', color: "var(--foreground)" }}>
              {formatTooltip(row.y)}
            </span>
          </div>
        ) : null}
        {showPrev ? (
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
            <span style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11, color: "var(--muted-foreground)", maxWidth: 160 }}>
              <span
                style={{
                  width: 12,
                  height: 0,
                  borderTop: `2px dashed ${prevColor}`,
                  flexShrink: 0,
                }}
              />
              <span>{prevLabel}</span>
            </span>
            <span style={{ fontSize: 13, fontWeight: 650, fontFeatureSettings: '"tnum"', color: "var(--muted-foreground)" }}>
              {formatTooltip(row.yPrev)}
            </span>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function AutoChart({
  chart,
  accentIndex = 0,
  periodComparison = null,
}: {
  chart: ChartConfig;
  accentIndex?: number;
  periodComparison?: PeriodComparison | null;
}) {
  const seriesLabels = seriesLabelsFromComparison(periodComparison);
  const prepared = prepareChart(chart, periodComparison);
  const safeId = chart.id.replace(/[^a-zA-Z0-9_-]/g, "_");

  if (!prepared) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">{chart.title}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="py-8 text-center text-sm text-muted-foreground">
            Not enough valid numeric data to plot this chart.
          </p>
        </CardContent>
      </Card>
    );
  }

  const insight = insightForPrepared(
    prepared,
    chart,
    periodComparison,
    seriesLabels
  );

  return (
    <Card>
      <CardHeader className="space-y-1 pb-2">
        <CardTitle className="text-sm font-medium">{chart.title}</CardTitle>
        {periodComparison?.description && (prepared.type === "line" || prepared.type === "area") ? (
          <p className="text-xs text-muted-foreground">{periodComparison.description}</p>
        ) : null}
        {insight.line1 ? (
          <div className="max-w-2xl space-y-1">
            <p className="text-sm text-foreground">{insight.line1}</p>
            {insight.line2 ? (
              <p className="text-xs text-muted-foreground">{insight.line2}</p>
            ) : null}
          </div>
        ) : null}
      </CardHeader>
      <CardContent className="pt-0">
        <div className="h-72 min-h-[18rem] w-full rounded-lg bg-gradient-to-b from-muted/20 to-transparent px-1 pb-1 pt-2">
          <ChartFrame className="h-full">
            <ResponsiveContainer width="100%" height="100%">
              {renderChart(prepared, safeId, accentIndex, seriesLabels)}
            </ResponsiveContainer>
          </ChartFrame>
        </div>
      </CardContent>
    </Card>
  );
}

/** ~1 tick per week for 30d+, all ticks only for 7d/14d-sized series (avoids overlap in 2-col layout). */
function timeSeriesXAxisProps(pointCount: number) {
  const n = pointCount;
  const compact = n > 0 && n <= 14;
  const interval = compact ? 0 : Math.max(1, Math.ceil(n / 8) - 1);
  const bottom = compact ? 16 : 28;
  const minTickGap = compact ? 4 : 12;
  const tick =
    compact
      ? tickStyle
      : { ...tickStyle, angle: -32, textAnchor: "end" as const };
  return { interval, bottom, minTickGap, tick };
}

function renderDualArea(
  data: DualPoint[],
  safeId: string,
  kind: "line" | "area",
  accentIndex: number,
  seriesLabels?: { current: string; previous: string } | null
) {
  const p = getSaaSPalette(accentIndex, kind);
  const idCur = `saasCur-${safeId}`;
  const idPrev = `saasPrev-${safeId}`;
  const xAxis = timeSeriesXAxisProps(data.length);
  /** Backend `line` is rendered here without fills so it reads as a true line chart (no warm wash). */
  const strokeOnly = kind === "line";
  const showPrev = hasPreviousSeries(data);
  const curName = seriesLabels?.current ?? "Current period";
  const prevName = seriesLabels?.previous ?? "Previous period";

  return (
    <AreaChart
      data={data}
      margin={{ top: 14, right: 10, left: 4, bottom: xAxis.bottom }}
    >
      <defs>
        <linearGradient id={idCur} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={p.primaryMid} stopOpacity={strokeOnly ? 0 : 0.12} />
          <stop offset="55%" stopColor={p.primaryMid} stopOpacity={strokeOnly ? 0 : 0.05} />
          <stop offset="100%" stopColor={p.primary} stopOpacity={0} />
        </linearGradient>
        <linearGradient id={idPrev} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={p.compareMid} stopOpacity={strokeOnly ? 0 : 0.08} />
          <stop offset="60%" stopColor={p.compare} stopOpacity={strokeOnly ? 0 : 0.03} />
          <stop offset="100%" stopColor={p.compare} stopOpacity={0} />
        </linearGradient>
      </defs>
      <CartesianGrid
        stroke={SAAS_GRID}
        strokeDasharray="4 6"
        strokeOpacity={0.45}
        vertical={false}
        horizontal
      />
      <XAxis
        dataKey="x"
        tick={xAxis.tick}
        tickLine={false}
        axisLine={false}
        tickFormatter={formatChartAxisDate}
        tickMargin={8}
        interval={xAxis.interval}
        minTickGap={xAxis.minTickGap}
      />
      <YAxis
        tick={tickStyle}
        tickLine={false}
        axisLine={false}
        tickFormatter={formatNumber}
        width={64}
      />
      <Tooltip content={<SaaSTooltip seriesLabels={seriesLabels} />} />
      {showPrev ? (
        <Legend
          verticalAlign="bottom"
          align="center"
          iconType="line"
          iconSize={11}
          wrapperStyle={{ paddingTop: 6 }}
          content={({ payload }) => {
            if (!payload?.length) return null;
            return <LegendPills payload={payload} />;
          }}
        />
      ) : null}
      {showPrev ? (
        <Area
          type="monotone"
          dataKey="yPrev"
          name={prevName}
          connectNulls={false}
          stroke={p.compareStroke}
          strokeWidth={2.25}
          strokeDasharray="6 5"
          fill={strokeOnly ? "none" : `url(#${idPrev})`}
          fillOpacity={strokeOnly ? 0 : 0.55}
          dot={false}
          activeDot={{
            r: 5,
            strokeWidth: 2,
            stroke: p.compareStroke,
            fill: "var(--card)",
          }}
          isAnimationActive={false}
        />
      ) : null}
      <Area
        type="monotone"
        dataKey="y"
        name={curName}
        connectNulls={false}
        stroke={p.primaryStroke}
        strokeWidth={2.6}
        fill={strokeOnly ? "none" : `url(#${idCur})`}
        fillOpacity={strokeOnly ? 0 : 0.75}
        dot={false}
        activeDot={{
          r: 5,
          strokeWidth: 2,
          stroke: p.primaryStroke,
          fill: "var(--card)",
        }}
        isAnimationActive={false}
      />
    </AreaChart>
  );
}

function renderChart(
  chart: PreparedChart,
  safeId: string,
  accentIndex: number,
  seriesLabels?: { current: string; previous: string } | null
) {
  const { type, data } = chart;

  switch (type) {
    case "line":
      return renderDualArea(data, safeId, "line", accentIndex, seriesLabels);

    case "area":
      return renderDualArea(data, safeId, "area", accentIndex, seriesLabels);

    case "bar": {
      const yWidth = barCategoryAxisWidth(data);
      return (
        <BarChart
          layout="vertical"
          data={data}
          margin={{ top: 8, right: 28, left: 4, bottom: 8 }}
        >
          <CartesianGrid
            stroke={SAAS_GRID}
            strokeDasharray="4 6"
            horizontal={false}
          />
          <XAxis
            type="number"
            tick={tickStyle}
            tickLine={false}
            axisLine={false}
            tickFormatter={formatNumber}
          />
          <YAxis
            type="category"
            dataKey="name"
            width={yWidth}
            tick={makeCategoryYAxisTick(data)}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            content={({ active, payload: items }) => {
              if (!active || !items?.length) return null;
              const row = items[0]?.payload as BarDatum | undefined;
              if (!row) return null;
              return (
                <div style={tooltipShell()}>
                  <p style={{ margin: 0, fontSize: 12, fontWeight: 600, color: "var(--foreground)", maxWidth: 280 }}>
                    {row.nameFull}
                  </p>
                  <p style={{ margin: "6px 0 0", fontSize: 13, fontWeight: 650, color: "var(--muted-foreground)" }}>
                    {formatTooltip(row.value)}
                  </p>
                </div>
              );
            }}
          />
          <Bar
            dataKey="value"
            fill={CHART_SERIES}
            barSize={18}
            radius={[999, 999, 999, 999]}
            background={{ fill: TRACK_FILL, radius: 999 }}
            isAnimationActive={false}
          >
            <LabelList
              dataKey="value"
              position="right"
              offset={8}
              className="fill-muted-foreground text-[11px] font-medium"
              formatter={(value: unknown) => formatTooltip(value)}
            />
          </Bar>
        </BarChart>
      );
    }

    case "pie":
      const pieTotal = data.reduce((sum, slice) => sum + slice.value, 0);
      return (
        <PieChart margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            cx="50%"
            cy="48%"
            innerRadius="60%"
            outerRadius="82%"
            paddingAngle={2}
            cornerRadius={10}
            stroke="var(--card)"
            strokeWidth={2.5}
            label={false}
            labelLine={false}
            isAnimationActive={false}
          >
            {data.map((_, i) => (
              <Cell key={i} fill={pieSegmentFill(i, data.length)} />
            ))}
            <Label
              position="center"
              content={() => (
                <text textAnchor="middle" dominantBaseline="middle">
                  <tspan
                    x="50%"
                    y="44%"
                    fill="var(--muted-foreground)"
                    fontSize="11"
                    fontWeight="600"
                  >
                    Total
                  </tspan>
                  <tspan
                    x="50%"
                    y="58%"
                    fill="var(--foreground)"
                    fontSize="18"
                    fontWeight="700"
                  >
                    {formatTooltip(pieTotal)}
                  </tspan>
                </text>
              )}
            />
          </Pie>
          <Tooltip formatter={formatTooltip} contentStyle={tooltipShell()} />
          <Legend
            verticalAlign="bottom"
            align="center"
            wrapperStyle={{ paddingTop: 10 }}
            content={({ payload }) => <LegendPills payload={payload} />}
          />
        </PieChart>
      );

    default:
      return (
        <BarChart data={data} layout="vertical">
          <Bar
            dataKey="value"
            fill={CHART_SERIES}
            radius={[0, 12, 12, 0]}
            isAnimationActive={false}
          />
        </BarChart>
      );
  }
}

function formatNumber(value: unknown) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "";
  return n.toLocaleString(undefined, {
    notation: "standard",
    maximumFractionDigits: n >= 100 && Number.isInteger(n) ? 0 : 2,
  });
}

function formatTooltip(value: unknown) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString(undefined, {
    notation: "standard",
    maximumFractionDigits: 2,
  });
}
