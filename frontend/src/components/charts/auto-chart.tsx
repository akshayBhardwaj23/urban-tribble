"use client";

import type { CSSProperties } from "react";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { cn } from "@/lib/utils";

/** HR / admin dashboard palette: sunset orange, electric blue, soft purple, teal */
const HR_ORANGE = "#FF7A45";
const HR_BLUE = "#4F7CFF";
const HR_PURPLE = "#9B7EDE";
const HR_TEAL = "#3ECFC0";
const HR_PINK = "#F472B6";
const HR_AMBER = "#FBBF24";

const BAR_PALETTE = [HR_ORANGE, HR_BLUE, HR_TEAL, HR_PURPLE, HR_PINK, HR_AMBER];

const CHART_GRID = "rgba(148, 163, 184, 0.35)";
const CHART_MUTED = "#64748b";

const tickStyle = {
  fill: CHART_MUTED,
  fontSize: 11,
  fontWeight: 600,
};

export interface ChartConfig {
  id: string;
  title: string;
  type: "line" | "bar" | "pie" | "area";
  data: Record<string, unknown>[];
  x_label?: string;
  y_label?: string;
}

const MAX_LINE_AREA_POINTS = 2_000;
const MAX_BAR_POINTS = 120;
const MAX_PIE_SLICES = 24;

function downsampleOrdered<T>(points: T[], max: number): T[] {
  if (points.length <= max) return points;
  const out: T[] = [];
  for (let i = 0; i < max; i++) {
    const idx = Math.floor((i / (max - 1)) * (points.length - 1));
    out.push(points[idx]);
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
  return downsampleOrdered(rows, MAX_LINE_AREA_POINTS);
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
  | { type: "line"; data: { x: string; y: number }[] }
  | { type: "area"; data: { x: string; y: number }[] }
  | { type: "bar"; data: { name: string; value: number }[] }
  | { type: "pie"; data: { name: string; value: number }[] };

function prepareChart(chart: ChartConfig): PreparedChart | null {
  switch (chart.type) {
    case "line": {
      const data = sanitizeLineAreaData(chart.data);
      return data.length ? { type: "line", data } : null;
    }
    case "area": {
      const data = sanitizeLineAreaData(chart.data);
      return data.length ? { type: "area", data } : null;
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

function tooltipBoxStyle(): CSSProperties {
  return {
    borderRadius: 16,
    border: "1px solid rgba(255,255,255,0.9)",
    boxShadow:
      "0 14px 40px -12px rgba(99, 102, 241, 0.2), 0 8px 20px -8px rgba(15, 23, 42, 0.12)",
    background: "rgba(255,255,255,0.95)",
    backdropFilter: "blur(8px)",
  };
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
  const lineStroke = accentIndex % 2 === 0 ? HR_ORANGE : HR_BLUE;
  const areaStroke = accentIndex % 2 === 0 ? HR_TEAL : HR_PURPLE;

  if (!prepared) {
    return (
      <div
        className={cn(
          "flex flex-col rounded-3xl border border-white/70 bg-white/75 p-6",
          "shadow-[0_8px_32px_-12px_rgba(99,102,241,0.1)] backdrop-blur-xl"
        )}
      >
        <h3 className="text-sm font-semibold text-slate-700">{chart.title}</h3>
        <p className="mt-4 text-center text-sm text-slate-500">
          Not enough valid numeric data to plot this chart.
        </p>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex flex-col overflow-hidden rounded-3xl border border-white/70 bg-white/75",
        "shadow-[0_8px_32px_-12px_rgba(91,76,255,0.12),0_4px_20px_-8px_rgba(15,23,42,0.06)]",
        "backdrop-blur-xl transition-shadow duration-300 hover:shadow-[0_14px_40px_-12px_rgba(91,76,255,0.16)]"
      )}
    >
      <div className="border-b border-slate-200/40 px-5 pb-3 pt-5">
        <h3 className="text-[13px] font-bold uppercase tracking-[0.06em] text-slate-500">
          {chart.title}
        </h3>
      </div>
      <div className="h-72 w-full min-h-[18rem] px-3 pb-4 pt-3">
        <ResponsiveContainer width="100%" height="100%">
          {renderChart(prepared, safeId, lineStroke, areaStroke)}
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function renderChart(
  chart: PreparedChart,
  safeId: string,
  lineStroke: string,
  areaStroke: string
) {
  const { type, data } = chart;

  switch (type) {
    case "line":
      return (
        <LineChart
          data={data}
          margin={{ top: 12, right: 12, left: 4, bottom: 8 }}
        >
          <defs>
            <filter
              id={`lineGlow-${safeId}`}
              x="-40%"
              y="-40%"
              width="180%"
              height="180%"
            >
              <feGaussianBlur stdDeviation="2.5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          <CartesianGrid
            stroke={CHART_GRID}
            strokeDasharray="6 8"
            vertical={false}
          />
          <XAxis
            dataKey="x"
            tick={tickStyle}
            tickLine={false}
            axisLine={{ stroke: CHART_GRID }}
            tickFormatter={formatTick}
            tickMargin={12}
          />
          <YAxis
            tick={tickStyle}
            tickLine={false}
            axisLine={false}
            tickFormatter={formatNumber}
            width={56}
          />
          <Tooltip
            formatter={formatTooltip}
            labelFormatter={formatTick}
            contentStyle={tooltipBoxStyle()}
            labelStyle={{ fontWeight: 700, marginBottom: 6, color: "#334155" }}
          />
          <Line
            type="monotone"
            dataKey="y"
            stroke={lineStroke}
            strokeWidth={3}
            dot={false}
            activeDot={{
              r: 6,
              strokeWidth: 3,
              stroke: "#fff",
              fill: lineStroke,
            }}
            strokeLinecap="round"
            strokeLinejoin="round"
            filter={`url(#lineGlow-${safeId})`}
            isAnimationActive={false}
          />
        </LineChart>
      );

    case "area":
      return (
        <AreaChart
          data={data}
          margin={{ top: 12, right: 12, left: 4, bottom: 8 }}
        >
          <defs>
            <linearGradient id={`areaGrad-${safeId}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={areaStroke} stopOpacity={0.45} />
              <stop offset="55%" stopColor={HR_BLUE} stopOpacity={0.12} />
              <stop offset="100%" stopColor={HR_PURPLE} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid
            stroke={CHART_GRID}
            strokeDasharray="6 8"
            vertical={false}
          />
          <XAxis
            dataKey="x"
            tick={tickStyle}
            tickLine={false}
            axisLine={{ stroke: CHART_GRID }}
            tickFormatter={formatTick}
            tickMargin={12}
          />
          <YAxis
            tick={tickStyle}
            tickLine={false}
            axisLine={false}
            tickFormatter={formatNumber}
            width={56}
          />
          <Tooltip
            formatter={formatTooltip}
            labelFormatter={formatTick}
            contentStyle={tooltipBoxStyle()}
            labelStyle={{ fontWeight: 700, marginBottom: 6, color: "#334155" }}
          />
          <Area
            type="monotone"
            dataKey="y"
            stroke={areaStroke}
            strokeWidth={3}
            fill={`url(#areaGrad-${safeId})`}
            fillOpacity={1}
            dot={false}
            activeDot={{
              r: 6,
              strokeWidth: 3,
              stroke: "#fff",
              fill: areaStroke,
            }}
            strokeLinecap="round"
            strokeLinejoin="round"
            isAnimationActive={false}
          />
        </AreaChart>
      );

    case "bar":
      return (
        <BarChart
          layout="vertical"
          data={data}
          margin={{ top: 8, right: 28, left: 8, bottom: 8 }}
        >
          <CartesianGrid
            stroke={CHART_GRID}
            strokeDasharray="6 8"
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
            contentStyle={tooltipBoxStyle()}
          />
          <Bar
            dataKey="value"
            barSize={14}
            radius={[0, 12, 12, 0]}
            isAnimationActive={false}
          >
            {data.map((_, i) => (
              <Cell key={i} fill={BAR_PALETTE[i % BAR_PALETTE.length]} />
            ))}
          </Bar>
        </BarChart>
      );

    case "pie":
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
            paddingAngle={3}
            cornerRadius={6}
            stroke="rgba(255,255,255,0.95)"
            strokeWidth={3}
            label={({ name, percent }) =>
              `${String(name).slice(0, 10)}${String(name).length > 10 ? "…" : ""} ${(((percent ?? 0) as number) * 100).toFixed(0)}%`
            }
            labelLine={{
              stroke: CHART_GRID,
              strokeWidth: 1,
            }}
            isAnimationActive={false}
          >
            {data.map((_, i) => (
              <Cell
                key={i}
                fill={BAR_PALETTE[i % BAR_PALETTE.length]}
                opacity={0.92}
              />
            ))}
          </Pie>
          <Tooltip formatter={formatTooltip} contentStyle={tooltipBoxStyle()} />
          <Legend
            wrapperStyle={{ fontSize: 11, fontWeight: 600, color: CHART_MUTED }}
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

function formatTick(value: unknown) {
  const s = String(value ?? "");
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) {
    return new Date(s).toLocaleDateString("en-US", {
      month: "short",
      year: "2-digit",
    });
  }
  return s.length > 12 ? s.slice(0, 12) + "..." : s;
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
