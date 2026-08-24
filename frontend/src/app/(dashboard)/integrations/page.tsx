"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
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
import {
  availableModes,
  isOauthMode,
  isProviderConnectable,
  isWaveOne,
  preferredMode,
  supportsMultiFileConnect,
} from "@/lib/integrations-flags";
import { formatUserFacingApiError } from "@/lib/api-errors";

const TIER_LABELS: Record<number, string> = {
  1: "Tier 1 — Must-have",
  2: "Tier 2 — Growth",
  3: "Tier 3 — Enterprise",
};

function statusVariant(
  status: string,
): "default" | "secondary" | "destructive" | "outline" {
  if (status === "active") return "default";
  if (status === "error") return "destructive";
  if (status === "syncing" || status === "pending") return "secondary";
  return "outline";
}

function formatWhen(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

/**
 * Sources refresh only when asked while the backend is in manual-only mode, so
 * a "next sync" time would be a promise the server will not keep. The record's
 * own next_sync_at is the honest signal: the backend leaves it null when
 * nothing is scheduled.
 */
function scheduleLabel(row: IntegrationRecord): string {
  return row.next_sync_at
    ? `Next refresh ${formatWhen(row.next_sync_at)}`
    : "Refreshes when you ask";
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
              type={
                field.type === "password"
                  ? "password"
                  : field.type === "number"
                    ? "number"
                    : "text"
              }
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
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();

  const [connectProvider, setConnectProvider] =
    useState<IntegrationProvider | null>(null);
  const [connectionMode, setConnectionMode] = useState("");
  const [integrationName, setIntegrationName] = useState("");
  const [config, setConfig] = useState<Record<string, string>>({});
  // null means the user has not chosen yet, which is distinct from having
  // deselected everything -- otherwise clearing a single auto-selected file
  // would immediately re-select it.
  const [selectedFileIds, setSelectedFileIds] = useState<string[] | null>(null);

  const oauthSessionId = searchParams.get("oauth_session");

  const catalogQuery = useQuery({
    queryKey: ["integration-catalog"],
    queryFn: () => api.getIntegrationCatalog(),
  });

  const listQuery = useQuery({
    queryKey: ["integrations"],
    queryFn: () => api.listIntegrations(),
    // A freshly connected source syncs in the background; poll until it settles
    // so the user sees it go from pending to active without a manual reload.
    refetchInterval: (query) => {
      const rows = query.state.data as IntegrationRecord[] | undefined;
      const busy = rows?.some(
        (r) => r.status === "pending" || r.status === "syncing",
      );
      return busy ? 4000 : false;
    },
  });

  const oauthSessionQuery = useQuery({
    queryKey: ["integration-oauth-session", oauthSessionId],
    queryFn: () => api.getIntegrationOauthSession(oauthSessionId!),
    enabled: Boolean(oauthSessionId),
    retry: false,
  });

  const backendEnabled = catalogQuery.data?.enabled ?? false;
  const providers = useMemo(
    () => catalogQuery.data?.providers ?? [],
    [catalogQuery.data],
  );

  const providersByTier = useMemo(() => {
    const tiers: Record<number, IntegrationProvider[]> = { 1: [], 2: [], 3: [] };
    for (const p of providers) tiers[p.tier]?.push(p);
    return tiers;
  }, [providers]);

  const oauthSession = oauthSessionQuery.data;
  const oauthProvider = oauthSession
    ? providers.find((p) => p.id === oauthSession.provider)
    : undefined;
  const multiSelect = oauthSession
    ? supportsMultiFileConnect(oauthSession.provider)
    : false;

  const oauthFiles = useMemo(() => oauthSession?.files ?? [], [oauthSession]);

  // With exactly one file there is nothing to choose between, so it starts
  // selected. Derived rather than written into state by an effect.
  const selectedIds = useMemo(() => {
    if (selectedFileIds !== null) return selectedFileIds;
    return oauthFiles.length === 1 ? [oauthFiles[0].id] : [];
  }, [selectedFileIds, oauthFiles]);

  const openConnect = (provider: IntegrationProvider) => {
    const mode = preferredMode(provider);
    setConnectProvider(provider);
    setConnectionMode(mode?.id ?? "");
    setIntegrationName(`${provider.name} data`);
    setConfig({});
  };

  const activeMode = connectProvider?.connection_modes.find(
    (m) => m.id === connectionMode,
  );

  const invalidateAfterChange = (datasetId?: string | null) => {
    queryClient.invalidateQueries({ queryKey: ["integrations"] });
    queryClient.invalidateQueries({ queryKey: ["datasets"] });
    if (datasetId) {
      queryClient.invalidateQueries({ queryKey: ["dataset", datasetId] });
      queryClient.invalidateQueries({ queryKey: ["dashboard-data", datasetId] });
    }
  };

  const createMutation = useMutation({
    mutationFn: () => {
      if (!connectProvider) throw new Error("No provider selected");
      const typed: Record<string, string | number> = { ...config };
      for (const field of activeMode?.fields ?? []) {
        if (field.type === "number" && typed[field.key] != null) {
          typed[field.key] = Number(typed[field.key]);
        }
      }
      return api.createIntegration({
        provider: connectProvider.id,
        name: integrationName.trim(),
        connection_mode: connectionMode,
        config: typed,
        run_initial_sync: true,
      });
    },
    onSuccess: (result) => {
      toast.success("Connected and synced");
      setConnectProvider(null);
      invalidateAfterChange(result.dataset_id);
    },
    onError: (e: Error) =>
      toast.error(formatUserFacingApiError(e, "connect this source")),
  });

  const oauthStartMutation = useMutation({
    mutationFn: () => {
      if (!connectProvider) throw new Error("No provider selected");
      return api.startIntegrationOauth({
        provider: connectProvider.id,
        name: integrationName.trim(),
      });
    },
    onSuccess: (result) => {
      window.location.href = result.authorize_url;
    },
    onError: (e: Error) =>
      toast.error(formatUserFacingApiError(e, "start sign-in")),
  });

  const clearOauthSession = () => {
    setSelectedFileIds(null);
    router.replace("/integrations");
  };

  const completeOauthMutation = useMutation({
    mutationFn: async () => {
      if (!oauthSessionId || selectedIds.length === 0) {
        throw new Error("Select at least one file first");
      }
      if (multiSelect) {
        return api.completeGoogleOauth({
          session_id: oauthSessionId,
          item_ids: selectedIds,
        });
      }
      return api.completeMicrosoftOauth({
        session_id: oauthSessionId,
        item_id: selectedIds[0],
      });
    },
    onSuccess: (result) => {
      const connected =
        "connected" in result ? result.connected : 1;
      toast.success(
        connected === 1
          ? "Connected. Preparing your dashboard…"
          : `Connected ${connected} sources. Preparing dashboards…`,
      );
      clearOauthSession();
      invalidateAfterChange(
        "dataset_id" in result ? result.dataset_id : undefined,
      );
    },
    onError: (e: Error) =>
      toast.error(formatUserFacingApiError(e, "finish connecting")),
  });

  const refreshMutation = useMutation({
    mutationFn: (id: string) => api.refreshIntegration(id),
    onSuccess: (result) => {
      toast.success(
        result.skipped
          ? "Already up to date — nothing has changed at the source."
          : "Refreshed",
      );
      if (result.analysis_skipped_reason) {
        toast.message("Data refreshed, no new briefing", {
          description: result.analysis_skipped_reason,
        });
      }
      invalidateAfterChange(result.dataset_id);
    },
    onError: (e: Error) =>
      toast.error(formatUserFacingApiError(e, "refresh this source")),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteIntegration(id),
    onSuccess: () => {
      toast.success("Source removed. Its existing dashboard is kept.");
      invalidateAfterChange();
    },
    onError: (e: Error) =>
      toast.error(formatUserFacingApiError(e, "remove this source")),
  });

  const connected = listQuery.data ?? [];

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Integrations</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Connect a spreadsheet once and refresh it whenever you need a fresh
            read. Your dashboard layout stays put — charts only change when the
            columns in your data change.
          </p>
        </div>
        <Link
          href="/upload"
          className="inline-flex h-9 shrink-0 items-center justify-center rounded-md border px-4 text-sm font-medium transition-colors hover:bg-muted"
        >
          Import a file instead
        </Link>
      </div>

      {catalogQuery.isSuccess && !backendEnabled ? (
        <Card className="border-dashed">
          <CardContent className="space-y-1 py-6">
            <p className="text-sm font-medium">Integrations are not switched on yet</p>
            <p className="text-sm text-muted-foreground">
              You can see the providers we support below. Until this is enabled,
              import CSV or Excel files from Import — dashboards and chat work
              the same way from those.
            </p>
          </CardContent>
        </Card>
      ) : null}

      {oauthSessionId ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Choose what to connect
              {oauthProvider ? ` from ${oauthProvider.name}` : ""}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {oauthSessionQuery.isLoading ? (
              <Skeleton className="h-24" />
            ) : oauthSessionQuery.isError ? (
              <div className="space-y-3">
                <p className="text-sm text-destructive">
                  That sign-in has expired. Start again from the provider below.
                </p>
                <Button variant="outline" onClick={clearOauthSession}>
                  Dismiss
                </Button>
              </div>
            ) : (
              <>
                <p className="text-sm text-muted-foreground">
                  {multiSelect
                    ? "Pick one or more spreadsheets. Each becomes its own dashboard you can refresh independently."
                    : "Pick the workbook to sync."}
                </p>

                <div className="grid gap-2">
                  {oauthFiles.map((file) => {
                    const checked = selectedIds.includes(file.id);
                    return (
                      <label
                        key={file.id}
                        className="flex cursor-pointer items-start gap-3 rounded-md border p-3 text-sm hover:bg-muted/50"
                      >
                        <input
                          type={multiSelect ? "checkbox" : "radio"}
                          name="oauth-file"
                          className="mt-0.5"
                          checked={checked}
                          onChange={() => {
                            if (!multiSelect) {
                              setSelectedFileIds([file.id]);
                              return;
                            }
                            setSelectedFileIds(
                              checked
                                ? selectedIds.filter((id) => id !== file.id)
                                : [...selectedIds, file.id],
                            );
                          }}
                        />
                        <div className="min-w-0">
                          <p className="font-medium">{file.name}</p>
                          <p className="text-xs text-muted-foreground">
                            {file.last_modified
                              ? `Edited ${formatWhen(file.last_modified)}`
                              : "Spreadsheet"}
                          </p>
                        </div>
                      </label>
                    );
                  })}
                </div>

                {oauthFiles.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No spreadsheets were found in that account.
                  </p>
                ) : null}

                <div className="flex flex-wrap gap-2">
                  <Button
                    onClick={() => completeOauthMutation.mutate()}
                    disabled={
                      completeOauthMutation.isPending ||
                      selectedIds.length === 0
                    }
                  >
                    {completeOauthMutation.isPending
                      ? "Connecting…"
                      : selectedIds.length > 1
                        ? `Connect ${selectedIds.length} sheets`
                        : "Connect"}
                  </Button>
                  <Button variant="outline" onClick={clearOauthSession}>
                    Cancel
                  </Button>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      ) : null}

      <section className="space-y-3">
        <h2 className="text-lg font-medium">Connected sources</h2>
        {listQuery.isLoading ? (
          <Skeleton className="h-24" />
        ) : connected.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-sm text-muted-foreground">
              Nothing connected yet. Pick a provider below to connect your first
              source.
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-3">
            {connected.map((row) => {
              const busy = row.status === "syncing" || row.status === "pending";
              return (
                <Card key={row.id}>
                  <CardContent className="flex flex-col gap-4 py-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-medium">{row.name}</p>
                        <Badge variant={statusVariant(row.status)}>
                          {row.status === "pending" ? "preparing" : row.status}
                        </Badge>
                        <Badge variant="outline">{row.provider_name}</Badge>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Last refreshed {formatWhen(row.last_sync_at)} ·{" "}
                        {scheduleLabel(row)}
                      </p>
                      {row.last_sync_error ? (
                        <p className="text-xs text-destructive">
                          {row.last_sync_error}
                        </p>
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
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={busy || refreshMutation.isPending}
                        onClick={() => refreshMutation.mutate(row.id)}
                      >
                        {busy ? "Working…" : "Refresh now"}
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
              );
            })}
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
          ) : catalogQuery.isError ? (
            <p className="text-sm text-muted-foreground">
              Provider list unavailable right now.
            </p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {(providersByTier[tier] ?? []).map((provider) => {
                const connectable =
                  backendEnabled && isProviderConnectable(provider);
                return (
                  <Card
                    key={provider.id}
                    className={`flex flex-col ${connectable ? "" : "opacity-90"}`}
                  >
                    <CardHeader className="pb-2">
                      <div className="flex items-start justify-between gap-2">
                        <CardTitle className="text-base">
                          {provider.name}
                        </CardTitle>
                        <Badge
                          variant="outline"
                          className="shrink-0 text-[10px]"
                        >
                          {provider.category}
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent className="flex flex-1 flex-col gap-3 pt-0">
                      <p className="flex-1 text-sm text-muted-foreground">
                        {provider.description}
                      </p>
                      <div className="flex items-center gap-2">
                        <Button
                          size="sm"
                          disabled={!connectable}
                          onClick={() => openConnect(provider)}
                        >
                          {connectable ? "Connect" : "Coming soon"}
                        </Button>
                        {connectable && isWaveOne(provider.id) ? (
                          <span className="text-[10px] text-muted-foreground">
                            Recommended
                          </span>
                        ) : null}
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </section>
      ))}

      <Dialog
        open={!!connectProvider}
        onOpenChange={(o) => !o && setConnectProvider(null)}
      >
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Connect {connectProvider?.name}</DialogTitle>
          </DialogHeader>
          {connectProvider ? (
            <div className="space-y-4">
              <div className="space-y-1">
                <label className="text-sm font-medium">Name</label>
                <Input
                  value={integrationName}
                  onChange={(e) => setIntegrationName(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  {supportsMultiFileConnect(connectProvider.id)
                    ? "Used only if you connect a single sheet — otherwise each source takes its file's name."
                    : "What this source is called in your workspace."}
                </p>
              </div>

              {availableModes(connectProvider).length > 1 ? (
                <div className="space-y-1">
                  <label className="text-sm font-medium">How to connect</label>
                  <div className="flex flex-wrap gap-2">
                    {availableModes(connectProvider).map((mode) => (
                      <Button
                        key={mode.id}
                        type="button"
                        size="sm"
                        variant={
                          connectionMode === mode.id ? "default" : "outline"
                        }
                        onClick={() => setConnectionMode(mode.id)}
                      >
                        {mode.label}
                      </Button>
                    ))}
                  </div>
                </div>
              ) : null}

              {activeMode?.help ? (
                <p className="text-xs text-muted-foreground">{activeMode.help}</p>
              ) : null}

              {!isOauthMode(activeMode) ? (
                <ConnectFields
                  fields={activeMode?.fields ?? []}
                  values={config}
                  onChange={(key, value) =>
                    setConfig((c) => ({ ...c, [key]: value }))
                  }
                />
              ) : null}

              <div className="flex justify-end gap-2 pt-2">
                <Button
                  variant="outline"
                  onClick={() => setConnectProvider(null)}
                >
                  Cancel
                </Button>
                <Button
                  onClick={() =>
                    isOauthMode(activeMode)
                      ? oauthStartMutation.mutate()
                      : createMutation.mutate()
                  }
                  disabled={
                    createMutation.isPending ||
                    oauthStartMutation.isPending ||
                    !integrationName.trim() ||
                    !activeMode
                  }
                >
                  {isOauthMode(activeMode)
                    ? oauthStartMutation.isPending
                      ? "Redirecting…"
                      : `Continue with ${activeMode?.label ?? "provider"}`
                    : createMutation.isPending
                      ? "Connecting…"
                      : "Connect"}
                </Button>
              </div>
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
