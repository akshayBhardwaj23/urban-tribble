"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  priorityBadgeClass,
} from "@/lib/top-priorities";
import type { PlanLimitDetail, WorkspaceRecommendedAction } from "@/lib/api";
import { cn } from "@/lib/utils";

function priorityLabel(p: WorkspaceRecommendedAction["priority"]): string {
  return p === "high" ? "High" : p === "medium" ? "Medium" : "Low";
}

function sourceLabel(s: string): string {
  if (s === "briefing") return "Briefing";
  if (s === "signal") return "Signal";
  if (s === "data_quality") return "Data";
  return s;
}

function stripeClass(p: WorkspaceRecommendedAction["priority"]): string {
  if (p === "high") return "bg-rose-500";
  if (p === "medium") return "bg-amber-500";
  return "bg-slate-400 dark:bg-slate-500";
}

export function RecommendedActionsSection({
  items,
  briefingAvailable,
  onRunBriefing,
  briefingBusy,
  analysesCapDetail,
  className,
}: {
  items: WorkspaceRecommendedAction[];
  briefingAvailable: boolean;
  onRunBriefing: () => void;
  briefingBusy: boolean;
  /** When set, workspace briefing cannot run until the next period or an upgrade. */
  analysesCapDetail?: PlanLimitDetail | null;
  className?: string;
}) {
  const sorted = [...items].sort((a, b) => {
    const o = { high: 0, medium: 1, low: 2 };
    return o[a.priority] - o[b.priority];
  });

  return (
    <section className={cn("space-y-3", className)}>
      <div>
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
          Recommended actions
        </h2>
        <p className="text-xs text-muted-foreground mt-0.5 max-w-2xl leading-relaxed">
          Concrete moves you can assign—sourced from your briefing, live signals, and
          period comparisons. Not generic advice.
        </p>
      </div>

      {sorted.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-200/90 bg-slate-50/50 px-4 py-5 dark:border-slate-800 dark:bg-slate-950/30">
          <p className="text-sm text-slate-700 dark:text-slate-200 font-medium">
            No prioritized actions yet.
          </p>
          <p className="text-xs text-muted-foreground mt-1.5 max-w-lg leading-relaxed">
            {briefingAvailable
              ? "Run or re-run a workspace briefing so model-backed moves appear here, or wait for sharper period-over-period signals from your data."
              : "Import data, then run a workspace briefing—the action list anchors on what the briefing and metrics surface."}
          </p>
          {!briefingAvailable && analysesCapDetail ? (
            <p className="text-xs text-muted-foreground mt-3 max-w-lg leading-relaxed">
              Workspace briefings use an analysis run from your plan allowance, and yours is
              currently full. Use the plan notice above this section or{" "}
              <Link
                href="/pricing"
                className="font-medium text-foreground underline underline-offset-2"
              >
                view pricing
              </Link>{" "}
              to continue.
            </p>
          ) : !briefingAvailable ? (
            <Button
              type="button"
              size="sm"
              className="mt-3 rounded-lg"
              onClick={onRunBriefing}
              disabled={briefingBusy}
            >
              {briefingBusy ? "Running…" : "Run workspace briefing"}
            </Button>
          ) : null}
        </div>
      ) : (
        <ol className="list-none m-0 p-0 space-y-2">
          {sorted.map((item, index) => (
            <li
              key={item.id}
              className="relative overflow-hidden rounded-2xl border border-slate-200/85 bg-white/90 shadow-sm dark:border-slate-800 dark:bg-slate-950/50"
            >
              <span
                className={cn(
                  "absolute left-0 top-0 bottom-0 w-1",
                  stripeClass(item.priority)
                )}
                aria-hidden
              />
              <div className="pl-4 pr-4 py-3 sm:pl-5 flex gap-3">
                <span
                  className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-slate-200/90 bg-slate-50 text-xs font-bold text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                  aria-hidden
                >
                  {index + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2 gap-y-1">
                    <Badge
                      variant="outline"
                      className={cn(
                        "text-[10px] font-semibold",
                        priorityBadgeClass(item.priority)
                      )}
                    >
                      {priorityLabel(item.priority)}
                    </Badge>
                    <span className="text-[10px] text-muted-foreground font-medium uppercase tracking-wide">
                      {sourceLabel(item.source)}
                    </span>
                  </div>
                  <p className="mt-2 text-sm font-medium leading-snug text-slate-900 dark:text-slate-50">
                    {item.action}
                  </p>
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
