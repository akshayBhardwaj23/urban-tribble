"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, type RecurringSummaryRecord } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace-context";

function SummaryBody({ row }: { row: RecurringSummaryRecord }) {
  const c = row.content;
  return (
    <div className="space-y-4">
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
          {row.period_label}
        </p>
        <p className="mt-1.5 text-sm font-semibold leading-snug text-slate-900 dark:text-slate-50">
          {c.headline}
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
            Key changes
          </p>
          <ul className="mt-2 list-disc space-y-1.5 pl-4 text-sm leading-relaxed text-slate-700 dark:text-slate-300">
            {(c.key_changes ?? []).slice(0, 4).map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        </div>
        <div className="space-y-3">
          <div className="rounded-xl border border-amber-200/80 bg-amber-50/40 px-3 py-2.5 dark:border-amber-900/40 dark:bg-amber-950/20">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-900/70 dark:text-amber-400/90">
              Biggest risk
            </p>
            <p className="mt-1 text-sm leading-relaxed text-slate-800 dark:text-slate-100">
              {c.biggest_risk}
            </p>
          </div>
          <div className="rounded-xl border border-emerald-200/80 bg-emerald-50/35 px-3 py-2.5 dark:border-emerald-900/40 dark:bg-emerald-950/20">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-emerald-900/70 dark:text-emerald-400/90">
              Biggest opportunity
            </p>
            <p className="mt-1 text-sm leading-relaxed text-slate-800 dark:text-slate-100">
              {c.biggest_opportunity}
            </p>
          </div>
        </div>
      </div>
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
          Recommended actions
        </p>
        <ol className="mt-2 list-decimal space-y-1.5 pl-4 text-sm font-medium leading-relaxed text-slate-800 dark:text-slate-100">
          {(c.recommended_actions ?? []).slice(0, 3).map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ol>
      </div>
      <p className="text-[11px] text-muted-foreground border-t border-slate-200/80 pt-3 dark:border-slate-800">
        Saved for history and comparison. Email delivery can plug into the stored HTML
        snapshot when you enable it—nothing sends automatically today.
      </p>
    </div>
  );
}

export function LatestSummaryCard({ className }: { className?: string }) {
  const { activeWorkspace, profile, loading: workspaceLoading } = useWorkspace();
  const plan = (profile?.subscription_plan ?? "free").toLowerCase();
  const proLike = plan === "pro" || plan === "internal";
  const canWeekly = proLike;
  const canMonthly = plan === "starter" || proLike;
  const queryClient = useQueryClient();
  const workspaceId = activeWorkspace?.id;
  const enabled = !workspaceLoading && Boolean(workspaceId);

  const { data, isPending, isFetching, refetch } = useQuery({
    queryKey: ["summaries-latest", workspaceId ?? "none"],
    queryFn: () => api.getSummariesLatest(),
    enabled,
  });

  const regenerate = useMutation({
    mutationFn: (kind: "weekly" | "monthly") =>
      api.generateSummary({ kind, force: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["summaries-latest"] });
    },
  });

  if (!enabled) return null;

  const showSkeleton = isPending && !data;

  return (
    <section className={className}>
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="dashboard-section-label">
            Latest summary
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5 max-w-xl">
            Calendar weekly and monthly digests—built to skim in under ten seconds.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="rounded-lg text-xs"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            {isFetching ? "Refreshing…" : "Refresh"}
          </Button>
        </div>
      </div>

      <Card className="dashboard-surface dashboard-inner-accent overflow-hidden border-white/70 bg-white/78 dark:border-white/10 dark:bg-slate-950/45">
        <CardContent className="p-0">
          {showSkeleton ? (
            <div className="p-6 space-y-4">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-20 w-full rounded-xl" />
              <div className="grid sm:grid-cols-2 gap-4">
                <Skeleton className="h-32 rounded-xl" />
                <Skeleton className="h-32 rounded-xl" />
              </div>
            </div>
          ) : (
            <Tabs defaultValue="weekly">
              <div className="flex flex-col gap-3 border-b border-white/65 bg-white/35 px-4 py-3 dark:border-white/10 dark:bg-slate-950/20 sm:flex-row sm:items-center sm:justify-between">
                <TabsList variant="line" className="bg-transparent p-0 h-auto gap-1">
                  <TabsTrigger
                    value="weekly"
                    className="rounded-full px-3 py-1.5 text-xs data-active:bg-white data-active:shadow-sm dark:data-active:bg-slate-900"
                  >
                    Weekly
                  </TabsTrigger>
                  <TabsTrigger
                    value="monthly"
                    className="rounded-full px-3 py-1.5 text-xs data-active:bg-white data-active:shadow-sm dark:data-active:bg-slate-900"
                  >
                    Monthly
                  </TabsTrigger>
                </TabsList>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-8 text-xs"
                    onClick={() => regenerate.mutate("weekly")}
                    disabled={regenerate.isPending || !canWeekly}
                    title={!canWeekly ? "Weekly summaries require Pro" : undefined}
                  >
                    Rebuild week
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-8 text-xs"
                    onClick={() => regenerate.mutate("monthly")}
                    disabled={regenerate.isPending || !canMonthly}
                    title={!canMonthly ? "Monthly summaries require a paid plan" : undefined}
                  >
                    Rebuild month
                  </Button>
                </div>
              </div>
              <TabsContent value="weekly" className="p-5 sm:p-6 mt-0">
                {data?.weekly ? (
                  <SummaryBody row={data.weekly} />
                ) : !canWeekly ? (
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    Weekly digests are included on{" "}
                    <Link href="/pricing" className="font-medium text-foreground underline-offset-4 hover:underline">
                      Pro
                    </Link>
                    .
                  </p>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No weekly summary yet—data may still be importing, or there are no
                    dated rows spanning the last full week versus the prior week.
                  </p>
                )}
              </TabsContent>
              <TabsContent value="monthly" className="p-5 sm:p-6 mt-0">
                {data?.monthly ? (
                  <SummaryBody row={data.monthly} />
                ) : !canMonthly ? (
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    Monthly summaries are on{" "}
                    <Link href="/pricing" className="font-medium text-foreground underline-offset-4 hover:underline">
                      Starter and Pro
                    </Link>
                    .
                  </p>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No monthly summary yet—needs dated history across the prior calendar month
                    and the month before that.
                  </p>
                )}
              </TabsContent>
            </Tabs>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
