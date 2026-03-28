"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
import { AnalysisPanel } from "@/components/dashboard/analysis-panel";
import { ChatOverlay } from "@/components/chat/chat-panel";
import { api } from "@/lib/api";

export default function OverviewPage() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [appendTarget, setAppendTarget] = useState<{
    id: string;
    name: string;
  } | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["overview"],
    queryFn: () => api.getOverview(),
  });

  const overviewAnalysis = useQuery({
    queryKey: ["overview-analysis"],
    queryFn: () => api.getOverviewAnalysis(),
  });

  const runOverviewAnalysis = useMutation({
    mutationFn: () => api.runOverviewAnalysis(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["overview-analysis"] });
    },
  });

  const forecastMutation = useMutation({
    mutationFn: () => api.runOverviewForecast(),
  });

  const appendMutation = useMutation({
    mutationFn: ({ datasetId, file }: { datasetId: string; file: File }) =>
      api.appendToDataset(datasetId, file),
    onSuccess: () => {
      setAppendTarget(null);
      queryClient.invalidateQueries({ queryKey: ["overview"] });
      queryClient.invalidateQueries({ queryKey: ["overview-analysis"] });
    },
  });

  const handleAppendFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && appendTarget) {
      appendMutation.mutate({ datasetId: appendTarget.id, file });
    }
    e.target.value = "";
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid gap-4 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-72" />
          ))}
        </div>
      </div>
    );
  }

  if (!data || data.total_datasets === 0) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Business Health</h1>
          <p className="text-sm text-muted-foreground mt-1">
            A single view of performance signals across your workspace.
          </p>
        </div>
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 text-center">
            <p className="text-sm text-muted-foreground mb-4">
              Import your first file to unlock KPIs, views, and executive-ready
              summaries.
            </p>
            <Link
              href="/upload"
              className="inline-flex h-9 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              Import Data
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  const analysisResult = overviewAnalysis.data?.result_json;

  return (
    <div className="space-y-6">
      {/* Header with actions */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Business Health</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Consolidated signals across {data.total_datasets} data source
            {data.total_datasets !== 1 ? "s" : ""} &middot;{" "}
            {data.total_rows.toLocaleString()} records
          </p>
        </div>
        <div className="flex items-center gap-2">
          {data.datasets.length > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                const ds = data.datasets[0];
                setAppendTarget({ id: ds.id, name: ds.name });
              }}
            >
              + Extend source
            </Button>
          )}
          <Link href="/upload">
            <Button size="sm">Import Data</Button>
          </Link>
          {!analysisResult && !overviewAnalysis.isLoading && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => runOverviewAnalysis.mutate()}
              disabled={runOverviewAnalysis.isPending}
            >
              {runOverviewAnalysis.isPending
                ? "Generating insights..."
                : "Generate insights"}
            </Button>
          )}
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card className="dashboard-glass-panel ring-0">
          <CardHeader className="pb-2">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Data sources
            </p>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">{data.total_datasets}</p>
          </CardContent>
        </Card>
        <Card className="dashboard-glass-panel ring-0">
          <CardHeader className="pb-2">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Total records
            </p>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">
              {data.total_rows.toLocaleString()}
            </p>
          </CardContent>
        </Card>
        {data.kpis.slice(0, 2).map((kpi: { label: string; value: number; dataset_name: string }, i: number) => (
          <Card key={i} className="dashboard-glass-panel ring-0">
            <CardHeader className="pb-2">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                {kpi.label}
              </p>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-semibold">
                {Number(kpi.value).toLocaleString(undefined, {
                  maximumFractionDigits: 0,
                })}
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                Source · {kpi.dataset_name}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      {data.kpis.length > 2 && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {data.kpis.slice(2).map((kpi: { label: string; value: number; dataset_name: string }, i: number) => (
            <Card key={i} className="dashboard-glass-panel ring-0">
              <CardHeader className="pb-2">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                  {kpi.label}
                </p>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-semibold">
                  {Number(kpi.value).toLocaleString(undefined, {
                    maximumFractionDigits: 0,
                  })}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Source · {kpi.dataset_name}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Tabs */}
      <Tabs defaultValue="dashboard">
        <TabsList className="dashboard-pill-tabs">
          <TabsTrigger value="dashboard">Business Health</TabsTrigger>
          <TabsTrigger value="analysis">Insights</TabsTrigger>
          <TabsTrigger value="forecast">Forecast</TabsTrigger>
          <TabsTrigger value="datasets">Data Sources</TabsTrigger>
        </TabsList>

        {/* Business Health tab - charts */}
        <TabsContent value="dashboard" className="space-y-4 mt-4">
          {data.charts.length > 0 ? (
            <div className="grid gap-5 md:grid-cols-2">
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
                <div key={chart.id}>
                  <AutoChart chart={chart} accentIndex={i} />
                  {chart.dataset_name && (
                    <p className="mt-2 text-xs font-medium text-slate-500">
                      Source · {chart.dataset_name}
                    </p>
                  )}
                </div>
              )
              )}
            </div>
          ) : (
            <Card>
              <CardContent className="py-8 text-center text-sm text-muted-foreground">
                No charts are available yet from your connected sources.
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Insights tab */}
        <TabsContent value="analysis" className="mt-4">
          {overviewAnalysis.isLoading ? (
            <Skeleton className="h-64" />
          ) : analysisResult ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground">
                  Last refreshed:{" "}
                  {new Date(
                    overviewAnalysis.data!.created_at
                  ).toLocaleString()}
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => runOverviewAnalysis.mutate()}
                  disabled={runOverviewAnalysis.isPending}
                >
                  {runOverviewAnalysis.isPending
                    ? "Refreshing..."
                    : "Refresh insights"}
                </Button>
              </div>
              <AnalysisPanel result={analysisResult} />
            </div>
          ) : (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12 text-center">
                <p className="text-sm text-muted-foreground mb-2">
                  Synthesize narrative insights, variance, and recommended next
                  steps across every connected source—built for leadership review.
                </p>
                <p className="text-xs text-muted-foreground mb-4">
                  Covers {data.total_datasets} source
                  {data.total_datasets !== 1 ? "s" : ""} and{" "}
                  {data.total_rows.toLocaleString()} records.
                </p>
                <Button
                  onClick={() => runOverviewAnalysis.mutate()}
                  disabled={runOverviewAnalysis.isPending}
                >
                  {runOverviewAnalysis.isPending
                    ? "Generating insights..."
                    : "Generate insights"}
                </Button>
                {runOverviewAnalysis.isError && (
                  <p className="text-sm text-destructive mt-2">
                    {runOverviewAnalysis.error.message}
                  </p>
                )}
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Forecast tab */}
        <TabsContent value="forecast" className="mt-4">
          {forecastMutation.data ? (
            <div className="space-y-4">
              <p className="text-xs text-muted-foreground">
                Outlook for{" "}
                <strong>{forecastMutation.data.value_column.replace(/_/g, " ")}</strong>{" "}
                · <strong>{forecastMutation.data.dataset_name}</strong>
              </p>
              <ForecastChart
                data={forecastMutation.data}
                valueColumn={forecastMutation.data.value_column}
              />
            </div>
          ) : (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12 text-center">
                <p className="text-sm text-muted-foreground mb-2">
                  Project forward from the strongest time-series signal across your
                  sources—ideal for planning and board-ready narratives.
                </p>
                <p className="text-xs text-muted-foreground mb-4">
                  Uses linear regression on your historical series; results are
                  directional, not guarantees.
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
          )}
        </TabsContent>

        {/* Data Sources tab */}
        <TabsContent value="datasets" className="mt-4">
          <div className="grid gap-3">
            {data.datasets.map((ds) => (
              <Card
                key={ds.id}
                className="transition-colors hover:bg-accent/50"
              >
                <CardContent className="flex items-center justify-between py-3">
                  <Link href={`/datasets/${ds.id}`} className="flex-1">
                    <p className="text-sm font-medium">{ds.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {ds.row_count?.toLocaleString()} rows &middot;{" "}
                      {ds.column_count} columns &middot;{" "}
                      {new Date(ds.created_at).toLocaleDateString()}
                    </p>
                  </Link>
                  <Button
                    variant="outline"
                    size="sm"
                    className="ml-3 shrink-0"
                    onClick={(e) => {
                      e.preventDefault();
                      setAppendTarget({ id: ds.id, name: ds.name });
                    }}
                  >
                    + Extend source
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>
      </Tabs>

      {/* Append dialog */}
      <Dialog
        open={!!appendTarget}
        onOpenChange={(open) => !open && setAppendTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Extend {appendTarget?.name}</DialogTitle>
          </DialogHeader>
          {data.datasets.length > 1 && (
            <div className="space-y-1">
              <label className="text-sm font-medium">Target source</label>
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
              onClick={() => setAppendTarget(null)}
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

      {/* Floating AI Chat */}
      <ChatOverlay datasets={data.datasets} />
    </div>
  );
}
