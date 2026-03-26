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
          <div className="h-80 rounded-lg bg-gradient-to-b from-muted/20 to-transparent px-1 pb-1 pt-2">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={combined} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
                <CartesianGrid
                  stroke="hsl(220, 13%, 91%)"
                  strokeDasharray="4 6"
                  vertical={false}
                  opacity={0.9}
                />
                <XAxis
                  dataKey="date"
                  tick={{ fill: "hsl(220, 9%, 46%)", fontSize: 11, fontWeight: 500 }}
                  tickLine={false}
                  axisLine={{ stroke: "hsl(220, 13%, 91%)", strokeWidth: 1 }}
                  tickMargin={10}
                  tickFormatter={(v) => {
                    const d = new Date(v);
                    return d.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
                  }}
                />
                <YAxis
                  tick={{ fill: "hsl(220, 9%, 46%)", fontSize: 11, fontWeight: 500 }}
                  tickLine={false}
                  axisLine={false}
                  width={52}
                  tickFormatter={(v) =>
                    Number(v).toLocaleString(undefined, {
                      notation: "standard",
                      maximumFractionDigits: Number(v) >= 100 ? 0 : 2,
                    })
                  }
                />
                <Tooltip
                  labelFormatter={(v) => new Date(v as string).toLocaleDateString()}
                  formatter={(value: number, name: string) => [
                    value != null
                      ? Number(value).toLocaleString(undefined, {
                          notation: "standard",
                          maximumFractionDigits: 2,
                        })
                      : "—",
                    name,
                  ]}
                  contentStyle={{
                    borderRadius: "10px",
                    border: "1px solid hsl(220, 13%, 91%)",
                    boxShadow: "0 10px 40px -12px rgba(15, 23, 42, 0.2)",
                  }}
                />
                <Legend />
                {lastHistorical && (
                  <ReferenceLine
                    x={lastHistorical}
                    stroke="hsl(220, 13%, 71%)"
                    strokeDasharray="4 4"
                    label={{ value: "Now", position: "top", fontSize: 11 }}
                  />
                )}
                <Area
                  type="linear"
                  dataKey="upper"
                  stroke="none"
                  fill="hsl(217, 91%, 59%)"
                  fillOpacity={0.1}
                  name="Upper bound"
                  isAnimationActive={false}
                />
                <Area
                  type="linear"
                  dataKey="lower"
                  stroke="none"
                  fill="hsl(0, 0%, 100%)"
                  fillOpacity={1}
                  name="Lower bound"
                  isAnimationActive={false}
                />
                <Line
                  type="linear"
                  dataKey="actual"
                  stroke="hsl(217, 91%, 59%)"
                  strokeWidth={2.5}
                  dot={false}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  name="Actual"
                  connectNulls={false}
                  isAnimationActive={false}
                  activeDot={{ r: 5, strokeWidth: 2, stroke: "#fff", fill: "hsl(217, 91%, 59%)" }}
                />
                <Line
                  type="linear"
                  dataKey="predicted"
                  stroke="hsl(189, 94%, 43%)"
                  strokeWidth={2.5}
                  strokeDasharray="6 5"
                  dot={false}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  name="Forecast"
                  connectNulls={false}
                  isAnimationActive={false}
                  activeDot={{ r: 5, strokeWidth: 2, stroke: "#fff", fill: "hsl(189, 94%, 43%)" }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
