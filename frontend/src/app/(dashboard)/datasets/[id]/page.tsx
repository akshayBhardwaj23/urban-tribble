"use client";

import { useCallback, useRef, useState } from "react";
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
import { ForecastChart } from "@/components/charts/forecast-chart";
import { AnalysisPanel } from "@/components/dashboard/analysis-panel";
import { api } from "@/lib/api";

export default function DatasetPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [appendDialogOpen, setAppendDialogOpen] = useState(false);

  const dataset = useQuery({
    queryKey: ["dataset", params.id],
    queryFn: () => api.getDataset(params.id),
  });

  const preview = useQuery({
    queryKey: ["dataset-preview", params.id],
    queryFn: () => api.getDatasetPreview(params.id),
  });

  const dashboardData = useQuery({
    queryKey: ["dashboard-data", params.id],
    queryFn: () => api.getDashboardData(params.id),
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
          Failed to load dataset: {dataset.error.message}
        </CardContent>
      </Card>
    );
  }

  const data = dataset.data!;
  const schema = data.schema_json;
  const summary = data.data_summary as Record<string, unknown> | null;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{data.name}</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {summary?.rows ? `${summary.rows} rows` : ""}{" "}
            {summary?.columns ? `· ${summary.columns} columns` : ""} · Uploaded{" "}
            {new Date(data.created_at).toLocaleDateString()}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setAppendDialogOpen(true)}
          >
            + Append Data
          </Button>
          {!analysis.data && (
            <Button
              size="sm"
              onClick={() => runAnalysis.mutate()}
              disabled={runAnalysis.isPending}
            >
              {runAnalysis.isPending ? "Analyzing..." : "Run AI Analysis"}
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

      {dashboardData.data?.dataset_brief ? (
        <div className="rounded-md border bg-muted/40 px-4 py-3 text-sm leading-relaxed">
          <span className="font-medium text-foreground">About this file</span>
          {dashboardData.data.dashboard_plan_source === "ai" ? (
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              · AI-chosen layout
            </span>
          ) : null}
          <p className="text-muted-foreground mt-1.5">
            {dashboardData.data.dataset_brief}
          </p>
        </div>
      ) : null}

      {/* KPI Cards — planned KPIs from upload-time dashboard planner when available */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {(dashboardData.data?.kpis?.length ?? 0) > 0
          ? dashboardData.data!.kpis.map((kpi) => (
              <Card key={kpi.id}>
                <CardHeader className="pb-2">
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                    {kpi.title}
                  </p>
                </CardHeader>
                <CardContent>
                  <p className="text-2xl font-semibold tabular-nums">
                    {kpi.formatted}
                  </p>
                </CardContent>
              </Card>
            ))
          : schema?.revenue_columns.map((col) => {
              const total = summary?.[`${col}_total`];
              const mean = summary?.[`${col}_mean`];
              return (
                <Card key={col}>
                  <CardHeader className="pb-2">
                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                      Total {col.replace(/_/g, " ")}
                    </p>
                  </CardHeader>
                  <CardContent>
                    {total != null && (
                      <p className="text-2xl font-semibold">
                        {Number(total).toLocaleString(undefined, {
                          maximumFractionDigits: 0,
                        })}
                      </p>
                    )}
                    {mean != null && (
                      <p className="text-xs text-muted-foreground mt-1">
                        Avg:{" "}
                        {Number(mean).toLocaleString(undefined, {
                          maximumFractionDigits: 0,
                        })}
                      </p>
                    )}
                  </CardContent>
                </Card>
              );
            })}
        <Card>
          <CardHeader className="pb-2">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Rows
            </p>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">
              {Number(summary?.rows ?? 0).toLocaleString()}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Columns
            </p>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">
              {Number(summary?.columns ?? 0).toLocaleString()}
            </p>
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="dashboard">
        <TabsList>
          <TabsTrigger value="dashboard">Dashboard</TabsTrigger>
          <TabsTrigger value="analysis">AI Analysis</TabsTrigger>
          <TabsTrigger value="forecast">Forecast</TabsTrigger>
          <TabsTrigger value="data">Data</TabsTrigger>
          <TabsTrigger value="details">Details</TabsTrigger>
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
                No charts could be auto-generated from this dataset.
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {dashboardData.data?.charts.map((chart) => (
                <AutoChart key={chart.id} chart={chart} />
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="analysis" className="mt-4">
          {analysis.isLoading ? (
            <Skeleton className="h-64" />
          ) : analysis.data?.result_json ? (
            <AnalysisPanel result={analysis.data.result_json} />
          ) : (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12 text-center">
                <p className="text-sm text-muted-foreground mb-4">
                  No AI analysis yet. Click the button to analyze this dataset.
                </p>
                <Button
                  onClick={() => runAnalysis.mutate()}
                  disabled={runAnalysis.isPending}
                >
                  {runAnalysis.isPending ? "Analyzing..." : "Run AI Analysis"}
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
                    Generate a forecast based on your historical data using
                    linear regression.
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
                Forecasting requires at least one date column and one
                revenue/numeric column.
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="data" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Data Preview{" "}
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
                <CardTitle className="text-base">Detected Columns</CardTitle>
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
                <CardTitle className="text-base">Cleaning Report</CardTitle>
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
            <DialogTitle>Delete dataset</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            This will permanently delete <strong>{data.name}</strong> and all
            its analysis, charts, and chat history. This action cannot be undone.
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
            <DialogTitle>Append data to {data.name}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Upload a file with matching columns to add more rows to this
            dataset. Duplicate rows will be automatically removed.
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
