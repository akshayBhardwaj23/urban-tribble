"use client";

import Link from "next/link";
import { useRef, useState, useMemo, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AutoChart,
  type ChartConfig,
} from "@/components/charts/auto-chart";
import { ForecastChart } from "@/components/charts/forecast-chart";
import {
  AnalysisPanel,
  type AnalysisResult,
} from "@/components/dashboard/analysis-panel";
import { ChatOverlay } from "@/components/chat/chat-panel";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace-context";
import {
  parseWorkspaceAnalysis,
  buildMetricSlots,
  healthHeadline,
  keyChangeLine,
  biggestRiskLine,
  biggestOpportunityLine,
  whatHappenedSummary,
  whyItMattersLine,
  primaryRecommendation,
  type WorkspaceAnalysis,
} from "@/lib/overview-briefing";
import { buildWorkspaceAiTraceContext } from "@/lib/traceability";
import { buildWorkspaceMetricSlotDetails } from "@/lib/kpi-drill-down";
import {
  WORKSPACE_BRIEFING_EMPTY_TILES,
  WORKSPACE_NO_BRIEFING_YET,
  WORKSPACE_OPERATOR_READ_BUSY,
  WORKSPACE_OPERATOR_READ_EMPTY,
  workspaceRunBriefingInvite,
} from "@/lib/analysis-fallback-copy";
import { KpiDetailsSheet } from "@/components/dashboard/kpi-details-sheet";
import { WhatChangedSection } from "@/components/dashboard/what-changed-section";
import { LatestSummaryCard } from "@/components/dashboard/latest-summary-card";
import { AlertsSignalsSection } from "@/components/dashboard/alerts-signals-section";
import { RecommendedActionsSection } from "@/components/dashboard/recommended-actions-section";
import { WorkspaceUsageStrip } from "@/components/dashboard/workspace-usage-strip";

function formatWorkspaceActivity(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(d);
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
      {children}
    </h2>
  );
}

function BriefTile({
  title,
  body,
  variant = "default",
  emptyHint,
}: {
  title: string;
  body: string;
  variant?: "default" | "risk" | "opportunity";
  emptyHint?: string;
}) {
  const border =
    variant === "risk"
      ? "border-amber-200/80 bg-amber-50/40 dark:border-amber-900/40 dark:bg-amber-950/20"
      : variant === "opportunity"
        ? "border-emerald-200/80 bg-emerald-50/35 dark:border-emerald-900/40 dark:bg-emerald-950/20"
        : "border-slate-200/80 bg-white/70 dark:border-slate-800 dark:bg-slate-950/30";
  const showEmpty = !body.trim();

  return (
    <div
      className={`rounded-2xl border px-5 py-4 shadow-sm backdrop-blur-sm ${border}`}
    >
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
        {title}
      </p>
      <p
        className={`mt-2 text-sm leading-relaxed ${
          showEmpty ? "text-slate-400" : "text-slate-800 dark:text-slate-100"
        }`}
      >
        {showEmpty ? emptyHint ?? "—" : body}
      </p>
    </div>
  );
}

function TrendBadge({ trend }: { trend: "up" | "down" | "stable" | null }) {
  if (trend === "up") {
    return (
      <span className="inline-flex items-center gap-0.5 text-xs font-medium text-emerald-700 dark:text-emerald-400">
        <span aria-hidden>↑</span> Up
      </span>
    );
  }
  if (trend === "down") {
    return (
      <span className="inline-flex items-center gap-0.5 text-xs font-medium text-red-600 dark:text-red-400">
        <span aria-hidden>↓</span> Down
      </span>
    );
  }
  return (
    <span className="text-xs font-medium text-slate-400">Steady</span>
  );
}

export default function OverviewPage() {
  const { activeWorkspace, loading: workspaceLoading } = useWorkspace();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [appendTarget, setAppendTarget] = useState<{
    id: string;
    name: string;
  } | null>(null);
  /** Steps forward at inferred frequency (day / week / month); max 366 on API. */
  const [outlookPeriods, setOutlookPeriods] = useState(90);

  const overviewEnabled =
    !workspaceLoading && Boolean(activeWorkspace?.id);

  const {
    data,
    isPending,
    isFetching,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["overview", activeWorkspace?.id ?? "none"],
    queryFn: () => api.getOverview(),
    enabled: overviewEnabled,
  });

  /** True while the overview request is actively in flight (not when the query is disabled). */
  const overviewLoading = overviewEnabled && isPending && isFetching;

  const overviewAnalysis = useQuery({
    queryKey: ["overview-analysis", activeWorkspace?.id ?? "none"],
    queryFn: () => api.getOverviewAnalysis(),
    enabled: overviewEnabled,
  });

  const runOverviewAnalysis = useMutation({
    mutationFn: () => api.runOverviewAnalysis(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["overview-analysis"] });
      queryClient.invalidateQueries({ queryKey: ["workspace-timeline"] });
    },
  });

  const forecastMutation = useMutation({
    mutationFn: () => api.runOverviewForecast(outlookPeriods),
  });

  useEffect(() => {
    forecastMutation.reset();
  }, [activeWorkspace?.id, forecastMutation.reset]);

  const appendMutation = useMutation({
    mutationFn: ({ datasetId, file }: { datasetId: string; file: File }) =>
      api.appendToDataset(datasetId, file),
    onSuccess: () => {
      setAppendTarget(null);
      queryClient.invalidateQueries({ queryKey: ["overview"] });
      queryClient.invalidateQueries({ queryKey: ["overview-analysis"] });
      queryClient.invalidateQueries({ queryKey: ["summaries-latest"] });
      queryClient.invalidateQueries({ queryKey: ["workspace-timeline"] });
    },
  });

  const handleAppendFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && appendTarget) {
      appendMutation.mutate({ datasetId: appendTarget.id, file });
    }
    e.target.value = "";
  };

  const analysis = useMemo((): WorkspaceAnalysis | null => {
    const raw = overviewAnalysis.data?.result_json;
    return parseWorkspaceAnalysis(raw);
  }, [overviewAnalysis.data?.result_json]);

  const metricSlots = useMemo(() => {
    if (!data?.kpis) return buildMetricSlots([], analysis);
    return buildMetricSlots(data.kpis, analysis);
  }, [data?.kpis, analysis]);

  const workspaceAiTraceContext = useMemo(
    () =>
      buildWorkspaceAiTraceContext({
        datasets: data?.datasets ?? [],
        totalRows: data?.total_rows ?? 0,
      }),
    [data?.datasets, data?.total_rows]
  );

  if (workspaceLoading) {
    return (
      <div className="space-y-10 max-w-6xl">
        <Skeleton className="h-9 w-64" />
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-2xl" />
          ))}
        </div>
        <Skeleton className="h-48 rounded-2xl" />
      </div>
    );
  }

  if (!activeWorkspace?.id) {
    return (
      <div className="space-y-6 max-w-6xl">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
            Overview
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Pick a workspace in the sidebar to load this view.
          </p>
        </div>
        <Card className="border-slate-200/80 shadow-sm">
          <CardContent className="flex flex-col items-center justify-center py-14 text-center">
            <p className="text-sm text-muted-foreground mb-4 max-w-md">
              No workspace is selected. Choose one from the menu above, or create a workspace if
              you are just getting started.
            </p>
            <p className="text-xs text-muted-foreground">
              If you just signed in, a quick refresh can help the list load.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (overviewLoading) {
    return (
      <div className="space-y-10 max-w-6xl">
        <Skeleton className="h-9 w-64" />
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-2xl" />
          ))}
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-32 rounded-2xl" />
          ))}
        </div>
        <Skeleton className="h-48 rounded-2xl" />
        <div className="grid gap-5 md:grid-cols-2">
          {Array.from({ length: 2 }).map((_, i) => (
            <Skeleton key={i} className="h-72 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="space-y-6 max-w-6xl">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
            Overview
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            This overview could not be loaded.
          </p>
        </div>
        <Card className="border-destructive/30 shadow-sm">
          <CardContent className="py-8 space-y-4">
            <p className="text-sm text-destructive">
              {error instanceof Error ? error.message : "Request failed"}
            </p>
            <p className="text-xs text-muted-foreground">
              Check that the API is running and you are still signed in. If you switched
              workspaces, try once more.
            </p>
            <Button type="button" size="sm" onClick={() => refetch()}>
              Retry
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!data || data.total_datasets === 0) {
    const emptyHints = data?.habit_hints;
    const emptyUpdated = formatWorkspaceActivity(emptyHints?.last_activity_at);
    return (
      <div className="space-y-6 max-w-6xl">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
            Overview
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            What moved, what it may imply, and what to do next—across your sources.
          </p>
          {emptyHints && (
            <div className="mt-3 space-y-1.5 text-xs text-muted-foreground max-w-xl leading-relaxed">
              {emptyUpdated && (
                <p>
                  <span className="font-medium text-slate-600 dark:text-slate-400">
                    Last updated
                  </span>
                  {" · "}
                  {emptyUpdated}
                </p>
              )}
              <p>{emptyHints.next_check_suggestion}</p>
              {emptyHints.gentle_nudge ? (
                <p className="text-slate-500 dark:text-slate-500">{emptyHints.gentle_nudge}</p>
              ) : null}
            </div>
          )}
        </div>
        <WorkspaceUsageStrip usage={data?.usage} className="max-w-6xl" />
        <Card className="border-slate-200/80 shadow-sm">
          <CardContent className="flex flex-col items-center justify-center py-14 text-center">
            <p className="text-sm text-muted-foreground mb-4 max-w-md">
              Import a file to see net position, what moved, downside and upside, and charts
              that support the read.
            </p>
            <Link
              href="/upload"
              className="inline-flex h-9 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              Import data
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  const health = healthHeadline(analysis);
  const keyChange = keyChangeLine(analysis);
  const risk = biggestRiskLine(analysis);
  const opportunity = biggestOpportunityLine(analysis);
  const happened = whatHappenedSummary(analysis);
  const matters = whyItMattersLine(analysis);
  const action = primaryRecommendation(analysis);
  const analysisReady = !!analysis;
  const analysisBusy =
    overviewAnalysis.isLoading || runOverviewAnalysis.isPending;

  const noInsightCopy = WORKSPACE_NO_BRIEFING_YET;
  const habits = data.habit_hints;
  const lastUpdatedLabel = formatWorkspaceActivity(habits?.last_activity_at);

  return (
    <div className="space-y-10 max-w-6xl pb-10">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
            Overview
          </h1>
          <p className="text-sm text-muted-foreground mt-1.5 leading-relaxed">
            {data.total_datasets} source{data.total_datasets !== 1 ? "s" : ""}{" "}
            · {data.total_rows.toLocaleString()} rows · Briefing first, then charts
          </p>
          {habits && (
            <div className="mt-3 space-y-1.5 max-w-2xl">
              {lastUpdatedLabel ? (
                <p className="text-xs text-slate-600 dark:text-slate-400">
                  <span className="font-semibold text-slate-700 dark:text-slate-300">
                    Last updated
                  </span>
                  {" · "}
                  <time dateTime={habits.last_activity_at ?? undefined}>
                    {lastUpdatedLabel}
                  </time>
                </p>
              ) : null}
              {habits.activity_nudge ? (
                <p className="text-xs text-slate-600 dark:text-slate-400 leading-snug">
                  {habits.activity_nudge}
                </p>
              ) : null}
              <p className="text-xs text-muted-foreground leading-relaxed">
                <span className="font-medium text-slate-600 dark:text-slate-400">
                  Next check
                </span>
                {" · "}
                {habits.next_check_suggestion}
              </p>
              {habits.gentle_nudge ? (
                <p className="text-xs text-muted-foreground/90 leading-relaxed">
                  {habits.gentle_nudge}
                </p>
              ) : null}
            </div>
          )}
        </div>
        <div className="flex flex-col gap-2 shrink-0 sm:items-end">
          <div className="flex flex-wrap items-center gap-2 justify-end">
            {data.datasets.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                className="rounded-lg"
                onClick={() => {
                  const ds = data.datasets[0];
                  setAppendTarget({ id: ds.id, name: ds.name });
                }}
              >
                Add rows
              </Button>
            )}
            <Link href="/history">
              <Button size="sm" variant="outline" className="rounded-lg">
                History
              </Button>
            </Link>
            <Link href="/upload">
              <Button size="sm" className="rounded-lg">
                Import data
              </Button>
            </Link>
            <Button
              size="sm"
              variant="secondary"
              className="rounded-lg"
              onClick={() => runOverviewAnalysis.mutate()}
              disabled={analysisBusy}
            >
              {runOverviewAnalysis.isPending
                ? "Running briefing…"
                : analysisReady
                  ? "Re-run briefing"
                  : "Run workspace briefing"}
            </Button>
          </div>
          {habits?.briefing_cta_context ? (
            <p className="text-[11px] text-muted-foreground sm:text-right max-w-md sm:max-w-[18rem] leading-snug">
              <span className="font-medium text-slate-600 dark:text-slate-400">
                Briefing
              </span>
              {" · "}
              {habits.briefing_cta_context}
            </p>
          ) : null}
        </div>
      </header>

      <WorkspaceUsageStrip usage={data.usage} className="max-w-6xl" />

      <LatestSummaryCard className="max-w-6xl" />

      <AlertsSignalsSection
        alerts={data.alerts ?? []}
        briefingReady={analysisReady}
        className="max-w-6xl"
      />

      <RecommendedActionsSection
        items={data.recommended_actions ?? []}
        briefingAvailable={analysisReady}
        onRunBriefing={() => runOverviewAnalysis.mutate()}
        briefingBusy={analysisBusy}
        className="max-w-6xl"
      />

      <WhatChangedSection block={data.what_changed} className="max-w-6xl" />

      {/* 1. Top summary */}
      <section className="space-y-3">
        <SectionLabel>Snapshot</SectionLabel>
        {analysisBusy && !analysisReady ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-28 rounded-2xl" />
            ))}
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <BriefTile
              title="Net position"
              body={health}
              emptyHint={noInsightCopy}
            />
            <BriefTile
              title="Main shift"
              body={keyChange}
              emptyHint={
                analysisReady
                  ? WORKSPACE_BRIEFING_EMPTY_TILES.keyChange
                  : noInsightCopy
              }
            />
            <BriefTile
              title="Largest downside"
              body={risk}
              variant="risk"
              emptyHint={
                analysisReady
                  ? WORKSPACE_BRIEFING_EMPTY_TILES.risk
                  : noInsightCopy
              }
            />
            <BriefTile
              title="Largest upside"
              body={opportunity}
              variant="opportunity"
              emptyHint={
                analysisReady
                  ? WORKSPACE_BRIEFING_EMPTY_TILES.upside
                  : noInsightCopy
              }
            />
          </div>
        )}
      </section>

      {/* 2. Important metrics */}
      <section className="space-y-3">
        <SectionLabel>Key numbers</SectionLabel>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {metricSlots.map((slot) => (
            <div
              key={slot.key}
              className="rounded-2xl border border-slate-200/80 bg-white/80 px-5 py-4 shadow-sm backdrop-blur-sm dark:border-slate-800 dark:bg-slate-950/40"
            >
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                {slot.label}
              </p>
              {slot.displayValue ? (
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-50 tabular-nums">
                  {slot.displayValue}
                </p>
              ) : (
                <p className="mt-2 text-lg text-slate-400">No match yet</p>
              )}
              <div className="mt-3 flex items-center justify-between gap-2 border-t border-slate-100 pt-3 dark:border-slate-800">
                <span className="text-[11px] text-slate-500">Direction</span>
                <TrendBadge trend={slot.trend} />
              </div>
              {slot.note && (
                <p className="mt-2 text-xs text-slate-500 leading-snug line-clamp-2">
                  {slot.note}
                </p>
              )}
              {slot.sourceName && (
                <p className="mt-2 text-[11px] text-slate-400">
                  Source · {slot.sourceName}
                </p>
              )}
              <div className="mt-3 border-t border-slate-100 pt-2 dark:border-slate-800">
                <KpiDetailsSheet
                  metricLabel={slot.label}
                  details={buildWorkspaceMetricSlotDetails({
                    label: slot.label,
                    sourceName: slot.sourceName,
                    note: slot.note,
                    totalRowsWorkspace: data.total_rows,
                    totalDatasets: data.total_datasets,
                  })}
                />
              </div>
            </div>
          ))}
          <div className="rounded-2xl border border-slate-200/80 bg-white/80 px-5 py-4 shadow-sm backdrop-blur-sm dark:border-slate-800 dark:bg-slate-950/40">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
              Record volume
            </p>
            <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-50 tabular-nums">
              {data.total_rows.toLocaleString()}
            </p>
            <div className="mt-3 flex items-center justify-between gap-2 border-t border-slate-100 pt-3 dark:border-slate-800">
              <span className="text-[11px] text-slate-500">Sources</span>
              <span className="text-xs font-medium text-slate-600 dark:text-slate-300">
                {data.total_datasets} source
                {data.total_datasets !== 1 ? "s" : ""}
              </span>
            </div>
            <p className="mt-2 text-[11px] text-slate-400">
              Total rows across this workspace
            </p>
            <div className="mt-3 border-t border-slate-100 pt-2 dark:border-slate-800">
              <KpiDetailsSheet
                metricLabel="Record volume"
                details={buildWorkspaceMetricSlotDetails({
                  label: "Record volume",
                  sourceName: null,
                  note: "Sum of row_count from all datasets in this workspace.",
                  totalRowsWorkspace: data.total_rows,
                  totalDatasets: data.total_datasets,
                })}
              />
            </div>
          </div>
        </div>
        <p className="text-xs text-slate-400 max-w-2xl">
          Titles follow your column names. Expense and profit slots fill when those fields exist
          or when the latest briefing names them.
        </p>
      </section>

      {/* 3. Leadership briefing */}
      <section className="space-y-3">
        <SectionLabel>Operator summary</SectionLabel>
        <div className="rounded-2xl border border-slate-200/80 bg-white/85 shadow-sm backdrop-blur-sm dark:border-slate-800 dark:bg-slate-950/40 overflow-hidden">
          <div className="grid divide-y divide-slate-100 dark:divide-slate-800 lg:grid-cols-3 lg:divide-y-0 lg:divide-x">
            <div className="p-6 lg:p-7">
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                What moved
              </p>
              <p className="mt-3 text-sm leading-relaxed text-slate-800 dark:text-slate-100">
                {analysisReady && happened ? (
                  happened
                ) : (
                  <span className="text-slate-400">
                    {analysisBusy
                      ? WORKSPACE_OPERATOR_READ_BUSY.whatMoved
                      : workspaceRunBriefingInvite(data.total_datasets)}
                  </span>
                )}
              </p>
            </div>
            <div className="p-6 lg:p-7 bg-slate-50/50 dark:bg-slate-900/20">
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                So what
              </p>
              <p className="mt-3 text-sm leading-relaxed text-slate-800 dark:text-slate-100">
                {analysisReady && matters ? (
                  matters
                ) : (
                  <span className="text-slate-400">
                    {analysisBusy
                      ? WORKSPACE_OPERATOR_READ_BUSY.soWhat
                      : WORKSPACE_OPERATOR_READ_EMPTY.soWhat}
                  </span>
                )}
              </p>
            </div>
            <div className="p-6 lg:p-7">
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                Lead move
              </p>
              <p className="mt-3 text-sm leading-relaxed text-slate-800 dark:text-slate-100 font-medium">
                {analysisReady && action ? (
                  action
                ) : (
                  <span className="text-slate-400 font-normal">
                    {analysisBusy
                      ? WORKSPACE_OPERATOR_READ_BUSY.leadMove
                      : WORKSPACE_OPERATOR_READ_EMPTY.leadMove}
                  </span>
                )}
              </p>
            </div>
          </div>
          {runOverviewAnalysis.isError && (
            <p className="px-6 py-3 text-sm text-destructive border-t border-slate-100 dark:border-slate-800">
              {runOverviewAnalysis.error.message}
            </p>
          )}
        </div>
      </section>

      {/* 4. Charts */}
      <section className="space-y-3">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <SectionLabel>Charts</SectionLabel>
            <p className="text-sm text-slate-500 mt-1 max-w-xl">
              Supporting views for the briefing above. Open a source for filters and row-level
              detail.
            </p>
          </div>
        </div>
        {data.charts.length > 0 ? (
          <div className="flex flex-col gap-6 w-full">
            {data.charts.map(
              (
                chart: {
                  id: string;
                  dataset_name?: string;
                  title: string;
                  type: ChartConfig["type"];
                  data: ChartConfig["data"];
                  x_label?: string;
                  y_label?: string;
                },
                i: number
              ) => (
                <div key={chart.id} className="space-y-2">
                  <AutoChart chart={chart} accentIndex={i} />
                  {chart.dataset_name && (
                    <p className="text-xs font-medium text-slate-500">
                      Source · {chart.dataset_name}
                    </p>
                  )}
                </div>
              )
            )}
          </div>
        ) : (
          <Card className="border-dashed border-slate-200 bg-slate-50/50 dark:bg-slate-900/20">
            <CardContent className="py-10 text-center text-sm text-muted-foreground">
              No charts yet from your sources. Ensure date and numeric columns
              are detected, or open a source to adjust the schema.
            </CardContent>
          </Card>
        )}
      </section>

      {/* Planning + sources (secondary) — outlook full width so the chart reads clearly */}
      <section className="space-y-3">
        <SectionLabel>Outlook & sources</SectionLabel>
        <div className="flex flex-col gap-6">
          <div className="rounded-2xl border border-slate-200/80 bg-white/70 p-6 md:p-8 shadow-sm dark:border-slate-800 dark:bg-slate-950/30 w-full">
            <h3 className="text-sm font-semibold text-slate-900">Outlook</h3>
            <p className="text-xs text-slate-500 mt-1 mb-2 leading-relaxed max-w-3xl">
              Directional linear projection—not a forecast of record.{" "}
              <span className="text-slate-600 dark:text-slate-400">
                Workspace outlook uses the{" "}
                <strong className="font-medium text-slate-800 dark:text-slate-200">
                  source with the most rows
                </strong>{" "}
                that has both a date column and a revenue-style numeric column,
                then the{" "}
                <strong className="font-medium text-slate-800 dark:text-slate-200">
                  first date
                </strong>{" "}
                and{" "}
                <strong className="font-medium text-slate-800 dark:text-slate-200">
                  first numeric measure
                </strong>{" "}
                from that file&apos;s schema. To model a different column or
                file, open that data source and use Forecast there.
              </span>
            </p>

            <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end mb-5 md:mb-6">
              <div className="space-y-1.5">
                <label
                  htmlFor="outlook-horizon"
                  className="text-[11px] font-semibold uppercase tracking-wide text-slate-500"
                >
                  Horizon
                </label>
                <select
                  id="outlook-horizon"
                  className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-800 shadow-sm dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 min-w-[11rem]"
                  value={outlookPeriods}
                  onChange={(e) => setOutlookPeriods(Number(e.target.value))}
                >
                  <option value={30}>30 periods</option>
                  <option value={90}>90 periods</option>
                  <option value={180}>180 periods</option>
                  <option value={365}>365 periods</option>
                </select>
                <p className="text-[11px] text-slate-400 max-w-xs leading-snug">
                  Each period matches your data spacing (day, week, or month).
                </p>
              </div>
              <Button
                size="sm"
                variant="outline"
                className="rounded-lg shrink-0"
                onClick={() => forecastMutation.mutate()}
                disabled={forecastMutation.isPending}
              >
                {forecastMutation.isPending
                  ? "Generating..."
                  : forecastMutation.data
                    ? "Regenerate outlook"
                    : "Generate outlook"}
              </Button>
            </div>

            {forecastMutation.isError && (
              <p className="text-sm text-destructive mb-4">
                {forecastMutation.error.message}
              </p>
            )}

            {forecastMutation.data ? (
              <div className="space-y-4">
                <div className="rounded-xl border border-slate-100 bg-slate-50/80 px-4 py-3 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-900/30 dark:text-slate-300">
                  <p className="font-medium text-slate-800 dark:text-slate-100">
                    What this chart uses
                  </p>
                  <p className="mt-1 leading-relaxed">
                    <span className="font-medium">
                      {forecastMutation.data.value_column.replace(/_/g, " ")}
                    </span>
                    {" · "}
                    timeline{" "}
                    <span className="font-medium">
                      {forecastMutation.data.date_column.replace(/_/g, " ")}
                    </span>
                    {" · "}
                    file{" "}
                    <span className="font-medium">
                      {forecastMutation.data.dataset_name}
                    </span>
                  </p>
                  <p className="mt-2 text-slate-500 dark:text-slate-400">
                    Showing{" "}
                    <span className="font-medium text-slate-700 dark:text-slate-200">
                      {forecastMutation.data.stats.forecast_periods}
                    </span>{" "}
                    future {forecastMutation.data.stats.period_type}
                    {forecastMutation.data.stats.forecast_periods === 1
                      ? ""
                      : "s"}
                    .
                  </p>
                </div>
                <ForecastChart
                  data={forecastMutation.data}
                  valueColumn={forecastMutation.data.value_column}
                  chartHeightClassName="min-h-[16rem] h-[min(34rem,52vh)] sm:min-h-[20rem]"
                />
              </div>
            ) : null}
          </div>

          <div className="rounded-2xl border border-slate-200/80 bg-white/70 p-6 shadow-sm dark:border-slate-800 dark:bg-slate-950/30 w-full lg:max-w-xl">
            <h3 className="text-sm font-semibold text-slate-900">Sources</h3>
            <p className="text-xs text-slate-500 mt-1 mb-4">
              Open a source for preview, briefing detail, or to add rows.
            </p>
            <ul className="space-y-2">
              {data.datasets.map((ds) => (
                <li key={ds.id}>
                  <div className="flex items-center justify-between gap-2 rounded-xl border border-transparent px-2 py-2 hover:border-slate-200 hover:bg-white/80 dark:hover:border-slate-700 dark:hover:bg-slate-900/40 transition-colors">
                    <Link
                      href={`/datasets/${ds.id}`}
                      className="flex-1 min-w-0"
                    >
                      <p className="text-sm font-medium text-slate-900 truncate">
                        {ds.name}
                      </p>
                      <p className="text-[11px] text-slate-500">
                        {ds.row_count?.toLocaleString()} rows ·{" "}
                        {ds.column_count} cols ·{" "}
                        {new Date(ds.created_at).toLocaleDateString()}
                      </p>
                    </Link>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="shrink-0 text-xs"
                      onClick={() =>
                        setAppendTarget({ id: ds.id, name: ds.name })
                      }
                    >
                      Add rows
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* Full analysis (optional depth) */}
      {analysisReady && overviewAnalysis.data?.result_json && (
        <details className="group rounded-2xl border border-slate-200/60 bg-slate-50/40 dark:border-slate-800 dark:bg-slate-900/20">
          <summary className="cursor-pointer list-none px-5 py-4 text-sm font-medium text-slate-700 dark:text-slate-200 flex items-center justify-between">
            <span>Full briefing</span>
            <span className="text-slate-400 text-xs group-open:rotate-180 transition-transform">
              ▾
            </span>
          </summary>
          <div className="px-5 pb-6 pt-0 border-t border-slate-200/60 dark:border-slate-800">
            <div className="pt-4 flex justify-end">
              <Button
                variant="outline"
                size="sm"
                className="rounded-lg mb-4"
                onClick={() => runOverviewAnalysis.mutate()}
                disabled={runOverviewAnalysis.isPending}
              >
                {runOverviewAnalysis.isPending
                  ? "Running…"
                  : "Re-run briefing"}
              </Button>
            </div>
            <AnalysisPanel
              result={overviewAnalysis.data!.result_json as AnalysisResult}
              traceContext={workspaceAiTraceContext}
            />
          </div>
        </details>
      )}

      <Dialog
        open={!!appendTarget}
        onOpenChange={(open) => !open && setAppendTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add rows · {appendTarget?.name}</DialogTitle>
          </DialogHeader>
          {data.datasets.length > 1 && (
            <div className="space-y-1">
              <label className="text-sm font-medium">Source</label>
              <select
                className="w-full rounded-md border px-3 py-2 text-sm"
                value={appendTarget?.id ?? ""}
                onChange={(e) => {
                  const ds = data.datasets.find(
                    (d: { id: string; name: string }) => d.id === e.target.value
                  );
                  if (ds) setAppendTarget({ id: ds.id, name: ds.name });
                }}
              >
                {data.datasets.map((ds: { id: string; name: string }) => (
                  <option key={ds.id} value={ds.id}>
                    {ds.name}
                  </option>
                ))}
              </select>
            </div>
          )}
          <p className="text-sm text-muted-foreground">
            Upload a file with the same columns to append rows. Duplicates are removed
            automatically.
          </p>
          {appendMutation.isError && (
            <p className="text-sm text-destructive">
              {appendMutation.error.message}
            </p>
          )}
          {appendMutation.isSuccess && (
            <p className="text-sm text-green-600">
              Rows added. {appendMutation.data.row_count} total rows in this source.
            </p>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.tsv,.xlsx,.xls"
            className="hidden"
            onChange={handleAppendFile}
          />
          <div className="flex justify-end gap-2 mt-2">
            <Button
              variant="outline"
              onClick={() => setAppendTarget(null)}
              disabled={appendMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              onClick={() => fileInputRef.current?.click()}
              disabled={appendMutation.isPending}
            >
              {appendMutation.isPending ? "Adding…" : "Choose file"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <ChatOverlay datasets={data.datasets} />
    </div>
  );
}
