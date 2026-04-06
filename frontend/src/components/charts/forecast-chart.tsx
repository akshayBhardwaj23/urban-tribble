"use client";

import { cn } from "@/lib/utils";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  ReferenceLine,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartFrame } from "@/components/charts/chart-frame";
import {
  formatChartAxisDate,
  formatChartTooltipDate,
} from "@/lib/chart-dates";

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

function mean(nums: number[]): number {
  if (!nums.length) return NaN;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

function formatInsightNum(n: number): string {
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString(undefined, {
    notation: "standard",
    maximumFractionDigits: 2,
  });
}

function forecastPeriodInsight(
  data: ForecastData,
  label: string
): { line1: string; line2?: string } | null {
  const hist = data.historical;
  if (hist.length < 2) return null;

  const n = hist.length;
  const w = Math.max(1, Math.min(14, Math.floor(n / 3)));
  const recentVals = hist.slice(Math.max(0, n - w)).map((h) => h.actual);
  const priorVals = hist
    .slice(Math.max(0, n - 2 * w), Math.max(0, n - w))
    .map((h) => h.actual);
  const curAvg = mean(recentVals);
  const prevAvg =
    priorVals.length >= 1 ? mean(priorVals) : hist[0]!.actual;

  const eps =
    1e-9 * Math.max(1, Math.abs(curAvg), Math.abs(prevAvg));

  let line1: string;
  if (!Number.isFinite(curAvg) || !Number.isFinite(prevAvg)) {
    line1 = `Could not summarize recent change for ${label}.`;
  } else if (Math.abs(prevAvg) < eps && Math.abs(curAvg) < eps) {
    line1 = `${label} was effectively flat in recent history vs the prior window.`;
  } else if (Math.abs(prevAvg) < eps) {
    line1 = `${label} rose in the latest historical stretch after a very small prior average.`;
  } else {
    const pct = ((curAvg - prevAvg) / Math.abs(prevAvg)) * 100;
    if (Math.abs(pct) < 0.5) {
      line1 = `${label} was nearly unchanged in recent history vs the prior comparable window.`;
    } else if (pct > 0) {
      line1 = `${label} increased by ${pct.toFixed(0)}% in recent history vs the previous period.`;
    } else {
      line1 = `${label} decreased by ${Math.abs(pct).toFixed(0)}% in recent history vs the previous period.`;
    }
  }

  const parts: string[] = [
    `Recent average ${formatInsightNum(curAvg)} vs ${formatInsightNum(prevAvg)} in the prior window.`,
  ];

  const lastActual = hist[n - 1]!.actual;
  const firstFc = data.forecast[0]?.predicted;
  if (
    data.forecast.length > 0 &&
    Number.isFinite(lastActual) &&
    Number.isFinite(firstFc) &&
    Math.abs(lastActual) > eps
  ) {
    const fwd = ((firstFc - lastActual) / Math.abs(lastActual)) * 100;
    parts.push(
      `First forecast step is about ${Math.abs(fwd).toFixed(0)}% ${fwd >= 0 ? "above" : "below"} the latest actual.`
    );
  }

  return { line1, line2: parts.join(" ") };
}

export function ForecastChart({
  data,
  valueColumn,
  chartHeightClassName = "h-80",
}: {
  data: ForecastData;
  valueColumn: string;
  /** Tailwind height classes for the plot area (default h-80). */
  chartHeightClassName?: string;
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

  const gradActual = "fcActualGrad";
  const gradPred = "fcPredGrad";
  const gradBand = "fcBandGrad";

  const metricLabel = valueColumn
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
  const chartInsight = forecastPeriodInsight(data, metricLabel);
  const fcN = combined.length;
  const fcCompact = fcN > 0 && fcN <= 14;
  const fcInterval = fcCompact ? 0 : Math.max(1, Math.ceil(fcN / 8) - 1);
  const fcBottom = fcCompact ? 10 : 22;
  const fcMinGap = fcCompact ? 4 : 12;
  const fcTick = fcCompact
    ? { fill: "hsl(220, 9%, 46%)", fontSize: 11, fontWeight: 500 }
    : {
        fill: "hsl(220, 9%, 46%)",
        fontSize: 11,
        fontWeight: 500,
        angle: -32,
        textAnchor: "end" as const,
      };

  return (
    <div className="space-y-4">
      <div className="grid w-full gap-4 md:grid-cols-3">
        <Card className="dashboard-surface dashboard-inner-accent border-white/70 bg-white/78 dark:border-white/10 dark:bg-slate-950/45">
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
        <Card className="dashboard-surface border-white/70 bg-white/78 dark:border-white/10 dark:bg-slate-950/45">
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
        <Card className="dashboard-surface border-white/70 bg-white/78 dark:border-white/10 dark:bg-slate-950/45">
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

      <Card className="dashboard-surface dashboard-inner-accent overflow-hidden border-white/70 bg-white/78 dark:border-white/10 dark:bg-slate-950/45">
        <CardHeader className="border-b border-white/65 pb-5 dark:border-white/10">
          <CardTitle className="text-sm font-medium">
            {metricLabel} — Historical & forecast
          </CardTitle>
          {chartInsight ? (
            <div className="mt-3 space-y-1.5">
              <p className="text-[13px] font-medium leading-snug text-foreground">
                {chartInsight.line1}
              </p>
              {chartInsight.line2 ? (
                <p className="text-xs leading-relaxed text-muted-foreground">
                  {chartInsight.line2}
                </p>
              ) : null}
            </div>
          ) : null}
        </CardHeader>
        <CardContent>
          <div
            className={cn(
              "rounded-[1.6rem] bg-[linear-gradient(180deg,rgba(255,255,255,0.76),rgba(255,255,255,0.42))] px-2 pb-2 pt-3 dark:bg-[linear-gradient(180deg,rgba(30,41,59,0.48),rgba(15,23,42,0.14))]",
              chartHeightClassName
            )}
          >
            <ChartFrame className="h-full" minHeight={320}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={combined}
                  margin={{
                    top: 8,
                    right: 8,
                    left: 0,
                    bottom: fcBottom,
                  }}
                >
                <defs>
                  <linearGradient id={gradActual} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id={gradPred} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#f472b6" stopOpacity={0.28} />
                    <stop offset="100%" stopColor="#f472b6" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id={gradBand} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#a78bfa" stopOpacity={0.18} />
                    <stop offset="100%" stopColor="#a78bfa" stopOpacity={0.04} />
                  </linearGradient>
                </defs>
                <CartesianGrid
                  stroke="rgba(148, 163, 184, 0.18)"
                  strokeDasharray="4 6"
                  vertical={false}
                  opacity={0.9}
                />
                <XAxis
                  dataKey="date"
                  tick={fcTick}
                  tickLine={false}
                  axisLine={{ stroke: "hsl(220, 13%, 91%)", strokeWidth: 1 }}
                  tickMargin={8}
                  tickFormatter={(v) => formatChartAxisDate(v)}
                  interval={fcInterval}
                  minTickGap={fcMinGap}
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
                  labelFormatter={(v) => formatChartTooltipDate(v)}
                  formatter={(value, name) => [
                    value != null && value !== ""
                      ? Number(value).toLocaleString(undefined, {
                          notation: "standard",
                          maximumFractionDigits: 2,
                        })
                      : "—",
                    String(name ?? ""),
                  ]}
                  contentStyle={{
                    borderRadius: "16px",
                    border: "1px solid rgba(255,255,255,0.82)",
                    background: "rgba(252,248,243,0.96)",
                    boxShadow: "0 24px 60px -20px rgba(15, 23, 42, 0.16)",
                  }}
                />
                <Legend
                  verticalAlign="bottom"
                  align="center"
                  wrapperStyle={{ paddingTop: 10 }}
                />
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
                  fill={`url(#${gradBand})`}
                  fillOpacity={1}
                  name="Upper bound"
                  isAnimationActive={false}
                />
                <Area
                  type="linear"
                  dataKey="lower"
                  stroke="none"
                  fill="rgba(255,255,255,0.9)"
                  fillOpacity={1}
                  name="Lower bound"
                  isAnimationActive={false}
                />
                <Area
                  type="monotone"
                  dataKey="actual"
                  stroke="#06b6d4"
                  strokeWidth={2.5}
                  fill={`url(#${gradActual})`}
                  fillOpacity={1}
                  dot={false}
                  name="Actual"
                  connectNulls={false}
                  isAnimationActive={false}
                  activeDot={{ r: 5, strokeWidth: 2, stroke: "#fff", fill: "#06b6d4" }}
                />
                <Area
                  type="monotone"
                  dataKey="predicted"
                  stroke="#ec4899"
                  strokeWidth={2.5}
                  strokeDasharray="6 5"
                  fill={`url(#${gradPred})`}
                  fillOpacity={1}
                  dot={false}
                  name="Forecast"
                  connectNulls={false}
                  isAnimationActive={false}
                  activeDot={{ r: 5, strokeWidth: 2, stroke: "#fff", fill: "#ec4899" }}
                />
                </AreaChart>
              </ResponsiveContainer>
            </ChartFrame>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
