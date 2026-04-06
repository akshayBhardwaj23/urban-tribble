"use client";

import { TrendingDown, TrendingUp } from "lucide-react";
import { KpiDetailsSheet } from "@/components/dashboard/kpi-details-sheet";
import type { KpiDrillDownDetails } from "@/lib/kpi-drill-down";
import { cn } from "@/lib/utils";

const ACCENT_RINGS = [
  "from-[#FF8A5C] to-[#FF6B35]",
  "from-[#5B8CFF] to-[#3D6DEB]",
  "from-[#B08CFF] to-[#8B5CF6]",
  "from-[#3ECFC0] to-[#2AB3A6]",
  "from-[#FF7EC8] to-[#EC4899]",
];

export function DashboardKpiTile({
  title,
  value,
  subtitle,
  index = 0,
  trend: trendProp,
  details,
}: {
  title: string;
  value: string;
  subtitle?: string;
  index?: number;
  /** "up" | "down" — if omitted, alternates by index for visual variety */
  trend?: "up" | "down";
  /** Drill-down provenance (from API or client-built) */
  details?: KpiDrillDownDetails | null;
}) {
  const trend =
    trendProp ?? (index % 3 === 1 ? "down" : "up");
  const Icon = trend === "up" ? TrendingUp : TrendingDown;

  return (
    <div
      className={cn(
        "dashboard-kpi-card flex min-h-[7rem] items-center gap-4",
        "transition-shadow hover:shadow-[0_26px_46px_-32px_rgba(15,23,42,0.28)]"
      )}
    >
      <div
        className={cn(
          "flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-gradient-to-br shadow-lg",
          ACCENT_RINGS[index % ACCENT_RINGS.length]
        )}
      >
        <Icon className="h-6 w-6 text-white drop-shadow-sm" strokeWidth={2.25} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
          {title}
        </p>
        <p className="mt-1.5 text-[1.75rem] font-bold tracking-tight text-foreground tabular-nums">
          {value}
        </p>
        {subtitle ? (
          <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p>
        ) : null}
        {details ? (
          <div className="mt-3 border-t border-border/60 pt-2">
            <KpiDetailsSheet details={details} metricLabel={title} />
          </div>
        ) : null}
      </div>
    </div>
  );
}
