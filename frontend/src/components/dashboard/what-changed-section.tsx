"use client";

import { cn } from "@/lib/utils";

export interface WhatChangedItem {
  label: string;
  direction: string;
  arrow: string;
  delta_pct: number | null;
  previous_value: number;
  current_value: number;
  explanation: string;
  higher_is_better?: boolean;
  is_favorable?: boolean;
  source_dataset?: string;
}

export interface WhatChangedPayload {
  available: boolean;
  period_description: string;
  items: WhatChangedItem[];
  highlights: WhatChangedItem[];
  cross_metric_note?: string | null;
}

function toneForItem(item: WhatChangedItem): "good" | "bad" | "neutral" {
  if (item.direction === "flat") return "neutral";
  if (item.is_favorable === true) return "good";
  if (item.is_favorable === false) return "bad";
  return "neutral";
}

export function WhatChangedSection({
  block,
  className,
}: {
  block: WhatChangedPayload | null | undefined;
  className?: string;
}) {
  if (!block?.available || !block.highlights?.length) {
    return (
      <section
        className={cn(
          "rounded-2xl border border-slate-200/90 bg-linear-to-br from-slate-50/90 to-white dark:from-slate-950/80 dark:to-slate-900/40 dark:border-slate-800 px-5 py-4 shadow-sm",
          className
        )}
      >
        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
          What changed
        </p>
        <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
          Add a dated column and at least one amount column to compare this period with the last.
          After the next import, we can show revenue, spend, and margin movement here.
        </p>
      </section>
    );
  }

  const { highlights, cross_metric_note, period_description } = block;

  return (
    <section
      className={cn(
        "rounded-2xl border-2 border-primary/20 bg-linear-to-br from-primary/6 via-white to-slate-50/90 dark:from-primary/10 dark:via-slate-950/60 dark:to-slate-900/50 dark:border-primary/25 px-5 py-5 shadow-md",
        className
      )}
    >
      <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-primary">
            What changed
          </p>
          <h2 className="mt-1 text-lg font-semibold tracking-tight text-slate-900 dark:text-slate-50">
            Since last period
          </h2>
        </div>
        {period_description ? (
          <p className="text-[11px] text-muted-foreground max-w-md text-right leading-snug">
            {period_description}
          </p>
        ) : null}
      </div>

      <ul className="mt-4 space-y-3">
        {highlights.slice(0, 3).map((item, i) => {
          const tone = toneForItem(item);
          const border =
            tone === "good"
              ? "border-emerald-200/80 dark:border-emerald-900/50"
              : tone === "bad"
                ? "border-amber-200/90 dark:border-amber-900/45"
                : "border-slate-200/80 dark:border-slate-700/80";
          return (
            <li
              key={`${item.label}-${i}`}
              className={cn(
                "flex gap-3 rounded-xl border bg-white/85 dark:bg-slate-950/35 px-4 py-3 backdrop-blur-sm",
                border
              )}
            >
              <div
                className={cn(
                  "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-lg font-semibold tabular-nums",
                  tone === "good" && "bg-emerald-100/90 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300",
                  tone === "bad" && "bg-amber-100/90 text-amber-900 dark:bg-amber-950/40 dark:text-amber-200",
                  tone === "neutral" && "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200"
                )}
                aria-hidden
              >
                {item.arrow}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                  <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    {item.label}
                  </span>
                  {item.delta_pct != null && item.direction !== "flat" ? (
                    <span className="text-sm font-medium tabular-nums text-slate-700 dark:text-slate-300">
                      {item.delta_pct > 0 ? "+" : ""}
                      {item.delta_pct}%
                    </span>
                  ) : null}
                  {item.source_dataset ? (
                    <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                      · {item.source_dataset}
                    </span>
                  ) : null}
                </div>
                <p className="mt-1 text-sm leading-relaxed text-slate-700 dark:text-slate-300">
                  {item.explanation}
                </p>
              </div>
            </li>
          );
        })}
      </ul>

      {cross_metric_note ? (
        <p className="mt-4 text-sm leading-relaxed text-slate-700 dark:text-slate-300 border-t border-slate-200/80 dark:border-slate-800 pt-3">
          <span className="font-medium text-slate-900 dark:text-slate-100">Read: </span>
          {cross_metric_note}
        </p>
      ) : null}
    </section>
  );
}
