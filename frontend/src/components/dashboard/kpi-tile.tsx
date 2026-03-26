"use client";

import { TrendingDown, TrendingUp } from "lucide-react";
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
}: {
  title: string;
  value: string;
  subtitle?: string;
  index?: number;
  /** "up" | "down" — if omitted, alternates by index for visual variety */
  trend?: "up" | "down";
}) {
  const trend =
    trendProp ?? (index % 3 === 1 ? "down" : "up");
  const Icon = trend === "up" ? TrendingUp : TrendingDown;

  return (
    <div
      className={cn(
        "flex min-h-[5.5rem] items-center gap-4 rounded-3xl border border-white/70",
        "bg-white/75 px-5 py-4 shadow-[0_8px_32px_-12px_rgba(91,76,255,0.12),0_4px_16px_-4px_rgba(15,23,42,0.08)]",
        "backdrop-blur-xl transition-shadow hover:shadow-[0_12px_40px_-12px_rgba(91,76,255,0.18)]"
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
        <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-slate-500">
          {title}
        </p>
        <p className="mt-1 text-2xl font-bold tabular-nums tracking-tight text-slate-900">
          {value}
        </p>
        {subtitle ? (
          <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>
        ) : null}
      </div>
    </div>
  );
}
