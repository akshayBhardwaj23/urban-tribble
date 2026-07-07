"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  api,
  type IntegrationConnectionField,
  type IntegrationProvider,
  type IntegrationRecord,
} from "@/lib/api";

const TIER_LABELS: Record<number, string> = {
  1: "Tier 1 — Must-have",
  2: "Tier 2 — Growth",
  3: "Tier 3 — Enterprise",
};

function statusVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "active") return "default";
  if (status === "error") return "destructive";
  if (status === "syncing") return "secondary";
  return "outline";
}

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString();
}

function ConnectFields({
  fields,
  values,
  onChange,
}: {
  fields: IntegrationConnectionField[];
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
}) {
  if (fields.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        OAuth sign-in for this provider is coming soon. Use an export link mode where available.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      {fields.map((field) => (
        <div key={field.key} className="space-y-1">
          <label className="text-sm font-medium">{field.label}</label>
          {field.type === "textarea" ? (
            <textarea
              className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              placeholder={field.placeholder}
              value={values[field.key] ?? ""}
              onChange={(e) => onChange(field.key, e.target.value)}
            />
          ) : (
            <Input
              type={field.type === "password" ? "password" : field.type === "number" ? "number" : "text"}
              placeholder={field.placeholder}
              value={values[field.key] ?? String(field.default ?? "")}
              onChange={(e) => onChange(field.key, e.target.value)}
            />
          )}
          {field.help ? (
            <p className="text-xs text-muted-foreground">{field.help}</p>
          ) : null}
        </div>
      ))}
    </div>
  );
}

export default function IntegrationsPage() {
  const queryClient = useQueryClient();
  const [connectProvider, setConnectProvider] = useState<IntegrationProvider | null>(null);
  const [connectionMode, setConnectionMode] = useState("");
  const [integrationName, setIntegrationName] = useState("");
  const [config, setConfig] = useState<Record<string, string>>({});
  const [refreshHours, setRefreshHours] = useState("24");
  const [autoAnalyze, setAutoAnalyze] = useState(true);
  const [lockDashboard, setLockDashboard] = useState(true);

  const catalogQuery = useQuery({
    queryKey: ["integration-catalog"],
    queryFn: () => api.getIntegrationCatalog(),
  });

  const listQuery = useQuery({
    queryKey: ["integrations"],
    queryFn: () => api.listIntegrations(),
  });

  const providersByTier = useMemo(() => {
    const providers = catalogQuery.data?.providers ?? [];
    const tiers: Record<number, IntegrationProvider[]> = { 1: [], 2: [], 3: [] };
    for (const p of providers) {
      tiers[p.tier]?.push(p);
    }
    return tiers;
  }, [catalogQuery.data]);

  const openConnect = (provider: IntegrationProvider) => {
    const firstAvailable =
      provider.connection_modes.find((m) => m.available !== false) ??
      provider.connection_modes[0];
    setConnectProvider(provider);
    setConnectionMode(firstAvailable?.id ?? "export_url");
    setIntegrationName(`${provider.name} data`);
    setConfig({});
    setRefreshHours("24");
    setAutoAnalyze(true);
    setLockDashboard(true);
  };

  const activeMode = connectProvider?.connection_modes.find((m) => m.id === connectionMode);

  const createMutation = useMutation({
    mutationFn: () => {
      if (!connectProvider) throw new Error("No provider selected");
      const numericConfig: Record<string, string | number> = { ...config };
      for (const field of activeMode?.fields ?? []) {
        if (field.type === "number" && numericConfig[field.key] != null) {
          numericConfig[field.key] = Number(numericConfig[field.key]);
        }
      }
      return api.createIntegration({
        provider: connectProvider.id,
        name: integrationName.trim(),
        connection_mode: connectionMode,
        config: numericConfig,
        refresh_interval_hours: Number(refreshHours) || 24,
        auto_analyze: autoAnalyze,
        dashboard_plan_locked: lockDashboard,
        run_initial_sync: true,
      });
    },
    onSuccess: (result) => {
      toast.success("Connected and synced");
      queryClient.invalidateQueries({ queryKey: ["integrations"] });
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      setConnectProvider(null);
      if (result.dataset_id) {
        queryClient.invalidateQueries({ queryKey: ["dataset", result.dataset_id] });
      }
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const refreshMutation = useMutation({
    mutationFn: (id: string) => api.refreshIntegration(id),
    onSuccess: (result) => {
      toast.success("Data refreshed");
      queryClient.invalidateQueries({ queryKey: ["integrations"] });
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      if (result.dataset_id) {
        queryClient.invalidateQueries({ queryKey: ["dataset", result.dataset_id] });
        queryClient.invalidateQueries({ queryKey: ["dashboard-data", result.dataset_id] });
      }
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteIntegration(id),
    onSuccess: () => {
      toast.success("Integration removed");
      queryClient.invalidateQueries({ queryKey: ["integrations"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const patchMutation = useMutation({
    mutationFn: ({
      id,
      refresh_interval_hours,
    }: {
      id: string;
      refresh_interval_hours: number;
    }) => api.patchIntegration(id, { refresh_interval_hours }),
    onSuccess: () => {
      toast.success("Schedule updated");
      queryClient.invalidateQueries({ queryKey: ["integrations"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const connected = listQuery.data ?? [];

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Integrations</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Connect live data sources. Dashboards stay pinned—KPIs and charts only change when
            your column schema changes. Refresh manually anytime or on your schedule (default every
            24 hours).
          </p>
        </div>
        <Link
          href="/upload"
          className="inline-flex h-9 shrink-0 items-center justify-center rounded-md border px-4 text-sm font-medium transition-colors hover:bg-muted"
        >
          Manual import
        </Link>
      </div>

      <section className="space-y-3">
        <h2 className="text-lg font-medium">Connected</h2>
        {listQuery.isLoading ? (
          <Skeleton className="h-24" />
        ) : connected.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-sm text-muted-foreground">
              No integrations yet. Pick a provider below to connect your first live source.
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-3">
            {connected.map((row: IntegrationRecord) => (
              <Card key={row.id}>
                <CardContent className="flex flex-col gap-4 py-4 sm:flex-row sm:items-center sm:justify-between">
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium">{row.name}</p>
                      <Badge variant={statusVariant(row.status)}>{row.status}</Badge>
                      <Badge variant="outline">{row.provider_name}</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Last sync: {formatRelative(row.last_sync_at)} · Next:{" "}
                      {formatRelative(row.next_sync_at)} · Every {row.refresh_interval_hours}h
                      {row.dashboard_plan_locked ? " · Dashboard locked" : ""}
                    </p>
                    {row.last_sync_error ? (
                      <p className="text-xs text-destructive">{row.last_sync_error}</p>
                    ) : null}
                    {row.dataset_id ? (
                      <Link
                        href={`/datasets/${row.dataset_id}`}
                        className="text-xs text-primary hover:underline"
                      >
                        View dashboard →
                      </Link>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="flex items-center gap-1">
                      <Input
                        type="number"
                        min={1}
                        max={168}
                        className="h-8 w-16 text-xs"
                        defaultValue={row.refresh_interval_hours}
                        onBlur={(e) => {
                          const v = Number(e.target.value);
                          if (v >= 1 && v <= 168 && v !== row.refresh_interval_hours) {
                            patchMutation.mutate({ id: row.id, refresh_interval_hours: v });
                          }
                        }}
                      />
                      <span className="text-xs text-muted-foreground">hrs</span>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={refreshMutation.isPending || row.status === "syncing"}
                      onClick={() => refreshMutation.mutate(row.id)}
                    >
                      {refreshMutation.isPending ? "Refreshing…" : "Refresh now"}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-destructive"
                      onClick={() => deleteMutation.mutate(row.id)}
                    >
                      Remove
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>

      {([1, 2, 3] as const).map((tier) => (
        <section key={tier} className="space-y-3">
          <h2 className="text-lg font-medium">{TIER_LABELS[tier]}</h2>
          {catalogQuery.isLoading ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-28" />
              ))}
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {(providersByTier[tier] ?? []).map((provider) => {
                const hasLiveMode = provider.connection_modes.some((m) => m.available !== false);
                return (
                  <Card key={provider.id} className="flex flex-col">
                    <CardHeader className="pb-2">
                      <div className="flex items-start justify-between gap-2">
                        <CardTitle className="text-base">{provider.name}</CardTitle>
                        <Badge variant="outline" className="shrink-0 text-[10px]">
                          {provider.category}
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent className="flex flex-1 flex-col gap-3 pt-0">
                      <p className="flex-1 text-sm text-muted-foreground">
                        {provider.description}
                      </p>
                      <Button
                        size="sm"
                        disabled={!hasLiveMode}
                        onClick={() => openConnect(provider)}
                      >
                        {hasLiveMode ? "Connect" : "Coming soon"}
                      </Button>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </section>
      ))}

      <Dialog open={!!connectProvider} onOpenChange={(o) => !o && setConnectProvider(null)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Connect {connectProvider?.name}</DialogTitle>
          </DialogHeader>
          {connectProvider ? (
            <div className="space-y-4">
              <div className="space-y-1">
                <label className="text-sm font-medium">Display name</label>
                <Input
                  value={integrationName}
                  onChange={(e) => setIntegrationName(e.target.value)}
                />
              </div>

              <div className="space-y-1">
                <label className="text-sm font-medium">Connection type</label>
                <div className="flex flex-wrap gap-2">
                  {connectProvider.connection_modes.map((mode) => (
                    <Button
                      key={mode.id}
                      type="button"
                      size="sm"
                      variant={connectionMode === mode.id ? "default" : "outline"}
                      disabled={mode.available === false}
                      onClick={() => setConnectionMode(mode.id)}
                    >
                      {mode.label}
                    </Button>
                  ))}
                </div>
              </div>

              <ConnectFields
                fields={activeMode?.fields ?? []}
                values={config}
                onChange={(key, value) => setConfig((c) => ({ ...c, [key]: value }))}
              />

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1">
                  <label className="text-sm font-medium">Auto-refresh every (hours)</label>
                  <Input
                    type="number"
                    min={1}
                    max={168}
                    value={refreshHours}
                    onChange={(e) => setRefreshHours(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">Default: 24 hours</p>
                </div>
              </div>

              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={autoAnalyze}
                  onChange={(e) => setAutoAnalyze(e.target.checked)}
                />
                Run AI briefing after each sync
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={lockDashboard}
                  onChange={(e) => setLockDashboard(e.target.checked)}
                />
                Keep dashboard layout stable (recommended)
              </label>

              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setConnectProvider(null)}>
                  Cancel
                </Button>
                <Button
                  onClick={() => createMutation.mutate()}
                  disabled={createMutation.isPending || !integrationName.trim()}
                >
                  {createMutation.isPending ? "Connecting…" : "Connect & sync"}
                </Button>
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
