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

export function AutoChart({ chart }: { chart: ChartConfig }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">{chart.title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            {renderChart(chart)}
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

function renderChart(chart: ChartConfig) {
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
          <Bar dataKey="value" radius={[4, 4, 0, 0]}>
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
          <Bar dataKey="value" fill={COLORS[0]} />
        </BarChart>
      );
  }
}

function formatTick(value: string) {
  if (value.match(/^\d{4}-\d{2}-\d{2}/)) {
    return new Date(value).toLocaleDateString("en-US", {
      month: "short",
      year: "2-digit",
    });
  }
  return value.length > 12 ? value.slice(0, 12) + "..." : value;
}

function formatNumber(value: number) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return value.toFixed(0);
}

function formatTooltip(value: number) {
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}
