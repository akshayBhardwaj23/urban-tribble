"use client";

import { useMemo } from "react";
import { AlertTriangle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  INSIGHT_PAY_ATTENTION_FALLBACK,
  INSIGHT_SOURCE_FALLBACK,
  INSIGHT_UNGRADED_CONFIDENCE,
} from "@/lib/analysis-fallback-copy";
import {
  insightContextLine,
  normalizeInsightsList,
  parseInsightTraceSlice,
  sortInsightsForDisplay,
  type ConfidenceBand,
  type NormalizedInsight,
} from "@/lib/analysis-normalize";
import {
  buildTopPriorities,
  lensAccentClass,
  lensLabel,
  priorityBadgeClass,
  type TopPriorityItem,
} from "@/lib/top-priorities";
import { cn } from "@/lib/utils";
import {
  mergeInsightTrace,
  type AnalysisTraceContext,
  type InsightTraceSlice,
} from "@/lib/traceability";
import {
  TraceCollapsible,
  TraceVerifyDialog,
} from "@/components/trust/analysis-trace";
import {
  CONFIDENCE_TONE_LEGEND,
  confidenceToneCardLine,
} from "@/lib/confidence-tone";

/** API payload; `insights` may be legacy or structured (normalized at render). */
export interface AnalysisResult {
  executive_summary: string;
  key_metrics: {
    label: string;
    value: string;
    trend: "up" | "down" | "stable";
    note: string;
    /** Optional per-metric provenance from the model */
    trace?: InsightTraceSlice;
  }[];
  insights: unknown[];
  anomalies: {
    description: string;
    severity: "high" | "medium" | "low";
  }[];
  recommendations: string[];
  /** Optional 3–5 rows from the model; merged with heuristics when sparse. */
  top_priorities?: unknown[];
}

const TREND_ICONS: Record<string, string> = {
  up: "↑",
  down: "↓",
  stable: "→",
};

const SEVERITY_VARIANT: Record<string, "default" | "secondary" | "destructive"> =
  {
    high: "destructive",
    medium: "default",
    low: "secondary",
  };

function SectionHeading({
  children,
  hint,
}: {
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="mb-4">
      <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
        {children}
      </h3>
      {hint ? (
        <p className="mt-1 text-xs text-slate-400 leading-relaxed max-w-2xl">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

function polarityLabel(t: NormalizedInsight["type"]): string {
  if (t === "negative") return "Downside";
  if (t === "positive") return "Upside";
  return "Context";
}

function polarityBar(t: NormalizedInsight["type"]): string {
  if (t === "negative") return "bg-red-500";
  if (t === "positive") return "bg-emerald-500";
  return "bg-slate-400";
}

function confidenceMeterFilled(level: ConfidenceBand): number {
  if (level === "high") return 3;
  if (level === "medium") return 2;
  if (level === "low") return 1;
  return 0;
}

function confidenceShortLabel(level: ConfidenceBand): string {
  switch (level) {
    case "high":
      return "High";
    case "medium":
      return "Medium";
    case "low":
      return "Low";
    default:
      return "Not graded";
  }
}

function confidenceAriaLabel(level: ConfidenceBand): string {
  switch (level) {
    case "high":
      return "Conviction: high";
    case "medium":
      return "Conviction: medium";
    case "low":
      return "Conviction: low";
    default:
      return "Conviction: not graded";
  }
}

function InsightConfidenceMeter({ level }: { level: ConfidenceBand }) {
  const filled = confidenceMeterFilled(level);
  return (
    <div
      className="flex w-[3.35rem] shrink-0 gap-0.5"
      role="img"
      aria-label={confidenceAriaLabel(level)}
    >
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className={cn(
            "h-1 min-w-0 flex-1 rounded-full transition-colors",
            i < filled
              ? level === "low"
                ? "bg-slate-500/80 dark:bg-slate-400/85"
                : level === "medium"
                  ? "bg-amber-500/70 dark:bg-amber-400/60"
                  : "bg-emerald-600/70 dark:bg-emerald-400/65"
              : "bg-slate-200 dark:bg-slate-700/95"
          )}
        />
      ))}
    </div>
  );
}

function InsightCaveatsBlock({
  caveats,
  emphasize,
}: {
  caveats: string[];
  emphasize: boolean;
}) {
  if (caveats.length === 0) return null;
  return (
    <div
      className={cn(
        "rounded-xl border px-3 py-2.5",
        emphasize
          ? "border-amber-200/75 bg-amber-50/45 dark:border-amber-900/50 dark:bg-amber-950/30"
          : "border-slate-100/90 bg-slate-50/50 dark:border-slate-800 dark:bg-slate-900/30"
      )}
    >
      <div className="flex items-start gap-2">
        <AlertTriangle
          className={cn(
            "mt-0.5 h-3.5 w-3.5 shrink-0",
            emphasize
              ? "text-amber-700/80 dark:text-amber-400/90"
              : "text-slate-400 dark:text-slate-500"
          )}
          aria-hidden
        />
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-slate-500 dark:text-slate-400">
            Validate before you act
          </p>
          <ul className="mt-1.5 space-y-1 text-xs leading-snug text-slate-600 dark:text-slate-300">
            {caveats.map((c, i) => (
              <li key={i} className="pl-0.5">
                {c}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

function TopPrioritiesBlock({
  items,
  traceContext,
}: {
  items: TopPriorityItem[];
  traceContext?: AnalysisTraceContext | null;
}) {
  if (items.length === 0) return null;

  return (
    <section
      className="rounded-2xl border border-slate-200/80 bg-gradient-to-b from-slate-50/95 via-white to-white shadow-sm ring-1 ring-slate-900/[0.03] dark:border-slate-800 dark:from-slate-900/50 dark:via-slate-950/80 dark:to-slate-950 dark:ring-white/[0.04]"
      aria-label="Priorities"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200/70 px-4 py-3 dark:border-slate-800/80">
        <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
          Priorities
        </h3>
        {traceContext ? (
          <TraceVerifyDialog
            context={traceContext}
            title="What this list draws on"
            extraHeadline="Same scope as the findings below."
            triggerLabel="Scope"
            size="sm"
          />
        ) : null}
      </div>
      <ul className="divide-y divide-slate-100 dark:divide-slate-800/90">
        {items.map((item, i) => (
          <li key={`${item.kind}-${i}`} className="flex gap-0">
            <div
              className={cn(
                "w-1 shrink-0 self-stretch rounded-l-[0.65rem] sm:rounded-l-xl",
                lensAccentClass(item.kind)
              )}
              aria-hidden
            />
            <div className="min-w-0 flex-1 px-3.5 py-3.5 sm:px-4 sm:py-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                  {lensLabel(item.kind)}
                </span>
                <Badge
                  variant="outline"
                  className={cn(
                    "h-5 border px-1.5 text-[9px] font-semibold uppercase tracking-wide",
                    priorityBadgeClass(item.priority)
                  )}
                >
                  {item.priority}
                </Badge>
              </div>
              <p className="mt-2 text-sm font-semibold leading-snug tracking-tight text-slate-900 dark:text-slate-50">
                {item.title}
              </p>
              <p className="mt-1.5 text-xs leading-snug text-slate-600 dark:text-slate-300">
                {item.explanation}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function InsightCard({
  insight,
  index,
  parentTrace,
}: {
  insight: NormalizedInsight;
  index: number;
  parentTrace?: AnalysisTraceContext | null;
}) {
  const verifyContext =
    mergeInsightTrace(parentTrace ?? null, insight.trace) ??
    parentTrace ??
    null;

  const caveatEmphasis =
    insight.caveats.length > 0 &&
    (insight.confidence_level === "low" ||
      insight.confidence_level === "medium" ||
      insight.confidence_level === "unknown");

  const contextLine = insightContextLine(insight.headline, insight.finding);
  const watchLine =
    insight.recommended_action?.trim() || INSIGHT_PAY_ATTENTION_FALLBACK;

  return (
    <article className="relative overflow-hidden rounded-xl border border-slate-200/90 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-slate-800 dark:bg-slate-950/40">
      <div
        className={`absolute left-0 top-0 h-full w-1 ${polarityBar(insight.type)}`}
        aria-hidden
      />
      <div className="pl-5 pr-5 py-4 sm:pl-5 sm:pr-5">
        <div className="flex flex-wrap items-center justify-between gap-2 gap-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-mono text-slate-400 tabular-nums">
              {String(index + 1).padStart(2, "0")}
            </span>
            <Badge
              variant="outline"
              className="h-5 text-[9px] font-semibold uppercase tracking-wide border-slate-200/90 text-slate-600 dark:text-slate-400"
            >
              {polarityLabel(insight.type)}
            </Badge>
          </div>
          <div className="flex items-start gap-2">
            <InsightConfidenceMeter level={insight.confidence_level} />
            <div className="min-w-0">
              <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400 dark:text-slate-500">
                Conviction · {confidenceShortLabel(insight.confidence_level)}
              </span>
              <p className="mt-0.5 text-[10px] leading-snug text-slate-500 dark:text-slate-400 max-w-[16rem] sm:max-w-xs">
                {confidenceToneCardLine(insight.confidence_level)}
              </p>
            </div>
          </div>
        </div>

        <h3 className="mt-3 text-[15px] font-semibold leading-snug tracking-tight text-slate-900 dark:text-slate-50 pr-1">
          {insight.headline}
        </h3>

        {contextLine ? (
          <p className="mt-2 text-sm leading-snug text-slate-600 dark:text-slate-300">
            {contextLine}
          </p>
        ) : null}

        <div className="mt-3 rounded-lg border border-slate-100/90 bg-slate-50/50 px-3 py-2.5 dark:border-slate-800/80 dark:bg-slate-900/20">
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
            Implication
          </p>
          <p className="mt-1 text-sm leading-snug text-slate-800 dark:text-slate-100">
            {insight.why_it_matters}
          </p>
        </div>

        <div className="mt-3 flex gap-2">
          <span
            className="mt-0.5 text-slate-400 text-xs font-semibold shrink-0"
            aria-hidden
          >
            →
          </span>
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
              Next
            </p>
            <p className="mt-0.5 text-sm font-medium leading-snug text-slate-900 dark:text-slate-50">
              {watchLine}
            </p>
            {insight.likely_cause?.trim() ? (
              <p className="mt-1.5 text-xs leading-snug text-slate-500 dark:text-slate-400">
                <span className="font-medium text-slate-600 dark:text-slate-300">
                  Hypothesis:{" "}
                </span>
                {insight.likely_cause.trim()}
              </p>
            ) : null}
          </div>
        </div>

        <details className="group mt-4 rounded-lg border border-slate-100 dark:border-slate-800 open:border-slate-200/90 dark:open:border-slate-700">
          <summary className="cursor-pointer list-none px-3 py-2 text-left text-[11px] font-medium text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 [&::-webkit-details-marker]:hidden flex items-center justify-between gap-2">
            <span>Evidence & limits</span>
            <span className="text-slate-400 text-[10px] transition-transform group-open:rotate-180">
              ▾
            </span>
          </summary>
          <div className="space-y-3 border-t border-slate-100 px-3 py-3 dark:border-slate-800">
            {insight.confidence_rationale ? (
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                  Conviction note
                </p>
                <p className="mt-1 text-xs leading-snug text-slate-600 dark:text-slate-300 m-0">
                  {insight.confidence_rationale}
                </p>
              </div>
            ) : insight.confidence_level === "unknown" &&
              !insight.confidence?.trim() ? (
              <p className="text-xs text-slate-500 dark:text-slate-400 leading-snug m-0">
                {INSIGHT_UNGRADED_CONFIDENCE}
              </p>
            ) : null}

            <InsightCaveatsBlock
              caveats={insight.caveats}
              emphasize={caveatEmphasis}
            />

            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                Figures
              </p>
              <p className="mt-1 text-xs font-mono text-slate-600 dark:text-slate-400 wrap-break-word m-0">
                {insight.source_reference?.trim() || (
                  <span className="text-slate-400 font-sans">{INSIGHT_SOURCE_FALLBACK}</span>
                )}
              </p>
            </div>
            {verifyContext ? (
              <div className="flex justify-end pt-1">
                <TraceVerifyDialog
                  context={verifyContext}
                  title="Basis for this brief"
                  extraHeadline={`${insight.headline} · ${polarityLabel(insight.type)}`}
                  triggerLabel="View basis"
                  size="sm"
                />
              </div>
            ) : null}
          </div>
        </details>
      </div>
    </article>
  );
}

export function AnalysisPanel({
  result,
  traceContext,
}: {
  result: AnalysisResult;
  /** Dataset or workspace scope for collapsible + verification dialogs */
  traceContext?: AnalysisTraceContext | null;
}) {
  const executive_summary =
    typeof result.executive_summary === "string"
      ? result.executive_summary
      : "";
  const key_metrics = Array.isArray(result.key_metrics) ? result.key_metrics : [];
  const rawInsights = Array.isArray(result.insights) ? result.insights : [];
  const anomalies = Array.isArray(result.anomalies) ? result.anomalies : [];
  const recommendations = Array.isArray(result.recommendations)
    ? result.recommendations.filter((x): x is string => typeof x === "string")
    : [];

  const insights = sortInsightsForDisplay(normalizeInsightsList(rawInsights));

  const topPriorities = useMemo(
    () =>
      buildTopPriorities({
        executive_summary,
        insights: Array.isArray(result.insights) ? result.insights : [],
        anomalies: Array.isArray(result.anomalies) ? result.anomalies : [],
        recommendations: Array.isArray(result.recommendations)
          ? result.recommendations.filter(
              (x): x is string => typeof x === "string"
            )
          : [],
        top_priorities: result.top_priorities,
      }),
    [
      executive_summary,
      result.insights,
      result.anomalies,
      result.recommendations,
      result.top_priorities,
    ]
  );

  return (
    <div className="space-y-10 max-w-4xl">
      <header className="border-b border-slate-200/80 pb-5 dark:border-slate-800">
        <h2 className="text-lg font-semibold tracking-tight text-slate-900 dark:text-slate-50">
          Briefing
        </h2>
        <p className="mt-1 text-sm text-slate-500 leading-snug">
          Downsides first, then context, then upside. Favor ties to revenue, margin, concentration,
          and risk; when the file is thin, the copy below says what to validate next.
        </p>

        <details className="group mt-4 rounded-lg border border-slate-200/80 bg-slate-50/40 dark:border-slate-800 dark:bg-slate-900/25">
          <summary className="cursor-pointer list-none px-4 py-2.5 text-left text-xs font-medium text-slate-600 hover:text-slate-800 dark:text-slate-300 dark:hover:text-slate-100 [&::-webkit-details-marker]:hidden flex items-center justify-between gap-2">
            <span>Why conviction changes the wording</span>
            <span className="text-slate-400 text-[10px] transition-transform group-open:rotate-180 shrink-0">
              ▾
            </span>
          </summary>
          <div className="border-t border-slate-200/70 dark:border-slate-800 px-4 py-3 space-y-2.5">
            <p className="text-[11px] leading-snug text-slate-500 dark:text-slate-400 m-0">
              Each signal carries a conviction label so the tone matches how strong the evidence
              is—no false confidence when the extract is thin.
            </p>
            <ul className="space-y-2 m-0 pl-0 list-none">
              {CONFIDENCE_TONE_LEGEND.map((row) => (
                <li
                  key={row.band}
                  className="text-[11px] leading-snug text-slate-600 dark:text-slate-300"
                >
                  <span className="font-semibold text-slate-700 dark:text-slate-200">
                    {row.title}
                  </span>
                  {" — "}
                  {row.body}
                </li>
              ))}
            </ul>
          </div>
        </details>
      </header>

      {traceContext ? (
        <TraceCollapsible
          context={traceContext}
          summaryHint={traceContext.scopeSubtitle ?? traceContext.sourceFiles[0]?.name}
        />
      ) : null}

      <TopPrioritiesBlock items={topPriorities} traceContext={traceContext} />

      <section>
        <SectionHeading hint="One or two sentences: net position and whether to act, wait, or dig deeper—specific to this scope, not generic praise.">
          Bottom line
        </SectionHeading>
        <div className="rounded-2xl border border-slate-200/90 bg-slate-50/60 px-5 py-4 dark:border-slate-800 dark:bg-slate-900/30">
          <p className="text-sm leading-snug text-slate-800 dark:text-slate-100">
            {executive_summary}
          </p>
        </div>
      </section>

      {key_metrics.length > 0 ? (
        <section>
          <SectionHeading hint="Confirm definitions (gross vs net, cash vs accrual) before these figures drive spend or headcount.">
            Key figures
          </SectionHeading>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {key_metrics.map((metric, i) => {
              const metricTrace = parseInsightTraceSlice(metric.trace);
              const figureCtx =
                mergeInsightTrace(traceContext ?? null, metricTrace) ??
                traceContext ??
                null;
              return (
                <div
                  key={i}
                  className="rounded-xl border border-slate-200/80 bg-white px-4 py-3 shadow-sm dark:border-slate-800 dark:bg-slate-950/40"
                >
                  <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                    {metric.label}
                  </p>
                  <div className="mt-1 flex items-baseline gap-2">
                    <p className="text-xl font-semibold tabular-nums text-slate-900 dark:text-slate-50">
                      {metric.value}
                    </p>
                    <span
                      className={`text-sm ${
                        metric.trend === "up"
                          ? "text-emerald-600"
                          : metric.trend === "down"
                            ? "text-red-600"
                            : "text-slate-400"
                      }`}
                    >
                      {TREND_ICONS[metric.trend] || ""}
                    </span>
                  </div>
                  {metric.note ? (
                    <p className="mt-2 text-xs text-slate-500 leading-snug">
                      {metric.note}
                    </p>
                  ) : null}
                  {figureCtx ? (
                    <div className="mt-3 border-t border-slate-100 pt-2 dark:border-slate-800">
                      <TraceVerifyDialog
                        context={figureCtx}
                        title="Figure basis"
                        extraHeadline={metric.label}
                        triggerLabel="See basis"
                        size="sm"
                      />
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

      {insights.length > 0 ? (
        <section>
          <SectionHeading hint="Short operator brief per card: context, implication, next step. Conviction steers how direct the language is; open Evidence & limits for rationale and figures.">
            Signals
          </SectionHeading>
          <div className="space-y-5">
            {insights.map((insight, i) => (
              <InsightCard
                key={i}
                insight={insight}
                index={i}
                parentTrace={traceContext}
              />
            ))}
          </div>
        </section>
      ) : null}

      {anomalies.length > 0 ? (
        <section>
          <SectionHeading hint="Skew, gaps, or duplication that could misstate revenue, cost, or risk—fix or footnote before you lock the plan.">
            Quality flags
          </SectionHeading>
          <div className="rounded-2xl border border-amber-200/80 bg-amber-50/40 px-5 py-4 dark:border-amber-900/50 dark:bg-amber-950/20">
            <ul className="space-y-3">
              {anomalies.map((anomaly, i) => (
                <li key={i} className="flex items-start gap-3">
                  <Badge
                    variant={
                      SEVERITY_VARIANT[anomaly.severity] || "secondary"
                    }
                    className="text-[10px] shrink-0 mt-0.5 uppercase"
                  >
                    {anomaly.severity}
                  </Badge>
                  <p className="text-sm leading-snug text-slate-800 dark:text-slate-100">
                    {anomaly.description}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}

      {recommendations.length > 0 ? (
        <section>
          <SectionHeading hint="Cross-cutting moves that still need an owner if they are not already covered above.">
            Open items
          </SectionHeading>
          <ol className="list-none space-y-3 rounded-2xl border border-slate-200/80 bg-white p-5 dark:border-slate-800 dark:bg-slate-950/30">
            {recommendations.map((rec, i) => (
              <li
                key={i}
                className="flex gap-3 text-sm leading-snug text-slate-700 dark:text-slate-200"
              >
                <span className="font-mono text-xs text-slate-400 tabular-nums w-6 shrink-0">
                  {i + 1}.
                </span>
                <span>{rec}</span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}
    </div>
  );
}
