"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export interface AnalysisResult {
  executive_summary: string;
  key_metrics: {
    label: string;
    value: string;
    trend: "up" | "down" | "stable";
    note: string;
  }[];
  insights: {
    title: string;
    description: string;
    type: "positive" | "negative" | "neutral";
  }[];
  anomalies: {
    description: string;
    severity: "high" | "medium" | "low";
  }[];
  recommendations: string[];
}

const TREND_ICONS: Record<string, string> = {
  up: "↑",
  down: "↓",
  stable: "→",
};

const INSIGHT_STYLES: Record<string, string> = {
  positive: "border-l-green-500",
  negative: "border-l-red-500",
  neutral: "border-l-blue-500",
};

const SEVERITY_VARIANT: Record<string, "default" | "secondary" | "destructive"> = {
  high: "destructive",
  medium: "default",
  low: "secondary",
};

export function AnalysisPanel({ result }: { result: AnalysisResult }) {
  return (
    <div className="space-y-4">
      {/* Executive Summary */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Executive read</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm leading-relaxed">{result.executive_summary}</p>
        </CardContent>
      </Card>

      {/* Key Metrics */}
      {result.key_metrics.length > 0 && (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {result.key_metrics.map((metric, i) => (
            <Card key={i}>
              <CardContent className="pt-4">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  {metric.label}
                </p>
                <div className="flex items-baseline gap-2 mt-1">
                  <p className="text-xl font-semibold">{metric.value}</p>
                  <span
                    className={`text-sm ${
                      metric.trend === "up"
                        ? "text-green-600"
                        : metric.trend === "down"
                          ? "text-red-500"
                          : "text-muted-foreground"
                    }`}
                  >
                    {TREND_ICONS[metric.trend] || ""}
                  </span>
                </div>
                {metric.note && (
                  <p className="text-xs text-muted-foreground mt-1">
                    {metric.note}
                  </p>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Insights */}
      {result.insights.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Signal & narrative</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {result.insights.map((insight, i) => (
              <div
                key={i}
                className={`border-l-2 pl-3 ${INSIGHT_STYLES[insight.type] || INSIGHT_STYLES.neutral}`}
              >
                <p className="text-sm font-medium">{insight.title}</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {insight.description}
                </p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Anomalies */}
      {result.anomalies.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Exceptions & outliers</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {result.anomalies.map((anomaly, i) => (
              <div key={i} className="flex items-start gap-2">
                <Badge variant={SEVERITY_VARIANT[anomaly.severity] || "secondary"} className="text-xs shrink-0 mt-0.5">
                  {anomaly.severity}
                </Badge>
                <p className="text-sm">{anomaly.description}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Recommendations */}
      {result.recommendations.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Recommended next steps</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {result.recommendations.map((rec, i) => (
                <li key={i} className="text-sm flex items-start gap-2">
                  <span className="text-primary mt-0.5 shrink-0">{i + 1}.</span>
                  {rec}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
