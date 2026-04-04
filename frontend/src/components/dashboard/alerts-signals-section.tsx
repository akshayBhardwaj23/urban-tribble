"use client";

import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { WorkspaceAlert } from "@/lib/api";
import { cn } from "@/lib/utils";

const PRI_ORDER: Record<WorkspaceAlert["priority"], number> = {
  high: 0,
  medium: 1,
  low: 2,
};

const CAT_ORDER: Record<WorkspaceAlert["category"], number> = {
  risk: 0,
  data_issue: 1,
  efficiency: 2,
  opportunity: 3,
};

function categoryLabel(c: WorkspaceAlert["category"]): string {
  switch (c) {
    case "risk":
      return "Risk";
    case "opportunity":
      return "Opportunity";
    case "data_issue":
      return "Data issue";
    case "efficiency":
      return "Efficiency";
    default:
      return c;
  }
}

function priorityLabel(p: WorkspaceAlert["priority"]): string {
  return p === "high" ? "High" : p === "medium" ? "Medium" : "Low";
}

function sourceHint(s: WorkspaceAlert["source"]): string {
  if (s === "signal") return "Live signal";
  if (s === "data_quality") return "Data scan";
  return "Briefing";
}

function priorityStripe(p: WorkspaceAlert["priority"]): string {
  if (p === "high") return "bg-red-500 dark:bg-red-500";
  if (p === "medium") return "bg-amber-500 dark:bg-amber-500";
  return "bg-slate-400 dark:bg-slate-500";
}

type SortMode = "urgency" | "category";

export function AlertsSignalsSection({
  alerts,
  briefingReady,
  className,
}: {
  alerts: WorkspaceAlert[];
  /** True if workspace AI briefing has been run at least once (for empty state copy). */
  briefingReady: boolean;
  className?: string;
}) {
  const [sortMode, setSortMode] = useState<SortMode>("urgency");

  const sorted = useMemo(() => {
    const copy = [...alerts];
    if (sortMode === "urgency") {
      copy.sort((a, b) => {
        const dp = PRI_ORDER[a.priority] - PRI_ORDER[b.priority];
        if (dp !== 0) return dp;
        return CAT_ORDER[a.category] - CAT_ORDER[b.category];
      });
    } else {
      copy.sort((a, b) => {
        const dc = CAT_ORDER[a.category] - CAT_ORDER[b.category];
        if (dc !== 0) return dc;
        return PRI_ORDER[a.priority] - PRI_ORDER[b.priority];
      });
    }
    return copy;
  }, [alerts, sortMode]);

  return (
    <section className={cn("space-y-3", className)}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
            Alerts &amp; signals
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5 max-w-xl">
            Thresholds, data checks, and briefing flags—sorted by what needs attention first.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[11px] text-muted-foreground whitespace-nowrap">
            Sort
          </span>
          <div className="flex rounded-lg border border-border bg-muted/40 p-0.5">
            <Button
              type="button"
              variant={sortMode === "urgency" ? "secondary" : "ghost"}
              size="sm"
              className="h-7 rounded-md px-2.5 text-xs"
              onClick={() => setSortMode("urgency")}
            >
              Urgency
            </Button>
            <Button
              type="button"
              variant={sortMode === "category" ? "secondary" : "ghost"}
              size="sm"
              className="h-7 rounded-md px-2.5 text-xs"
              onClick={() => setSortMode("category")}
            >
              Category
            </Button>
          </div>
        </div>
      </div>

      {sorted.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-200/90 bg-slate-50/40 px-5 py-6 dark:border-slate-800 dark:bg-slate-950/30">
          <p className="text-sm text-slate-700 dark:text-slate-200 font-medium">
            No active alerts on this pass.
          </p>
          <p className="text-xs text-muted-foreground mt-2 leading-relaxed max-w-lg">
            {briefingReady
              ? "Numbers are stable versus thresholds, or date coverage is too thin to compare. Refresh data or widen the history to re-run scans."
              : "Run a workspace briefing—combined with live scans, that surfaces risks, upside, and data quality you should act on."}
          </p>
        </div>
      ) : (
        <ul className="space-y-2.5 list-none p-0 m-0">
          {sorted.map((a) => (
            <li
              key={a.id}
              className={cn(
                "relative overflow-hidden rounded-2xl border border-slate-200/85 bg-white/85 pl-1 shadow-sm",
                "dark:border-slate-800 dark:bg-slate-950/45"
              )}
            >
              <span
                className={cn(
                  "absolute left-0 top-0 bottom-0 w-1",
                  priorityStripe(a.priority)
                )}
                aria-hidden
              />
              <div className="pl-4 pr-4 py-3.5 sm:pl-5">
                <div className="flex flex-wrap items-center gap-2 gap-y-1.5">
                  <Badge
                    variant={
                      a.priority === "high" ? "destructive" : "secondary"
                    }
                    className="text-[10px] font-semibold uppercase tracking-wide"
                  >
                    {priorityLabel(a.priority)}
                  </Badge>
                  <Badge variant="outline" className="text-[10px] font-medium">
                    {categoryLabel(a.category)}
                  </Badge>
                  <span className="text-[10px] text-muted-foreground ml-auto sm:ml-0">
                    {sourceHint(a.source)}
                  </span>
                </div>
                <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-slate-50 leading-snug">
                  {a.title}
                </p>
                <p className="mt-1.5 text-sm text-slate-600 dark:text-slate-300 leading-relaxed">
                  {a.detail}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
