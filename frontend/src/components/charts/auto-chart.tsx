"use client";

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
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const CHART_LINE = "hsl(217, 91%, 59%)";
const CHART_LINE_SECONDARY = "hsl(189, 94%, 43%)";
const CHART_GRID = "hsl(220, 13%, 91%)";
const CHART_MUTED = "hsl(220, 9%, 46%)";

const COLORS = [
  CHART_LINE,
  CHART_LINE_SECONDARY,
  "hsl(291, 64%, 58%)",
  "hsl(24, 95%, 53%)",
  "hsl(142, 71%, 45%)",
  "hsl(330, 81%, 60%)",
  "hsl(43, 96%, 56%)",
  "hsl(199, 89%, 48%)",
];

const tickStyle = { fill: CHART_MUTED, fontSize: 11, fontWeight: 500 };
const axisLine = { stroke: CHART_GRID, strokeWidth: 1 };

interface ChartConfig {
  id: string;
  title: string;
  type: "line" | "bar" | "pie" | "area";
  data: Record<string, unknown>[];
  x_label?: string;
  y_label?: string;
}

/** Recharts can overflow the stack on very large series or NaN domains; cap points for safety. */
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

export function AutoChart({ chart }: { chart: ChartConfig }) {
  const prepared = prepareChart(chart);

  if (!prepared) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">{chart.title}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground py-8 text-center">
            Not enough valid numeric data to plot this chart.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">{chart.title}</CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="h-72 w-full min-h-[18rem] rounded-lg bg-gradient-to-b from-muted/20 to-transparent px-1 pb-1 pt-2">
          <ResponsiveContainer width="100%" height="100%">
            {renderChart(prepared)}
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

function renderChart(chart: PreparedChart) {
  const { type, data } = chart;

  switch (type) {
    case "line":
      return (
        <LineChart
          data={data}
          margin={{ top: 8, right: 8, left: 0, bottom: 4 }}
        >
          <CartesianGrid
            stroke={CHART_GRID}
            strokeDasharray="4 6"
            vertical={false}
            opacity={0.9}
          />
          <XAxis
            dataKey="x"
            tick={tickStyle}
            tickLine={false}
            axisLine={axisLine}
            tickFormatter={formatTick}
            tickMargin={10}
          />
          <YAxis
            tick={tickStyle}
            tickLine={false}
            axisLine={false}
            tickFormatter={formatNumber}
            width={52}
          />
          <Tooltip
            formatter={formatTooltip}
            labelFormatter={formatTick}
            contentStyle={{
              borderRadius: "10px",
              border: `1px solid ${CHART_GRID}`,
              boxShadow: "0 10px 40px -12px rgba(15, 23, 42, 0.2)",
            }}
            labelStyle={{ fontWeight: 600, marginBottom: 4 }}
          />
          <Line
            type="linear"
            dataKey="y"
            stroke={CHART_LINE}
            strokeWidth={2.5}
            dot={false}
            activeDot={{
              r: 5,
              strokeWidth: 2,
              stroke: "hsl(0, 0%, 100%)",
              fill: CHART_LINE,
            }}
            strokeLinecap="round"
            strokeLinejoin="round"
            isAnimationActive={false}
          />
        </LineChart>
      );

    case "area":
      return (
        <AreaChart
          data={data}
          margin={{ top: 8, right: 8, left: 0, bottom: 4 }}
        >
          <defs>
            <linearGradient id="areaFillPrimary" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={CHART_LINE_SECONDARY} stopOpacity={0.35} />
              <stop offset="95%" stopColor={CHART_LINE_SECONDARY} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid
            stroke={CHART_GRID}
            strokeDasharray="4 6"
            vertical={false}
            opacity={0.9}
          />
          <XAxis
            dataKey="x"
            tick={tickStyle}
            tickLine={false}
            axisLine={axisLine}
            tickFormatter={formatTick}
            tickMargin={10}
          />
          <YAxis
            tick={tickStyle}
            tickLine={false}
            axisLine={false}
            tickFormatter={formatNumber}
            width={52}
          />
          <Tooltip
            formatter={formatTooltip}
            labelFormatter={formatTick}
            contentStyle={{
              borderRadius: "10px",
              border: `1px solid ${CHART_GRID}`,
              boxShadow: "0 10px 40px -12px rgba(15, 23, 42, 0.2)",
            }}
            labelStyle={{ fontWeight: 600, marginBottom: 4 }}
          />
          <Area
            type="linear"
            dataKey="y"
            stroke={CHART_LINE_SECONDARY}
            strokeWidth={2.5}
            fill="url(#areaFillPrimary)"
            fillOpacity={1}
            dot={false}
            activeDot={{
              r: 5,
              strokeWidth: 2,
              stroke: "hsl(0, 0%, 100%)",
              fill: CHART_LINE_SECONDARY,
            }}
            strokeLinecap="round"
            strokeLinejoin="round"
            isAnimationActive={false}
          />
        </AreaChart>
      );

    case "bar":
      return (
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
          <CartesianGrid
            stroke={CHART_GRID}
            strokeDasharray="4 6"
            vertical={false}
            opacity={0.9}
          />
          <XAxis
            dataKey="name"
            tick={tickStyle}
            tickLine={false}
            axisLine={axisLine}
            tickMargin={10}
          />
          <YAxis
            tick={tickStyle}
            tickLine={false}
            axisLine={false}
            tickFormatter={formatNumber}
            width={52}
          />
          <Tooltip
            formatter={formatTooltip}
            contentStyle={{
              borderRadius: "10px",
              border: `1px solid ${CHART_GRID}`,
              boxShadow: "0 10px 40px -12px rgba(15, 23, 42, 0.2)",
            }}
          />
          <Bar dataKey="value" radius={[6, 6, 0, 0]} isAnimationActive={false}>
            {data.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      );

    case "pie":
      return (
        <PieChart margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            cx="50%"
            cy="50%"
            innerRadius={44}
            outerRadius={88}
            paddingAngle={2}
            stroke="hsl(0, 0%, 100%)"
            strokeWidth={2}
            label={({ name, percent }) =>
              `${name} (${(percent * 100).toFixed(0)}%)`
            }
            labelLine={{ stroke: CHART_GRID, strokeWidth: 1 }}
            isAnimationActive={false}
          >
            {data.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip formatter={formatTooltip} />
          <Legend />
        </PieChart>
      );

    default:
      return (
        <BarChart data={data}>
          <Bar dataKey="value" fill={COLORS[0]} isAnimationActive={false} />
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
