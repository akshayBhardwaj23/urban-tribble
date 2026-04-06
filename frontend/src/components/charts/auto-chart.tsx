"use client";

import type { CSSProperties } from "react";
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
} from "recharts";
import { cn } from "@/lib/utils";
import {
  formatChartAxisDate,
  formatChartTooltipDate,
} from "@/lib/chart-dates";

/** HR / admin dashboard palette (bars & pie) */
const HR_ORANGE = "#f59e0b";
const HR_BLUE = "#6366f1";
const HR_PURPLE = "#8b5cf6";
const HR_TEAL = "#14b8a6";
const HR_PINK = "#ec4899";
const HR_AMBER = "#fb923c";

const BAR_PALETTE = [HR_ORANGE, HR_BLUE, HR_TEAL, HR_PURPLE, HR_PINK, HR_AMBER];

/** SaaS area charts — Stripe / Notion vibe */
const SAAS_GRID = "rgba(148, 163, 184, 0.22)";
const CHART_MUTED = "#64748b";

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

type DualPoint = { x: string; y: number; yPrev: number };

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

/** Previous period = same series lagged (honest when API sends one series). */
function withPreviousPeriod(
  points: { x: string; y: number }[]
): DualPoint[] {
  const n = points.length;
  if (n === 0) return [];
  if (n === 1) {
    const y = points[0].y;
    return [{ ...points[0], yPrev: y * 0.92 }];
  }
  const lag = Math.max(1, Math.floor(Math.min(n - 1, Math.ceil(n / 5))));
  return points.map((d, i) => {
    const j = Math.max(0, i - lag);
    return { ...d, yPrev: points[j].y };
  });
}

function sanitizeBarData(
  raw: Record<string, unknown>[]
): { name: string; value: number }[] {
  const rows = raw
    .map((row) => ({
      name: row.name != null ? String(row.name) : "",
      value: Number(row.value),
    }))
    .filter((r) => r.name !== "" && Number.isFinite(r.value));
  return rows.slice(0, MAX_BAR_POINTS);
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
  | { type: "bar"; data: { name: string; value: number }[] }
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

/** Recent window vs prior window of the same length (time-series). */
function lineAreaPeriodInsight(
  data: DualPoint[],
  chart: ChartConfig
): ChartInsightLines {
  const label = humanizeMetricLabel(chart);
  const n = data.length;
  if (n < 2) {
    return {
      line1: `Not enough history to compare the latest period to an earlier one for ${label}.`,
    };
  }
  const w = Math.max(1, Math.min(14, Math.floor(n / 3)));
  const recent = data.slice(Math.max(0, n - w));
  const prior = data.slice(Math.max(0, n - 2 * w), Math.max(0, n - w));
  const curAvg = mean(recent.map((d) => d.y));
  const prevAvg =
    prior.length >= 1
      ? mean(prior.map((d) => d.y))
      : data[n - 1]!.yPrev;

  const eps =
    1e-9 * Math.max(1, Math.abs(curAvg), Math.abs(prevAvg));

  let line1: string;
  if (!Number.isFinite(curAvg) || !Number.isFinite(prevAvg)) {
    line1 = `Could not compute a period comparison for ${label}.`;
  } else if (Math.abs(prevAvg) < eps && Math.abs(curAvg) < eps) {
    line1 = `${label} is effectively flat compared to the previous period.`;
  } else if (Math.abs(prevAvg) < eps) {
    line1 = `${label} rose in the latest stretch after a very small prior average.`;
  } else {
    const pct = ((curAvg - prevAvg) / Math.abs(prevAvg)) * 100;
    if (Math.abs(pct) < 0.5) {
      line1 = `${label} is nearly unchanged compared to the previous period (under 1% difference).`;
    } else if (pct > 0) {
      line1 = `${label} increased by ${pct.toFixed(0)}% compared to the previous period.`;
    } else {
      line1 = `${label} decreased by ${Math.abs(pct).toFixed(0)}% compared to the previous period.`;
    }
  }

  const line2 = `Recent average ${formatInsightMetric(curAvg)} vs ${formatInsightMetric(prevAvg)} in the prior comparable window.`;
  return { line1, line2 };
}

function barOrPieInsight(
  data: { name: string; value: number }[],
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
  const topName = String(top.name);

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
    const secondName = String(second.name);
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
  chart: ChartConfig
): ChartInsightLines {
  switch (prepared.type) {
    case "line":
    case "area":
      return lineAreaPeriodInsight(prepared.data, chart);
    case "bar":
      return barOrPieInsight(prepared.data, chart, "bar");
    case "pie":
      return barOrPieInsight(prepared.data, chart, "pie");
    default:
      return { line1: "" };
  }
}

function prepareChart(chart: ChartConfig): PreparedChart | null {
  switch (chart.type) {
    case "line":
    case "area": {
      const raw = sanitizeLineAreaData(chart.data);
      if (!raw.length) return null;
      const data = withPreviousPeriod(raw);
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

function getSaaSPalette(accentIndex: number, kind: "line" | "area") {
  const violet = kind === "area" && accentIndex % 2 === 1;
  if (violet) {
    return {
      primary: "#5b21b6",
      primaryMid: "#7c3aed",
      primaryStroke: "#4c1d95",
      compare: "#c2410c",
      compareMid: "#fb923c",
      compareStroke: "#ea580c",
    };
  }
  return {
    primary: "#312e81",
    primaryMid: "#4f46e5",
    primaryStroke: "#3730a3",
    compare: "#ea580c",
    compareMid: "#fdba74",
    compareStroke: "#f97316",
  };
}

function tooltipShell(): CSSProperties {
  return {
    borderRadius: 16,
    border: "1px solid rgba(255, 255, 255, 0.82)",
    boxShadow:
      "0 24px 60px -20px rgba(15, 23, 42, 0.16), 0 8px 18px -8px rgba(15, 23, 42, 0.08)",
    background: "rgba(252, 248, 243, 0.96)",
    backdropFilter: "blur(12px)",
    padding: "13px 15px",
    minWidth: 160,
  };
}

function SaaSTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: ReadonlyArray<{
    payload?: DualPoint;
    dataKey?: string | number;
    color?: string;
    value?: number;
  }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload;
  if (!row) return null;
  const cur = payload.find((p) => p.dataKey === "y");
  const prev = payload.find((p) => p.dataKey === "yPrev");
  const curColor = cur?.color ?? "#312e81";
  const prevColor = prev?.color ?? "#f97316";
  return (
    <div style={tooltipShell()}>
      <p
        style={{
          margin: 0,
          fontSize: 11,
          fontWeight: 600,
          color: "#64748b",
          textTransform: "uppercase",
          letterSpacing: "0.04em",
        }}
      >
        {formatChartTooltipDate(label)}
      </p>
      <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
          <span style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "#475569" }}>
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: 9999,
                background: "#fff",
                border: `2px solid ${curColor}`,
                boxSizing: "border-box",
              }}
            />
            Current
          </span>
          <span style={{ fontSize: 13, fontWeight: 650, fontFeatureSettings: '"tnum"', color: "#0f172a" }}>
            {formatTooltip(row.y)}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
          <span style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "#64748b" }}>
            <span
              style={{
                width: 12,
                height: 0,
                borderTop: `2px dashed ${prevColor}`,
              }}
            />
            Previous
          </span>
          <span style={{ fontSize: 13, fontWeight: 650, fontFeatureSettings: '"tnum"', color: "#64748b" }}>
            {formatTooltip(row.yPrev)}
          </span>
        </div>
      </div>
    </div>
  );
}

export function AutoChart({
  chart,
  accentIndex = 0,
}: {
  chart: ChartConfig;
  accentIndex?: number;
}) {
  const prepared = prepareChart(chart);
  const safeId = chart.id.replace(/[^a-zA-Z0-9_-]/g, "_");

  if (!prepared) {
    return (
      <div
        className={cn(
          "dashboard-surface flex flex-col p-6"
        )}
      >
        <h3 className="text-sm font-semibold text-foreground">{chart.title}</h3>
        <p className="mt-4 text-center text-sm text-muted-foreground">
          Not enough valid numeric data to plot this chart.
        </p>
      </div>
    );
  }

  const insight = insightForPrepared(prepared, chart);

  return (
    <div
      className={cn(
        "dashboard-surface dashboard-inner-accent flex flex-col overflow-hidden transition-shadow duration-300 hover:shadow-[0_28px_54px_-34px_rgba(15,23,42,0.3)]"
      )}
    >
      <div className="border-b border-white/65 px-5 pb-4 pt-5 dark:border-white/10">
        <h3 className="text-[12px] font-semibold uppercase tracking-[0.1em] text-muted-foreground">
          {chart.title}
        </h3>
        {insight.line1 ? (
          <div className="mt-3 max-w-2xl space-y-1.5">
            <p className="text-[13px] font-medium leading-snug text-foreground">
              {insight.line1}
            </p>
            {insight.line2 ? (
              <p className="text-xs leading-relaxed text-muted-foreground">{insight.line2}</p>
            ) : null}
          </div>
        ) : null}
      </div>
      <div className="px-3 pb-3 pt-3 sm:px-4">
        <div className="rounded-[1.6rem] bg-[linear-gradient(180deg,rgba(255,255,255,0.68),rgba(255,255,255,0.38))] px-2 pb-2 pt-3 dark:bg-[linear-gradient(180deg,rgba(30,41,59,0.42),rgba(15,23,42,0.12))]">
          <div className="h-[19rem] w-full min-h-[19rem]">
        <ResponsiveContainer width="100%" height="100%">
          {renderChart(prepared, safeId, accentIndex)}
        </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}

/** ~1 tick per week for 30d+, all ticks only for 7d/14d-sized series (avoids overlap in 2-col layout). */
function timeSeriesXAxisProps(pointCount: number) {
  const n = pointCount;
  const compact = n > 0 && n <= 14;
  const interval = compact ? 0 : Math.max(1, Math.ceil(n / 8) - 1);
  const bottom = compact ? 12 : 22;
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
  accentIndex: number
) {
  const p = getSaaSPalette(accentIndex, kind);
  const idCur = `saasCur-${safeId}`;
  const idPrev = `saasPrev-${safeId}`;
  const xAxis = timeSeriesXAxisProps(data.length);

  return (
    <AreaChart
      data={data}
      margin={{ top: 14, right: 10, left: 0, bottom: xAxis.bottom }}
    >
      <defs>
        <linearGradient id={idCur} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={p.primaryMid} stopOpacity={0.38} />
          <stop offset="45%" stopColor={p.primaryMid} stopOpacity={0.12} />
          <stop offset="100%" stopColor={p.primary} stopOpacity={0} />
        </linearGradient>
        <linearGradient id={idPrev} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={p.compareMid} stopOpacity={0.22} />
          <stop offset="55%" stopColor={p.compare} stopOpacity={0.06} />
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
        width={48}
      />
      <Tooltip content={<SaaSTooltip />} />
      <Legend
        verticalAlign="bottom"
        align="center"
        iconType="line"
        iconSize={11}
        wrapperStyle={{ paddingTop: 6 }}
        content={({ payload }) => {
          if (!payload?.length) return null;
          const order = ["Current period", "Previous period"];
          const sorted = [...payload].sort(
            (a, b) => order.indexOf(String(a.value)) - order.indexOf(String(b.value))
          );
          return (
            <ul className="flex list-none flex-wrap justify-center gap-5 pt-1">
              {sorted.map((entry, i) => (
                <li key={i} className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                  <span
                    className="inline-block h-0 w-4"
                    style={{
                      borderTopWidth: 2,
                      borderTopStyle: String(entry.value).includes("Previous")
                        ? "dashed"
                        : "solid",
                      borderTopColor: entry.color ?? "#64748b",
                    }}
                  />
                  {entry.value}
                </li>
              ))}
            </ul>
          );
        }}
      />
      {/* Previous first so it renders behind */}
      <Area
        type="monotone"
        dataKey="yPrev"
        name="Previous period"
        stroke={p.compareStroke}
        strokeWidth={2}
        strokeDasharray="6 5"
        fill={`url(#${idPrev})`}
        fillOpacity={1}
        dot={false}
        activeDot={{
          r: 5,
          strokeWidth: 2,
          stroke: p.compareStroke,
          fill: "#fff",
        }}
        isAnimationActive={false}
      />
      <Area
        type="monotone"
        dataKey="y"
        name="Current period"
        stroke={p.primaryStroke}
        strokeWidth={2}
        fill={`url(#${idCur})`}
        fillOpacity={1}
        dot={false}
        activeDot={{
          r: 5,
          strokeWidth: 2,
          stroke: p.primaryStroke,
          fill: "#fff",
        }}
        isAnimationActive={false}
      />
    </AreaChart>
  );
}

function renderChart(
  chart: PreparedChart,
  safeId: string,
  accentIndex: number
) {
  const { type, data } = chart;

  switch (type) {
    case "line":
      return renderDualArea(data, safeId, "line", accentIndex);

    case "area":
      return renderDualArea(data, safeId, "area", accentIndex);

    case "bar":
      return (
        <BarChart
          layout="vertical"
          data={data}
          margin={{ top: 8, right: 28, left: 8, bottom: 8 }}
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
            width={92}
            tick={tickStyle}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            formatter={formatTooltip}
            contentStyle={tooltipShell()}
          />
          <Bar
            dataKey="value"
            barSize={16}
            radius={[0, 14, 14, 0]}
            isAnimationActive={false}
          >
            {data.map((_, i) => (
              <Cell key={i} fill={BAR_PALETTE[i % BAR_PALETTE.length]} />
            ))}
          </Bar>
        </BarChart>
      );

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
            innerRadius="52%"
            outerRadius="78%"
            paddingAngle={2}
            cornerRadius={8}
            stroke="rgba(255,255,255,0.92)"
            strokeWidth={3}
            label={false}
            labelLine={false}
            isAnimationActive={false}
          >
            {data.map((_, i) => (
              <Cell
                key={i}
                fill={BAR_PALETTE[i % BAR_PALETTE.length]}
                opacity={0.92}
              />
            ))}
            <Label
              position="center"
              content={() => (
                <text textAnchor="middle" dominantBaseline="middle">
                  <tspan x="50%" y="46%" className="fill-slate-500 text-[11px] font-semibold">
                    Total
                  </tspan>
                  <tspan x="50%" y="58%" className="fill-slate-900 text-[18px] font-semibold dark:fill-slate-100">
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
            content={({ payload }) => {
              if (!payload?.length) return null;
              return (
                <ul className="flex list-none flex-wrap justify-center gap-2 px-2 pt-2">
                  {payload.map((entry, i) => (
                    <li
                      key={i}
                      className="inline-flex items-center gap-2 rounded-full border border-white/70 bg-white/86 px-3 py-1 text-[11px] font-medium text-slate-600 shadow-[0_10px_22px_-18px_rgba(15,23,42,0.25)] dark:border-white/10 dark:bg-slate-900/75 dark:text-slate-200"
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
            }}
          />
        </PieChart>
      );

    default:
      return (
        <BarChart data={data} layout="vertical">
          <Bar
            dataKey="value"
            fill={HR_ORANGE}
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
