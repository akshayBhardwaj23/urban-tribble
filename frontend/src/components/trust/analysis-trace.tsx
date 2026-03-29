"use client";

import { useId } from "react";
import { CircleHelp, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import type { AnalysisTraceContext } from "@/lib/traceability";

function TraceField({
  label,
  children,
  mono,
}: {
  label: string;
  children: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
        {label}
      </dt>
      <dd
        className={cn(
          "mt-1 text-sm leading-relaxed text-slate-800 dark:text-slate-100",
          mono && "font-mono text-xs text-slate-600 dark:text-slate-300"
        )}
      >
        {children}
      </dd>
    </div>
  );
}

export function TraceDetailsBody({
  context,
  extraHeadline,
}: {
  context: AnalysisTraceContext;
  /** e.g. metric name or "Insight #2" */
  extraHeadline?: string;
}) {
  return (
    <div className="space-y-5 text-left">
      {extraHeadline ? (
        <p className="text-xs font-medium text-slate-600 dark:text-slate-300 border-b border-slate-100 dark:border-slate-800 pb-3">
          {extraHeadline}
        </p>
      ) : null}

      <dl className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <TraceField label="Scope">{context.scopeSubtitle ?? context.scopeTitle}</TraceField>
        </div>

        <div className="sm:col-span-2 space-y-2">
          <TraceField label="Source files">
            <ul className="list-none space-y-2">
              {context.sourceFiles.length === 0 ? (
                <li className="text-slate-500">Not specified</li>
              ) : (
                context.sourceFiles.map((f, i) => (
                  <li key={i} className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2 dark:border-slate-800 dark:bg-slate-900/40">
                    <span className="font-medium text-slate-900 dark:text-slate-50">
                      {f.name}
                    </span>
                    {f.sheetName ? (
                      <span className="block text-xs text-slate-500 mt-0.5">
                        Sheet · {f.sheetName}
                      </span>
                    ) : null}
                    <span className="block text-[11px] text-slate-500 mt-1 tabular-nums">
                      {f.rowCount != null
                        ? `${f.rowCount.toLocaleString()} rows`
                        : ""}
                      {f.rowCount != null && f.columnCount != null ? " · " : ""}
                      {f.columnCount != null
                        ? `${f.columnCount} columns`
                        : ""}
                    </span>
                  </li>
                ))
              )}
            </ul>
          </TraceField>
        </div>

        {context.columnsInScope.length > 0 ? (
          <div className="sm:col-span-2">
            <TraceField label="Columns in scope" mono>
              <span className="block wrap-break-word">
                {context.columnsInScope.join(", ")}
              </span>
            </TraceField>
          </div>
        ) : null}

        {context.dateRangeLabel ? (
          <TraceField label="Date range analyzed">
            {context.dateRangeLabel}
          </TraceField>
        ) : null}

        {context.rowBasisLabel ? (
          <TraceField label="Row basis">{context.rowBasisLabel}</TraceField>
        ) : null}

        {context.modelLabel ? (
          <div className="sm:col-span-2">
            <TraceField label="Model">{context.modelLabel}</TraceField>
          </div>
        ) : null}

        <div className="sm:col-span-2">
          <TraceField label="How we built this">{context.methodNote}</TraceField>
        </div>
      </dl>

      {context.assumptions.length > 0 ? (
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500 mb-2">
            Assumptions
          </p>
          <ul className="list-disc pl-4 space-y-1.5 text-xs text-slate-600 dark:text-slate-300">
            {context.assumptions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {context.caveats.length > 0 ? (
        <div className="rounded-lg border border-amber-200/80 bg-amber-50/50 px-3 py-2.5 dark:border-amber-900/40 dark:bg-amber-950/25">
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-900/80 dark:text-amber-200/90 mb-1.5">
            Caveats
          </p>
          <ul className="list-disc pl-4 space-y-1 text-xs text-amber-950/90 dark:text-amber-100/90">
            {context.caveats.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

/** Collapsible block — default closed; keeps the page clean. */
export function TraceCollapsible({
  context,
  summaryHint,
  className,
}: {
  context: AnalysisTraceContext;
  /** Short line visible next to the chevron */
  summaryHint?: string;
  className?: string;
}) {
  const id = useId();
  return (
    <details
      className={cn(
        "group rounded-xl border border-slate-200/80 bg-white/60 shadow-sm dark:border-slate-800 dark:bg-slate-950/30",
        className
      )}
    >
      <summary
        className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-left outline-none hover:bg-slate-50/80 dark:hover:bg-slate-900/40 rounded-xl [&::-webkit-details-marker]:hidden"
        aria-controls={`${id}-trace`}
      >
        <span className="flex min-w-0 items-center gap-2">
          <ShieldCheck
            className="h-4 w-4 shrink-0 text-slate-400"
            aria-hidden
          />
          <span className="min-w-0">
            <span className="text-sm font-medium text-slate-800 dark:text-slate-100">
              What fed this briefing
            </span>
            {summaryHint ? (
              <span className="mt-0.5 block text-xs text-slate-500 truncate">
                {summaryHint}
              </span>
            ) : null}
          </span>
        </span>
        <span
          className="text-slate-400 text-xs shrink-0 transition-transform group-open:rotate-180"
          aria-hidden
        >
          ▾
        </span>
      </summary>
      <div
        id={`${id}-trace`}
        className="border-t border-slate-100 px-4 py-4 dark:border-slate-800"
      >
        <TraceDetailsBody context={context} />
      </div>
    </details>
  );
}

export function TraceVerifyDialog({
  context,
  triggerLabel = "View source",
  title = "Basis for this read",
  extraHeadline,
  size = "default",
}: {
  context: AnalysisTraceContext;
  triggerLabel?: string;
  title?: string;
  extraHeadline?: string;
  size?: "default" | "sm";
}) {
  return (
    <Dialog>
      <DialogTrigger
        render={
          <Button
            variant="ghost"
            size={size === "sm" ? "sm" : "default"}
            className={cn(
              "h-auto gap-1.5 px-2 py-1 text-xs font-medium text-slate-500 hover:text-slate-800 dark:hover:text-slate-100",
              size === "sm" && "px-1.5 py-0.5"
            )}
          />
        }
      >
        <CircleHelp className="h-3.5 w-3.5 opacity-70" aria-hidden />
        {triggerLabel}
      </DialogTrigger>
      <DialogContent
        className="sm:max-w-lg max-h-[min(85vh,36rem)] overflow-y-auto gap-0 p-0"
        showCloseButton
      >
        <DialogHeader className="px-5 pt-5 pb-3 border-b border-slate-100 dark:border-slate-800">
          <DialogTitle className="text-base pr-8">{title}</DialogTitle>
        </DialogHeader>
        <div className="px-5 py-4">
          <TraceDetailsBody context={context} extraHeadline={extraHeadline} />
        </div>
      </DialogContent>
    </Dialog>
  );
}
