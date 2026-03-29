import {
  normalizeInsightsList,
  type NormalizedInsight,
} from "@/lib/analysis-normalize";

/** Shape returned from workspace overview analysis (AI). */
export interface WorkspaceAnalysis {
  executive_summary: string;
  key_metrics: {
    label: string;
    value: string;
    trend: "up" | "down" | "stable";
    note: string;
  }[];
  insights: NormalizedInsight[];
  anomalies: { description: string; severity: "high" | "medium" | "low" }[];
  recommendations: string[];
}

export interface OverviewKpi {
  label: string;
  value: number;
  dataset_name: string;
}

function norm(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]/g, "");
}

export function parseWorkspaceAnalysis(raw: unknown): WorkspaceAnalysis | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const summary = o.executive_summary;
  if (typeof summary !== "string") return null;
  const key_metrics = Array.isArray(o.key_metrics) ? o.key_metrics : [];
  const insights = normalizeInsightsList(o.insights);
  const anomalies = Array.isArray(o.anomalies) ? o.anomalies : [];
  const recommendations = Array.isArray(o.recommendations)
    ? o.recommendations.filter((x): x is string => typeof x === "string")
    : [];
  return {
    executive_summary: summary,
    key_metrics: key_metrics.filter(isKeyMetric),
    insights,
    anomalies: anomalies.filter(isAnomaly),
    recommendations,
  };
}

function isKeyMetric(x: unknown): x is WorkspaceAnalysis["key_metrics"][0] {
  if (!x || typeof x !== "object") return false;
  const m = x as Record<string, unknown>;
  return (
    typeof m.label === "string" &&
    typeof m.value === "string" &&
    (m.trend === "up" || m.trend === "down" || m.trend === "stable")
  );
}

function isAnomaly(x: unknown): x is WorkspaceAnalysis["anomalies"][0] {
  if (!x || typeof x !== "object") return false;
  const a = x as Record<string, unknown>;
  return (
    typeof a.description === "string" &&
    (a.severity === "high" || a.severity === "medium" || a.severity === "low")
  );
}

const REV_PAT =
  /revenue|sales|income|gmv|gross|booking|turnover|topline|mrr|arr|recurring/i;
const EXP_PAT =
  /expense|cost|spend|outlay|payroll|opex|cogs|burn|payout|fee|charge/i;
const PROFIT_PAT =
  /profit|margin|net|ebit|ebitda|contribution|bottom|income\s*after/i;
const EFF_PAT =
  /efficiency|aov|conversion|rate|ratio|roi|cac|ltv|average|per\s|utilization|yield/i;

export type MetricSlotKey = "revenue" | "expenses" | "profit" | "efficiency";

export interface MetricSlot {
  key: MetricSlotKey;
  label: string;
  /** Raw numeric overview KPI if matched */
  kpi: OverviewKpi | null;
  /** Display value (from KPI number or AI metric string) */
  displayValue: string | null;
  trend: "up" | "down" | "stable" | null;
  note: string | null;
  sourceName: string | null;
}

function findAiMetricForSlot(
  slot: MetricSlotKey,
  analysis: WorkspaceAnalysis | null
): WorkspaceAnalysis["key_metrics"][0] | null {
  if (!analysis?.key_metrics.length) return null;
  const tests: Record<MetricSlotKey, RegExp> = {
    revenue: REV_PAT,
    expenses: EXP_PAT,
    profit: PROFIT_PAT,
    efficiency: EFF_PAT,
  };
  const re = tests[slot];
  return (
    analysis.key_metrics.find((m) => re.test(m.label)) ??
    analysis.key_metrics.find((m) => re.test(norm(m.label))) ??
    null
  );
}

/**
 * Map overview KPIs + AI key_metrics into fixed slots for the decision dashboard.
 */
export function buildMetricSlots(
  kpis: OverviewKpi[],
  analysis: WorkspaceAnalysis | null
): MetricSlot[] {
  const used = new Set<number>();
  const takeMatch = (re: RegExp): OverviewKpi | null => {
    for (let i = 0; i < kpis.length; i++) {
      if (used.has(i)) continue;
      if (re.test(kpis[i].label) || re.test(norm(kpis[i].label))) {
        used.add(i);
        return kpis[i];
      }
    }
    return null;
  };

  let revenueKpi = takeMatch(REV_PAT);
  if (!revenueKpi) {
    for (let i = 0; i < kpis.length; i++) {
      if (!used.has(i)) {
        used.add(i);
        revenueKpi = kpis[i];
        break;
      }
    }
  }
  const expenseKpi = takeMatch(EXP_PAT);
  const profitKpi = takeMatch(PROFIT_PAT);
  const effKpi = takeMatch(EFF_PAT);

  const slots: { key: MetricSlotKey; label: string; kpi: OverviewKpi | null }[] =
    [
      { key: "revenue", label: "Revenue", kpi: revenueKpi },
      { key: "expenses", label: "Expenses", kpi: expenseKpi },
      { key: "profit", label: "Profit or margin", kpi: profitKpi },
      { key: "efficiency", label: "Efficiency", kpi: effKpi },
    ];

  return slots.map((s) => {
    const ai = findAiMetricForSlot(s.key, analysis);
    const num =
      s.kpi != null
        ? Number(s.kpi.value).toLocaleString(undefined, {
            maximumFractionDigits: 0,
          })
        : null;
    const displayValue = num ?? ai?.value ?? null;
    const trend =
      ai?.trend === "up" || ai?.trend === "down" || ai?.trend === "stable"
        ? ai.trend
        : null;
    const note = ai?.note?.trim() || null;
    const sourceName = s.kpi?.dataset_name ?? null;
    return {
      key: s.key,
      label: s.label,
      kpi: s.kpi,
      displayValue,
      trend,
      note,
      sourceName,
    };
  });
}

export function healthHeadline(analysis: WorkspaceAnalysis | null): string {
  if (!analysis?.executive_summary?.trim()) return "";
  const t = analysis.executive_summary.trim();
  const parts = t.split(/(?<=[.!?])\s+/).filter(Boolean);
  const first = parts[0] || t;
  return first.length > 220 ? `${first.slice(0, 217)}…` : first;
}

export function keyChangeLine(analysis: WorkspaceAnalysis | null): string {
  if (!analysis) return "";
  const km = analysis.key_metrics.find(
    (m) => m.trend !== "stable" && (m.note?.trim() || m.value)
  );
  if (km) {
    const bit = km.note?.trim() || `${km.label}: ${km.value}`;
    return bit.length > 240 ? `${bit.slice(0, 237)}…` : bit;
  }
  const neutral = analysis.insights.find((i) => i.type === "neutral");
  if (neutral) {
    const bit = `${neutral.finding} — ${neutral.why_it_matters}`;
    return bit.length > 240 ? `${bit.slice(0, 237)}…` : bit;
  }
  const any = analysis.insights[0];
  if (any) {
    const bit = `${any.finding} — ${any.why_it_matters}`;
    return bit.length > 240 ? `${bit.slice(0, 237)}…` : bit;
  }
  return "";
}

export function biggestRiskLine(analysis: WorkspaceAnalysis | null): string {
  if (!analysis) return "";
  const neg = analysis.insights.find((i) => i.type === "negative");
  if (neg) {
    const bit = `${neg.finding}: ${neg.why_it_matters}`;
    return bit.length > 240 ? `${bit.slice(0, 237)}…` : bit;
  }
  const hi = analysis.anomalies.find((a) => a.severity === "high");
  if (hi) return hi.description;
  const med = analysis.anomalies.find((a) => a.severity === "medium");
  if (med) return med.description;
  const any = analysis.anomalies[0];
  return any?.description ?? "";
}

export function biggestOpportunityLine(
  analysis: WorkspaceAnalysis | null
): string {
  if (!analysis) return "";
  const pos = analysis.insights.find((i) => i.type === "positive");
  if (pos) {
    const bit = `${pos.finding}: ${pos.why_it_matters}`;
    return bit.length > 240 ? `${bit.slice(0, 237)}…` : bit;
  }
  const rec = analysis.recommendations[0];
  if (rec) return rec.length > 240 ? `${rec.slice(0, 237)}…` : rec;
  return "";
}

export function whyItMattersLine(analysis: WorkspaceAnalysis | null): string {
  if (!analysis) return "";
  const priority = analysis.insights.find(
    (i) => i.type === "negative" || i.type === "neutral"
  );
  const pick = priority ?? analysis.insights[0];
  if (!pick) return "";
  return pick.why_it_matters.trim();
}

export function whatHappenedSummary(analysis: WorkspaceAnalysis | null): string {
  if (!analysis?.executive_summary?.trim()) return "";
  return analysis.executive_summary.trim();
}

export function primaryRecommendation(
  analysis: WorkspaceAnalysis | null
): string {
  if (!analysis) return "";
  for (const ins of analysis.insights) {
    if (ins.recommended_action?.trim()) return ins.recommended_action.trim();
  }
  const r = analysis.recommendations[0];
  return r?.trim() ?? "";
}
