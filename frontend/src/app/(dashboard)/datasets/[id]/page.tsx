"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { AutoChart } from "@/components/charts/auto-chart";
import { DashboardKpiTile } from "@/components/dashboard/kpi-tile";
import { ForecastChart } from "@/components/charts/forecast-chart";
import {
  AnalysisPanel,
  type AnalysisResult,
} from "@/components/dashboard/analysis-panel";
import {
  TimeframeToolbar,
  type TimeframeValue,
} from "@/components/dashboard/timeframe-toolbar";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace-context";
import {
  buildDatasetAiTraceContext,
  buildDatasetDashboardTraceContext,
} from "@/lib/traceability";
import { TraceCollapsible } from "@/components/trust/analysis-trace";
import {
  buildHeuristicKpiDetails,
  buildStaticSummaryKpiDetails,
  parseKpiDrillDown,
} from "@/lib/kpi-drill-down";

type DashboardRequest =
  | { kind: "all" }
  | { kind: "preset"; days: number }
  | { kind: "custom"; start: string; end: string };

function dashboardRequestToApi(
  r: DashboardRequest
): { start?: string; end?: string; lastNDays?: number } | undefined {
  if (r.kind === "all") return undefined;
  if (r.kind === "preset") return { lastNDays: r.days };
  return { start: r.start, end: r.end };
}

export default function DatasetPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { activeWorkspace } = useWorkspace();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [appendDialogOpen, setAppendDialogOpen] = useState(false);
  const [timeframe, setTimeframe] = useState<TimeframeValue>({ preset: "all" });

  const dataset = useQuery({
    queryKey: ["dataset", params.id],
    queryFn: () => api.getDataset(params.id),
  });

  const preview = useQuery({
    queryKey: ["dataset-preview", params.id],
    queryFn: () => api.getDatasetPreview(params.id),
  });

  const hasDateColumn = (dataset.data?.schema_json?.date_columns?.length ?? 0) > 0;

  const dashboardRequest = useMemo((): DashboardRequest => {
    if (timeframe.preset === "all") return { kind: "all" };
    if (timeframe.preset === "custom") {
      return { kind: "custom", start: timeframe.start, end: timeframe.end };
    }
    const daysMap = { "7d": 7, "14d": 14, "30d": 30, "60d": 60 } as const;
    return { kind: "preset", days: daysMap[timeframe.preset] };
  }, [timeframe]);

  const dashboardData = useQuery({
    queryKey: [
      "dashboard-data",
      params.id,
      dashboardRequest.kind === "all"
        ? "all"
        : dashboardRequest.kind === "preset"
          ? `n:${dashboardRequest.days}`
          : `c:${dashboardRequest.start}:${dashboardRequest.end}`,
    ],
    queryFn: () =>
      api.getDashboardData(params.id, dashboardRequestToApi(dashboardRequest)),
    enabled: !!params.id,
  });

  const analysis = useQuery({
    queryKey: ["analysis", params.id],
    queryFn: () => api.getAnalysisByDataset(params.id),
  });

  const runAnalysis = useMutation({
    mutationFn: () => api.runAnalysis(params.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["analysis", params.id] });
    },
  });

  const forecastMutation = useMutation({
    mutationFn: () => api.runForecast(params.id),
  });

  useEffect(() => {
    forecastMutation.reset();
  }, [activeWorkspace?.id, params.id, forecastMutation.reset]);

  const deleteMutation = useMutation({
    mutationFn: () => api.deleteDataset(params.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      router.push("/datasets");
    },
  });

  const appendMutation = useMutation({
    mutationFn: (file: File) => api.appendToDataset(params.id, file),
    onSuccess: () => {
      setAppendDialogOpen(false);
      queryClient.invalidateQueries({ queryKey: ["dataset", params.id] });
      queryClient.invalidateQueries({ queryKey: ["dataset-preview", params.id] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-data", params.id] });
    },
  });

  const handleAppendFile = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        appendMutation.mutate(file);
      }
      e.target.value = "";
    },
    [appendMutation]
  );

  if (dataset.isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid gap-4 md:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (dataset.isError) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-destructive">
          Could not load this data source: {dataset.error.message}
        </CardContent>
      </Card>
    );
  }

  const data = dataset.data!;
  const schema = data.schema_json;
  const summary = data.data_summary as Record<string, unknown> | null;

  const timeframeWarn =
    hasDateColumn &&
    timeframe.preset !== "all" &&
    dashboardData.data?.timeframe &&
    !dashboardData.data.timeframe.applied
      ? "This period could not be applied—verify the date field format in the source."
      : null;

  const resolvedTfRange =
    dashboardData.data?.timeframe?.applied &&
    dashboardData.data.timeframe.start &&
    dashboardData.data.timeframe.end
      ? {
          start: dashboardData.data.timeframe.start,
          end: dashboardData.data.timeframe.end,
        }
      : null;

  const datasetDateMax = dashboardData.data?.date_bounds?.max ?? null;

  const dashboardTraceContext = useMemo(
    () =>
      buildDatasetDashboardTraceContext({
        datasetName: data.name,
        datasetId: data.id,
        rowCount: typeof summary?.rows === "number" ? summary.rows : null,
        columnCount: typeof summary?.columns === "number" ? summary.columns : null,
        schema,
        dateRangeLabel: resolvedTfRange
          ? `${resolvedTfRange.start} → ${resolvedTfRange.end}`
          : null,
        timeframeWarning: timeframeWarn,
      }),
    [
      data.name,
      data.id,
      summary?.rows,
      summary?.columns,
      schema,
      resolvedTfRange,
      timeframeWarn,
    ]
  );

  const kpiDrillContext = useMemo(() => {
    const tf = dashboardData.data?.timeframe;
    const dateRangeLabel =
      tf?.applied && (tf?.start || tf?.end)
        ? `${tf.start ?? "…"} → ${tf.end ?? "…"}`
        : "Full ingested range (no date filter on this view)";
    const dateColumn = tf?.date_column ?? null;
    const filteredRowCount =
      dashboardData.data?.filtered_row_count ??
      (typeof summary?.rows === "number" ? summary.rows : 0);
    return { dateRangeLabel, dateColumn, filteredRowCount };
  }, [
    dashboardData.data?.timeframe,
    dashboardData.data?.filtered_row_count,
    summary?.rows,
  ]);

  const aiTraceContext = useMemo(
    () =>
      buildDatasetAiTraceContext({
        datasetName: data.name,
        datasetId: data.id,
        rowCount: typeof summary?.rows === "number" ? summary.rows : null,
        columnCount: typeof summary?.columns === "number" ? summary.columns : null,
        schema,
        cleaningStepSummaries: data.cleaned_report?.steps?.slice(0, 4),
      }),
    [
      data.name,
      data.id,
      summary?.rows,
      summary?.columns,
      schema,
      data.cleaned_report?.steps,
    ]
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            {data.name}
          </h1>
          <p className="mt-1 text-sm font-medium text-slate-500">
            {summary?.rows ? `${summary.rows} rows` : ""}{" "}
            {summary?.columns ? `· ${summary.columns} columns` : ""} · Imported{" "}
            {new Date(data.created_at).toLocaleDateString()}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setAppendDialogOpen(true)}
          >
            + Extend source
          </Button>
          {!analysis.data && (
            <Button
              size="sm"
              onClick={() => runAnalysis.mutate()}
              disabled={runAnalysis.isPending}
            >
              {runAnalysis.isPending
                ? "Analyzing…"
                : "Run AI analysis"}
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            className="text-destructive hover:text-destructive"
            onClick={() => setDeleteDialogOpen(true)}
          >
            Delete
          </Button>
        </div>
      </div>

      <div className="dashboard-glass-panel px-5 py-4">
        <TimeframeToolbar
          value={timeframe}
          onChange={setTimeframe}
          hasDateColumn={hasDateColumn}
          appliedLabel={timeframeWarn}
          dataEnd={datasetDateMax}
          resolvedRange={resolvedTfRange}
        />
      </div>

      {dashboardData.data?.dataset_brief ? (
        <div className="dashboard-glass-panel px-5 py-4 text-sm leading-relaxed">
          <span className="font-bold uppercase tracking-wide text-slate-600">
            Source summary
          </span>
          {dashboardData.data.dashboard_plan_source === "ai" ? (
            <span className="ml-2 text-xs font-semibold text-violet-600">
              · AI-curated layout
            </span>
          ) : null}
          <p className="mt-2 text-slate-600">
            {dashboardData.data.dataset_brief}
          </p>
        </div>
      ) : null}

      {/* KPI row — HR-style tiles with gradient trend orbs */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {(dashboardData.data?.kpis?.length ?? 0) > 0
          ? dashboardData.data!.kpis.map((kpi, i) => {
              const details =
                parseKpiDrillDown(kpi.details) ??
                buildHeuristicKpiDetails({
                  title: kpi.title,
                  datasetName: data.name,
                  column: kpi.column ?? null,
                  aggregation: kpi.aggregation ?? null,
                  filteredRowCount: kpiDrillContext.filteredRowCount,
                  dateRangeLabel: kpiDrillContext.dateRangeLabel,
                  dateColumn: kpiDrillContext.dateColumn,
                });
              return (
                <DashboardKpiTile
                  key={kpi.id}
                  index={i}
                  title={kpi.title}
                  value={kpi.formatted}
                  subtitle={kpi.subtitle ?? undefined}
                  details={details}
                />
              );
            })
          : schema?.revenue_columns.map((col, i) => {
              const total = summary?.[`${col}_total`];
              const mean = summary?.[`${col}_mean`];
              const title = `Total ${col.replace(/_/g, " ")}`;
              return (
                <DashboardKpiTile
                  key={col}
                  index={i}
                  title={title}
                  value={
                    total != null
                      ? Number(total).toLocaleString(undefined, {
                          maximumFractionDigits: 0,
                        })
                      : "—"
                  }
                  subtitle={
                    mean != null
                      ? `Avg: ${Number(mean).toLocaleString(undefined, {
                          maximumFractionDigits: 0,
                        })}`
                      : undefined
                  }
                  details={buildStaticSummaryKpiDetails({
                    title,
                    datasetName: data.name,
                    column: col,
                    aggregationLabel: "SUM (ingest summary)",
                    formula_summary: `Stored aggregate data_summary['${col}_total'] on the full cleaned file.`,
                    scopeNote:
                      "Uses the saved summary from import, not the live filtered dataframe. Change the date range above once dashboard KPIs load, or re-open after refresh.",
                  })}
                />
              );
            })}
        {(dashboardData.data?.kpis?.length ?? 0) === 0 ? (
          <>
            <DashboardKpiTile
              index={100}
              title="Rows"
              value={Number(summary?.rows ?? 0).toLocaleString()}
              details={buildStaticSummaryKpiDetails({
                title: "Rows",
                datasetName: data.name,
                aggregationLabel: "count",
                formula_summary: "data_summary.rows (or equivalent) from dataset ingest.",
                scopeNote:
                  "Row count reflects the full cleaned file at ingest—not the filtered slice used for charts.",
              })}
            />
            <DashboardKpiTile
              index={101}
              title="Columns"
              value={Number(summary?.columns ?? 0).toLocaleString()}
              details={buildStaticSummaryKpiDetails({
                title: "Columns",
                datasetName: data.name,
                aggregationLabel: "count",
                formula_summary: "data_summary.columns from dataset ingest.",
                scopeNote:
                  "Column count is schema-wide at ingest; independent of the dashboard date filter.",
              })}
            />
          </>
        ) : null}
      </div>

      <TraceCollapsible
        context={dashboardTraceContext}
        summaryHint={`${data.name} · ${resolvedTfRange ? `${resolvedTfRange.start} → ${resolvedTfRange.end}` : "all periods"}`}
        className="mt-1"
      />

      <Tabs defaultValue="dashboard">
        <TabsList className="dashboard-pill-tabs">
          <TabsTrigger value="dashboard">Business Health</TabsTrigger>
          <TabsTrigger value="analysis">AI analysis</TabsTrigger>
          <TabsTrigger value="forecast">Forecast</TabsTrigger>
          <TabsTrigger value="data">Preview</TabsTrigger>
          <TabsTrigger value="details">Schema</TabsTrigger>
        </TabsList>

        <TabsContent value="dashboard" className="space-y-4 mt-4">
          {dashboardData.isLoading ? (
            <div className="grid gap-4 md:grid-cols-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-72" />
              ))}
            </div>
          ) : (dashboardData.data?.charts?.length ?? 0) === 0 ? (
            <Card>
              <CardContent className="py-8 text-center text-sm text-muted-foreground">
                No charts could be produced from this source with the current
                schema and filters.
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-5 md:grid-cols-2">
              {dashboardData.data?.charts.map((chart, i) => (
                <AutoChart key={chart.id} chart={chart} accentIndex={i} />
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="analysis" className="mt-4">
          {analysis.isLoading ? (
            <Skeleton className="h-64" />
          ) : analysis.data?.result_json ? (
            <AnalysisPanel
              result={analysis.data.result_json as AnalysisResult}
              traceContext={aiTraceContext}
            />
          ) : (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12 text-center">
                <p className="text-sm text-muted-foreground mb-4 max-w-md mx-auto">
                  Run AI analysis for takeaways tied to revenue, cost, and risk—plus
                  a clear next move—not a narration of what’s in each column.
                </p>
                <Button
                  onClick={() => runAnalysis.mutate()}
                  disabled={runAnalysis.isPending}
                >
                  {runAnalysis.isPending
                    ? "Analyzing…"
                    : "Run AI analysis"}
                </Button>
                {runAnalysis.isError && (
                  <p className="text-sm text-destructive mt-2">
                    {runAnalysis.error.message}
                  </p>
                )}
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="forecast" className="mt-4">
          {schema?.date_columns.length && schema?.revenue_columns.length ? (
            forecastMutation.data ? (
              <ForecastChart
                data={forecastMutation.data}
                valueColumn={forecastMutation.data.value_column}
              />
            ) : (
              <Card>
                <CardContent className="flex flex-col items-center justify-center py-12 text-center">
                  <p className="text-sm text-muted-foreground mb-4">
                    Model the next period from your historical series using linear
                    regression—useful for planning, not as a sole forecast of record.
                  </p>
                  <Button
                    onClick={() => forecastMutation.mutate()}
                    disabled={forecastMutation.isPending}
                  >
                    {forecastMutation.isPending
                      ? "Generating..."
                      : "Generate Forecast"}
                  </Button>
                  {forecastMutation.isError && (
                    <p className="text-sm text-destructive mt-2">
                      {forecastMutation.error.message}
                    </p>
                  )}
                </CardContent>
              </Card>
            )
          ) : (
            <Card>
              <CardContent className="py-8 text-center text-sm text-muted-foreground">
                Forecasting needs at least one date field and one revenue or
                numeric measure.
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="data" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Row preview{" "}
                {preview.data && (
                  <span className="text-muted-foreground font-normal">
                    (showing {preview.data.rows.length} of{" "}
                    {preview.data.total_rows})
                  </span>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {preview.isLoading ? (
                <Skeleton className="h-48" />
              ) : preview.isError ? (
                <p className="text-sm text-destructive">
                  Failed to load preview
                </p>
              ) : (
                <div className="overflow-auto rounded-md border max-h-96">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        {preview.data!.columns.map((col) => (
                          <TableHead
                            key={col}
                            className="whitespace-nowrap text-xs"
                          >
                            {col}
                          </TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {preview.data!.rows.map((row, i) => (
                        <TableRow key={i}>
                          {preview.data!.columns.map((col) => (
                            <TableCell
                              key={col}
                              className="whitespace-nowrap text-xs"
                            >
                              {row[col] != null ? String(row[col]) : "—"}
                            </TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="details" className="space-y-4 mt-4">
          {schema && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Detected schema</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {schema.date_columns.map((c) => (
                    <Badge
                      key={c}
                      variant="outline"
                      className="font-mono text-xs"
                    >
                      {c}{" "}
                      <span className="ml-1 text-muted-foreground">date</span>
                    </Badge>
                  ))}
                  {schema.revenue_columns.map((c) => (
                    <Badge
                      key={c}
                      variant="outline"
                      className="font-mono text-xs"
                    >
                      {c}{" "}
                      <span className="ml-1 text-muted-foreground">
                        revenue
                      </span>
                    </Badge>
                  ))}
                  {schema.category_columns.map((c) => (
                    <Badge
                      key={c}
                      variant="outline"
                      className="font-mono text-xs"
                    >
                      {c}{" "}
                      <span className="ml-1 text-muted-foreground">
                        category
                      </span>
                    </Badge>
                  ))}
                  {schema.numeric_columns.map((c) => (
                    <Badge
                      key={c}
                      variant="outline"
                      className="font-mono text-xs"
                    >
                      {c}{" "}
                      <span className="ml-1 text-muted-foreground">
                        numeric
                      </span>
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {data.cleaned_report && data.cleaned_report.steps.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Preparation log</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1">
                  {data.cleaned_report.steps.map((step, i) => (
                    <li
                      key={i}
                      className="text-sm text-muted-foreground flex items-start gap-2"
                    >
                      <span className="text-green-600 mt-0.5">&#10003;</span>
                      {step}
                    </li>
                  ))}
                </ul>
                <p className="text-xs text-muted-foreground mt-3">
                  Shape: {data.cleaned_report.original_shape.join(" x ")} →{" "}
                  {data.cleaned_report.cleaned_shape.join(" x ")}
                </p>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove data source</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            This permanently removes <strong>{data.name}</strong> and all
            associated insights, views, and conversation history. This cannot be undone.
          </p>
          {deleteMutation.isError && (
            <p className="text-sm text-destructive">
              {deleteMutation.error.message}
            </p>
          )}
          <div className="flex justify-end gap-2 mt-2">
            <Button
              variant="outline"
              onClick={() => setDeleteDialogOpen(false)}
              disabled={deleteMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "Deleting..." : "Delete"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Append Data Dialog */}
      <Dialog open={appendDialogOpen} onOpenChange={setAppendDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Extend {data.name}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Import a file with matching columns to append rows to this source.
            Duplicate records are removed automatically.
          </p>
          {appendMutation.isError && (
            <p className="text-sm text-destructive">
              {appendMutation.error.message}
            </p>
          )}
          {appendMutation.isSuccess && (
            <p className="text-sm text-green-600">
              Data appended successfully. {appendMutation.data.row_count} total
              rows now.
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
              onClick={() => setAppendDialogOpen(false)}
              disabled={appendMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              onClick={() => fileInputRef.current?.click()}
              disabled={appendMutation.isPending}
            >
              {appendMutation.isPending ? "Appending..." : "Choose File"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
