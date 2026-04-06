"use client";

import Link from "next/link";
import type { WorkspaceUsage, WorkspaceUsageMeterDetail } from "@/lib/api";
import { cn } from "@/lib/utils";

function MiniMeter({ meter }: { meter: WorkspaceUsageMeterDetail }) {
  const w = Math.min(100, Math.max(0, meter.pct));
  const hot = meter.approaching;
  return (
    <span className="inline-flex items-center gap-1.5 align-middle">
      <span
        className="relative h-1.5 w-14 overflow-hidden rounded-full bg-muted dark:bg-slate-800"
        aria-hidden
      >
        <span
          className={cn(
            "absolute left-0 top-0 h-full rounded-full transition-[width]",
            hot
              ? "bg-amber-500/90 dark:bg-amber-500/80"
              : "bg-primary/55 dark:bg-primary/50"
          )}
          style={{ width: `${w}%` }}
        />
      </span>
    </span>
  );
}

function MeterLine({
  label,
  meter,
}: {
  label: string;
  meter: WorkspaceUsageMeterDetail | null;
}) {
  if (!meter) {
    return (
      <span className="text-muted-foreground">
        {label}: <span className="text-foreground/85 font-medium">Unlimited</span>
      </span>
    );
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-muted-foreground">
      <span>
        {label}:{" "}
        <span className="tabular-nums text-foreground/90 font-medium">
          {meter.used}/{meter.limit}
        </span>
        <span className="text-muted-foreground/90"> this month</span>
      </span>
      <MiniMeter meter={meter} />
    </span>
  );
}

export function WorkspaceUsageStrip({
  usage,
  className,
}: {
  usage: WorkspaceUsage | undefined;
  className?: string;
}) {
  if (!usage) return null;

  return (
    <div
      className={cn(
        "dashboard-surface-muted px-3 py-3 sm:px-4",
        className
      )}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between sm:gap-x-6 sm:gap-y-2">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[11px] sm:text-xs">
          <span className="rounded-md border border-border/70 bg-background/60 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-foreground/80">
            {usage.plan_label}
          </span>
          <MeterLine label="Analyses" meter={usage.meters.analyses} />
          <span className="hidden sm:inline text-border/80" aria-hidden>
            ·
          </span>
          <MeterLine label="Uploads" meter={usage.meters.uploads} />
        </div>
        <p className="text-[11px] text-muted-foreground leading-snug sm:max-w-[20rem] sm:text-right">
          {usage.history.summary}
        </p>
      </div>
      {usage.nudges.length > 0 && (
        <ul className="mt-2.5 space-y-1.5 list-none m-0 p-0 border-t border-border/40 pt-2.5">
          {usage.nudges.map((n, i) => (
            <li key={i}>
              <Link
                href={n.href}
                className={cn(
                  "text-[11px] leading-snug transition-colors hover:text-foreground",
                  n.tone === "whisper"
                    ? "text-muted-foreground/85"
                    : "text-slate-600 dark:text-slate-400",
                  n.tone === "approaching" && "font-medium text-amber-800/95 dark:text-amber-200/90"
                )}
              >
                {n.message}
                <span className="text-muted-foreground/70"> · Plans</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
