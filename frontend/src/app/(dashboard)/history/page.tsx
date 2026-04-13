"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { api, isApiPlanLimitError, type WorkspaceTimelineEvent } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace-context";

function fmtNum(n: number): string {
  if (!Number.isFinite(n)) return "—";
  const a = Math.abs(n);
  if (a >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (a >= 10_000) return `${(n / 1_000).toFixed(1)}K`;
  if (a >= 1_000) return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function eventTypeLabel(t: string): string {
  if (t === "upload") return "Import";
  if (t === "briefing") return "Briefing";
  if (t === "append") return "Append";
  return t;
}

function MetricChips({ ev }: { ev: WorkspaceTimelineEvent }) {
  const kpis = ev.metrics?.kpis ?? [];
  const top = kpis.slice(0, 3);
  if (!top.length) {
    return (
      <p className="text-xs text-muted-foreground">
        {ev.metrics?.workspace_row_total != null
          ? `${ev.metrics.workspace_row_total.toLocaleString()} rows · metrics in snapshot are thin`
          : "No KPI totals in snapshot"}
      </p>
    );
  }
  return (
    <div className="flex flex-wrap gap-2">
      {top.map((k, i) => (
        <span
          key={i}
          className="inline-flex items-center rounded-md border border-border/80 bg-muted/40 px-2 py-0.5 text-[11px] tabular-nums"
        >
          <span className="text-muted-foreground mr-1">{k.label}:</span>
          <span className="font-semibold">{fmtNum(k.value)}</span>
        </span>
      ))}
    </div>
  );
}

export default function HistoryPage() {
  const { activeWorkspace, loading: wsLoading } = useWorkspace();
  const enabled = !wsLoading && Boolean(activeWorkspace?.id);

  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ["workspace-timeline", activeWorkspace?.id ?? "none"],
    queryFn: () => api.getWorkspaceTimeline(),
    enabled,
  });

  const events = data?.events ?? [];
  const [fromId, setFromId] = useState<string>("");
  const [toId, setToId] = useState<string>("");

  const compareEnabled =
    Boolean(fromId) && Boolean(toId) && fromId !== toId;

  const compareQuery = useQuery({
    queryKey: ["workspace-compare", fromId, toId],
    queryFn: () => api.compareWorkspaceSnapshots(fromId, toId),
    enabled: compareEnabled && enabled,
  });

  const defaultPair = useMemo(() => {
    if (events.length < 2) return null;
    return { older: events[events.length - 1], newer: events[0] };
  }, [events]);

  const recurring = data?.evolution?.recurring ?? [];
  const improving = data?.evolution?.improving ?? [];
  const digests = data?.digests ?? [];

  if (wsLoading || (!enabled && !activeWorkspace?.id)) {
    return (
      <div className="space-y-6 max-w-3xl">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-40 w-full rounded-2xl" />
      </div>
    );
  }

  if (isError && isApiPlanLimitError(error)) {
    return (
      <div className="max-w-lg space-y-4 rounded-2xl border border-border/80 bg-muted/20 p-6">
        <h1 className="text-lg font-semibold text-foreground">History & timeline</h1>
        <p className="text-sm text-muted-foreground leading-relaxed">{error.message}</p>
        <Link href="/pricing" className={cn(buttonVariants({ variant: "default" }))}>
          View plans
        </Link>
      </div>
    );
  }

  if (!activeWorkspace?.id) {
    return (
      <p className="text-sm text-muted-foreground">
        Select a workspace to view history.
      </p>
    );
  }

  return (
    <div className="dashboard-page max-w-5xl">
      <header className="dashboard-hero-card dashboard-inner-accent">
        <h1 className="text-[2.2rem] font-semibold leading-none tracking-[-0.04em] text-slate-900 dark:text-slate-50">
          History
        </h1>
        <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
          Imports, row appends, and briefings leave snapshots so you can see what changed—not
          a blank slate every time.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Link
            href="/dashboard"
            className="text-xs font-medium text-primary hover:underline"
          >
            ← Overview
          </Link>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 text-xs"
            onClick={() => void refetch()}
          >
            Refresh
          </Button>
        </div>
      </header>

      {isPending ? (
        <div className="space-y-3">
          <Skeleton className="h-24 rounded-2xl" />
          <Skeleton className="h-40 rounded-2xl" />
        </div>
      ) : isError ? (
        <Card className="dashboard-surface border-destructive/30">
          <CardContent className="py-6 text-sm text-destructive">
            {error instanceof Error ? error.message : "Could not load history"}
          </CardContent>
        </Card>
      ) : (
        <>
          {(recurring.length > 0 || improving.length > 0) && (
            <section className="space-y-3">
              <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                Insight evolution
              </h2>
              <div className="space-y-2">
                {recurring.map((r, i) => (
                  <div
                    key={`${r.theme_key}-${i}`}
                    className="rounded-xl border border-amber-200/80 bg-amber-50/50 px-3 py-2.5 text-sm dark:border-amber-900/40 dark:bg-amber-950/25"
                  >
                    <span className="text-[10px] font-semibold uppercase tracking-wide text-amber-900/80 dark:text-amber-400/90">
                      Recurring
                    </span>
                    <p className="mt-1 text-slate-800 dark:text-slate-100 leading-snug">
                      {r.narrative}
                    </p>
                  </div>
                ))}
                {improving.map((r, i) => (
                  <div
                    key={`${r.theme_key}-${i}`}
                    className="rounded-xl border border-emerald-200/80 bg-emerald-50/45 px-3 py-2.5 text-sm dark:border-emerald-900/40 dark:bg-emerald-950/25"
                  >
                    <span className="text-[10px] font-semibold uppercase tracking-wide text-emerald-900/80 dark:text-emerald-400/90">
                      Improving
                    </span>
                    <p className="mt-1 text-slate-800 dark:text-slate-100 leading-snug">
                      {r.narrative}
                    </p>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section className="space-y-3">
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              Compare snapshots
            </h2>
            <Card className="dashboard-surface overflow-hidden border-white/70 bg-white/78 dark:border-white/10 dark:bg-slate-950/45">
              <CardContent className="pt-5 space-y-4">
                {defaultPair && (
                  <p className="text-xs text-muted-foreground">
                    Tip: newest events are at the top. Compare an older import or briefing to
                    the latest to see KPI drift and row growth.
                  </p>
                )}
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <label className="text-[11px] font-medium text-muted-foreground block mb-1">
                      Earlier snapshot
                    </label>
                    <select
                      className="w-full rounded-lg border border-input bg-background px-2 py-2 text-sm"
                      value={fromId}
                      onChange={(e) => setFromId(e.target.value)}
                    >
                      <option value="">Select…</option>
                      {[...events].reverse().map((ev) => (
                        <option key={ev.id} value={ev.id}>
                          {ev.created_at?.slice(0, 10)} · {eventTypeLabel(ev.event_type)} ·{" "}
                          {ev.display_label.slice(0, 40)}
                          {ev.display_label.length > 40 ? "…" : ""}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-[11px] font-medium text-muted-foreground block mb-1">
                      Later snapshot
                    </label>
                    <select
                      className="w-full rounded-lg border border-input bg-background px-2 py-2 text-sm"
                      value={toId}
                      onChange={(e) => setToId(e.target.value)}
                    >
                      <option value="">Select…</option>
                      {events.map((ev) => (
                        <option key={`to-${ev.id}`} value={ev.id}>
                          {ev.created_at?.slice(0, 10)} · {eventTypeLabel(ev.event_type)} ·{" "}
                          {ev.display_label.slice(0, 40)}
                          {ev.display_label.length > 40 ? "…" : ""}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                {defaultPair && (!fromId || !toId) && (
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="text-xs"
                    onClick={() => {
                      setFromId(defaultPair.older.id);
                      setToId(defaultPair.newer.id);
                    }}
                  >
                    Use oldest vs newest in list
                  </Button>
                )}
                {compareQuery.isSuccess && compareQuery.data && (
                  <div className="dashboard-surface-muted space-y-2 px-3 py-3 text-sm">
                    <p className="font-medium text-foreground">
                      Rows: {compareQuery.data.workspace_row_previous.toLocaleString()} →{" "}
                      {compareQuery.data.workspace_row_current.toLocaleString()}
                      {compareQuery.data.workspace_row_delta !== 0 && (
                        <span
                          className={
                            compareQuery.data.workspace_row_delta > 0
                              ? " text-emerald-600 dark:text-emerald-400"
                              : " text-red-600 dark:text-red-400"
                          }
                        >
                          {" "}
                          ({compareQuery.data.workspace_row_delta > 0 ? "+" : ""}
                          {compareQuery.data.workspace_row_delta})
                        </span>
                      )}
                    </p>
                    {compareQuery.data.kpi_changes.length === 0 ? (
                      <p className="text-xs text-muted-foreground">
                        No overlapping KPI labels to diff—imports may use different schemas.
                      </p>
                    ) : (
                      <ul className="list-none m-0 p-0 space-y-1.5">
                        {compareQuery.data.kpi_changes.map((ch, i) => (
                          <li key={i} className="text-xs sm:text-sm leading-snug">
                            <span className="font-medium">{ch.label}</span>
                            {ch.dataset_name ? (
                              <span className="text-muted-foreground"> · {ch.dataset_name}</span>
                            ) : null}
                            : {fmtNum(ch.previous_value)} → {fmtNum(ch.current_value)}
                            <span
                              className={
                                ch.direction === "up"
                                  ? " text-emerald-600 dark:text-emerald-400"
                                  : ch.direction === "down"
                                    ? " text-red-600 dark:text-red-400"
                                    : ""
                              }
                            >
                              {" "}
                              ({ch.delta_pct > 0 ? "+" : ""}
                              {ch.delta_pct}%)
                            </span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
                {compareQuery.isError && (
                  <p className="text-xs text-destructive">
                    {compareQuery.error instanceof Error
                      ? compareQuery.error.message
                      : "Compare failed"}
                  </p>
                )}
              </CardContent>
            </Card>
          </section>

          <section className="space-y-3">
            <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
              Timeline
            </h2>
            {events.length === 0 ? (
              <Card className="dashboard-surface border-white/70 bg-white/75 dark:border-white/10 dark:bg-slate-950/45">
                <CardContent className="py-8 text-sm text-muted-foreground">
                  No snapshots yet. Import a file or run a workspace briefing—they are recorded
                  automatically from here on. Existing activity may appear after the next app
                  restart (one-time backfill).
                </CardContent>
              </Card>
            ) : (
              <ul className="space-y-2 list-none m-0 p-0">
                {events.map((ev) => (
                  <li key={ev.id}>
                    <Card className="shadow-sm border-slate-200/85 dark:border-slate-800">
                      <CardContent className="py-3.5 px-4">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="outline" className="text-[10px]">
                            {eventTypeLabel(ev.event_type)}
                          </Badge>
                          {ev.metrics?.snapshot_quality === "backfill" && (
                            <span className="text-[10px] text-muted-foreground">
                              Backfilled
                            </span>
                          )}
                          <time
                            dateTime={ev.created_at ?? undefined}
                            className="text-[11px] text-muted-foreground ml-auto"
                          >
                            {ev.created_at?.replace("T", " ").slice(0, 16) ?? ""}
                          </time>
                        </div>
                        <p className="mt-2 text-sm font-semibold text-foreground">
                          {ev.display_label}
                        </p>
                        <p className="text-xs text-muted-foreground mt-1">
                          {ev.metrics?.workspace_row_total != null
                            ? `${ev.metrics.workspace_row_total.toLocaleString()} rows · ${ev.metrics.dataset_count ?? 0} source(s) in snapshot`
                            : ""}
                        </p>
                        <div className="mt-2">
                          <MetricChips ev={ev} />
                        </div>
                        {ev.themes?.priority_titles &&
                          ev.themes.priority_titles.length > 0 && (
                            <p className="mt-2 text-xs text-slate-600 dark:text-slate-400 leading-snug">
                              Briefing priorities:{" "}
                              {ev.themes.priority_titles.slice(0, 3).join(" · ")}
                            </p>
                          )}
                      </CardContent>
                    </Card>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {digests.length > 0 && (
            <section className="space-y-3">
              <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                Stored summaries
              </h2>
              <ul className="space-y-2 list-none m-0 p-0">
                {digests.map((d) => (
                  <li
                    key={d.id}
                    className="rounded-xl border border-border/80 bg-card/60 px-3 py-2.5 text-sm"
                  >
                    <span className="text-[10px] font-semibold uppercase text-muted-foreground">
                      {d.kind} · {d.period_label}
                    </span>
                    <p className="mt-1 text-foreground leading-snug">{d.headline}</p>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}
