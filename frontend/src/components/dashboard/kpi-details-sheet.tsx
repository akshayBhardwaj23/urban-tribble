"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import type { KpiDrillDownDetails } from "@/lib/kpi-drill-down";

function Row({
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
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
        {label}
      </p>
      <div
        className={cn(
          "mt-1 text-sm leading-relaxed text-slate-800 dark:text-slate-100",
          mono && "font-mono text-xs text-slate-600 dark:text-slate-300 wrap-break-word"
        )}
      >
        {children}
      </div>
    </div>
  );
}

export function KpiDetailsBody({ d }: { d: KpiDrillDownDetails }) {
  return (
    <div className="space-y-5 text-left">
      <Row label="Definition">{d.definition}</Row>
      {d.formula_summary ? (
        <Row label="Calculation" mono>
          {d.formula_summary}
        </Row>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <Row label="Source file">{d.source_file}</Row>
        <Row label="Rows in scope">
          {d.row_count > 0
            ? d.row_count.toLocaleString()
            : "— (see definition for scope)"}
        </Row>
        <Row label="Date range">{d.date_range_label}</Row>
        <Row label="Date column (filter)">
          {d.date_column ? (
            <span className="font-mono text-xs">{d.date_column}</span>
          ) : (
            <span className="text-slate-500">Not applied</span>
          )}
        </Row>
      </div>
      {d.aggregation ? (
        <Row label="Aggregation">{d.aggregation}</Row>
      ) : null}
      {d.source_column ? (
        <Row label="Source column" mono>
          {d.source_column}
        </Row>
      ) : null}
      {d.columns_used.length > 0 ? (
        <Row label="Columns used" mono>
          {d.columns_used.join(", ")}
        </Row>
      ) : null}
    </div>
  );
}

export function KpiDetailsSheet({
  details,
  metricLabel,
  className,
}: {
  details: KpiDrillDownDetails;
  /** Tile title for dialog header */
  metricLabel: string;
  className?: string;
}) {
  return (
    <Dialog>
      <DialogTrigger
        render={
          <Button
            variant="ghost"
            size="sm"
            className={cn(
              "h-7 px-2 text-[11px] font-medium text-slate-500 hover:text-slate-800 dark:hover:text-slate-100 -ml-2",
              className
            )}
          />
        }
      >
        See basis
      </DialogTrigger>
      <DialogContent
        showCloseButton
        className="max-h-[min(90dvh,36rem)] w-full max-w-md gap-0 overflow-hidden border-slate-200/90 p-0 shadow-xl dark:border-slate-800 sm:max-w-lg"
      >
        <DialogHeader className="border-b border-slate-100 px-5 py-4 dark:border-slate-800">
          <DialogTitle className="text-base font-semibold leading-snug pr-8">
            {metricLabel}
          </DialogTitle>
          <p className="text-xs text-muted-foreground mt-1 font-normal">
            Where this number comes from
          </p>
        </DialogHeader>
        <div className="max-h-[min(70dvh,28rem)] overflow-y-auto px-5 py-4">
          <KpiDetailsBody d={details} />
        </div>
      </DialogContent>
    </Dialog>
  );
}
