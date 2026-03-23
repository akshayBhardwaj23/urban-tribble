"use client";

import {
  AreaChart,
  Area,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  ReferenceLine,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface ForecastData {
  historical: { date: string; actual: number; predicted: number }[];
  forecast: {
    date: string;
    predicted: number;
    lower: number;
    upper: number;
  }[];
  stats: {
    trend: string;
    slope_per_period: number;
    period_type: string;
    r_squared: number;
    std_error: number;
    forecast_periods: number;
  };
}

export function ForecastChart({
  data,
  valueColumn,
}: {
  data: ForecastData;
  valueColumn: string;
}) {
  const combined = [
    ...data.historical.map((h) => ({
      date: h.date,
      actual: h.actual,
      predicted: null as number | null,
      lower: null as number | null,
      upper: null as number | null,
    })),
    ...data.forecast.map((f) => ({
      date: f.date,
      actual: null as number | null,
      predicted: f.predicted,
      lower: f.lower,
      upper: f.upper,
    })),
  ];

  const lastHistorical = data.historical[data.historical.length - 1]?.date;

  const trendLabel = data.stats.trend === "increasing" ? "↑" : data.stats.trend === "decreasing" ? "↓" : "→";

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">Trend</p>
            <p className="text-lg font-semibold mt-1">
              {trendLabel} {data.stats.trend}
            </p>
            <p className="text-xs text-muted-foreground">
              {data.stats.slope_per_period > 0 ? "+" : ""}
              {data.stats.slope_per_period.toLocaleString()} per {data.stats.period_type}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">Model Fit (R²)</p>
            <p className="text-lg font-semibold mt-1">
              {(data.stats.r_squared * 100).toFixed(1)}%
            </p>
            <p className="text-xs text-muted-foreground">
              How well the trend line fits
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">Forecast Range</p>
            <p className="text-lg font-semibold mt-1">
              {data.stats.forecast_periods} {data.stats.period_type}s
            </p>
            <p className="text-xs text-muted-foreground">
              Std error: ±{data.stats.std_error.toLocaleString()}
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">
            {valueColumn.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())} — Historical &amp; Forecast
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={combined}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v) => {
                    const d = new Date(v);
                    return d.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
                  }}
                />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip
                  labelFormatter={(v) => new Date(v as string).toLocaleDateString()}
                  formatter={(value: number, name: string) => [
                    value?.toLocaleString(undefined, { maximumFractionDigits: 0 }),
                    name,
                  ]}
                />
                <Legend />
                {lastHistorical && (
                  <ReferenceLine
                    x={lastHistorical}
                    stroke="hsl(var(--muted-foreground))"
                    strokeDasharray="3 3"
                    label={{ value: "Now", position: "top", fontSize: 11 }}
                  />
                )}
                <Area
                  type="monotone"
                  dataKey="upper"
                  stroke="none"
                  fill="hsl(220, 70%, 50%)"
                  fillOpacity={0.08}
                  name="Upper bound"
                />
                <Area
                  type="monotone"
                  dataKey="lower"
                  stroke="none"
                  fill="white"
                  fillOpacity={1}
                  name="Lower bound"
                />
                <Line
                  type="monotone"
                  dataKey="actual"
                  stroke="hsl(220, 70%, 50%)"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  name="Actual"
                  connectNulls={false}
                />
                <Line
                  type="monotone"
                  dataKey="predicted"
                  stroke="hsl(160, 60%, 45%)"
                  strokeWidth={2}
                  strokeDasharray="5 5"
                  dot={{ r: 3 }}
                  name="Forecast"
                  connectNulls={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
