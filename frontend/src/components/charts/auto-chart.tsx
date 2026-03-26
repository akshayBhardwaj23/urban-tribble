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

const COLORS = [
  "hsl(220, 70%, 50%)",
  "hsl(160, 60%, 45%)",
  "hsl(30, 80%, 55%)",
  "hsl(280, 60%, 50%)",
  "hsl(0, 70%, 50%)",
  "hsl(190, 70%, 45%)",
  "hsl(45, 90%, 50%)",
  "hsl(330, 60%, 50%)",
];

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
      <CardContent>
        <div className="h-64">
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
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
          <XAxis
            dataKey="x"
            tick={{ fontSize: 11 }}
            tickFormatter={formatTick}
          />
          <YAxis tick={{ fontSize: 11 }} tickFormatter={formatNumber} />
          <Tooltip formatter={formatTooltip} labelFormatter={formatTick} />
          <Line
            type="monotone"
            dataKey="y"
            stroke={COLORS[0]}
            strokeWidth={2}
            dot={{ r: 3 }}
            isAnimationActive={false}
          />
        </LineChart>
      );

    case "area":
      return (
        <AreaChart data={data}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
          <XAxis
            dataKey="x"
            tick={{ fontSize: 11 }}
            tickFormatter={formatTick}
          />
          <YAxis tick={{ fontSize: 11 }} tickFormatter={formatNumber} />
          <Tooltip formatter={formatTooltip} labelFormatter={formatTick} />
          <Area
            type="monotone"
            dataKey="y"
            stroke={COLORS[1]}
            fill={COLORS[1]}
            fillOpacity={0.15}
            strokeWidth={2}
            isAnimationActive={false}
          />
        </AreaChart>
      );

    case "bar":
      return (
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
          <XAxis dataKey="name" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} tickFormatter={formatNumber} />
          <Tooltip formatter={formatTooltip} />
          <Bar dataKey="value" radius={[4, 4, 0, 0]} isAnimationActive={false}>
            {data.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      );

    case "pie":
      return (
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            cx="50%"
            cy="50%"
            outerRadius={80}
            label={({ name, percent }) =>
              `${name} (${(percent * 100).toFixed(0)}%)`
            }
            labelLine={true}
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
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toFixed(0);
}

function formatTooltip(value: unknown) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}
