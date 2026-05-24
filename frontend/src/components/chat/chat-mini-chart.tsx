"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface ChatChartPayload {
  type?: string;
  title?: string;
  data?: { name: string; value: number }[];
}

function formatTooltipValue(value: unknown): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function formatValue(value: number): string {
  if (Math.abs(value) >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`;
  }
  if (Math.abs(value) >= 1_000) {
    return `${(value / 1_000).toFixed(1)}K`;
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

export function ChatMiniChart({ chart }: { chart: ChatChartPayload }) {
  const rows = (chart.data ?? []).filter(
    (r) => r.name && Number.isFinite(r.value)
  );
  if (rows.length < 2) return null;

  const height = Math.min(220, 44 + rows.length * 28);

  return (
    <div className="mt-2 w-full rounded-md border bg-background/80 p-2">
      {chart.title ? (
        <p className="mb-1.5 text-[10px] font-medium text-muted-foreground leading-snug">
          {chart.title}
        </p>
      ) : null}
      <ResponsiveContainer width="100%" height={height}>
        <BarChart
          layout="vertical"
          data={rows}
          margin={{ top: 4, right: 8, left: 4, bottom: 4 }}
        >
          <CartesianGrid
            stroke="var(--border)"
            strokeDasharray="3 4"
            horizontal={false}
          />
          <XAxis
            type="number"
            tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={formatValue}
          />
          <YAxis
            type="category"
            dataKey="name"
            width={96}
            tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            formatter={(value) => [formatTooltipValue(value), ""]}
            labelFormatter={(label) => String(label)}
            contentStyle={{
              fontSize: 11,
              borderRadius: 8,
              border: "1px solid var(--border)",
              background: "var(--card)",
            }}
          />
          <Bar
            dataKey="value"
            fill="var(--chart-1, hsl(var(--primary)))"
            radius={[0, 4, 4, 0]}
            barSize={14}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
