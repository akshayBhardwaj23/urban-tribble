"use client";

import { useState } from "react";
import { CalendarRange } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export type TimeframePresetId = "all" | "7d" | "14d" | "30d" | "60d" | "custom";

export type TimeframeValue =
  | { preset: "all" }
  | { preset: "7d" | "14d" | "30d" | "60d" }
  | { preset: "custom"; start: string; end: string };

const PRESETS: { id: Exclude<TimeframePresetId, "custom">; label: string }[] = [
  { id: "all", label: "All" },
  { id: "7d", label: "7d" },
  { id: "14d", label: "14d" },
  { id: "30d", label: "30d" },
  { id: "60d", label: "60d" },
];

function localYMD(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function parseYMDLocal(s: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s.trim());
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]) - 1;
  const d = Number(m[3]);
  const dt = new Date(y, mo, d);
  if (dt.getFullYear() !== y || dt.getMonth() !== mo || dt.getDate() !== d) return null;
  return dt;
}

function addCalendarDaysFromYMD(ymd: string, deltaDays: number): string {
  const d = parseYMDLocal(ymd);
  if (!d) return ymd;
  d.setDate(d.getDate() + deltaDays);
  return localYMD(d);
}

/**
 * Preset ranges end at the latest date in the dataset (not wall-clock “today”),
 * so historical exports still show data. Falls back to local today if no anchor.
 */
export function timeframeToQueryRange(
  value: TimeframeValue,
  opts?: { dataEnd?: string | null }
): { start?: string; end?: string } {
  if (value.preset === "all") {
    return {};
  }
  if (value.preset === "custom") {
    return { start: value.start, end: value.end };
  }
  const n = Number(value.preset.replace("d", ""));
  const anchor =
    opts?.dataEnd && /^\d{4}-\d{2}-\d{2}$/.test(opts.dataEnd)
      ? opts.dataEnd
      : localYMD(new Date());
  const start = addCalendarDaysFromYMD(anchor, -(n - 1));
  return { start, end: anchor };
}

function formatRangeLabel(start: string, end: string): string {
  const a = parseYMDLocal(start);
  const b = parseYMDLocal(end);
  if (!a || !b) return `${start} – ${end}`;
  return `${a.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })} – ${b.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}`;
}

export function TimeframeToolbar({
  value,
  onChange,
  hasDateColumn,
  appliedLabel,
  dataEnd,
  resolvedRange,
}: {
  value: TimeframeValue;
  onChange: (next: TimeframeValue) => void;
  hasDateColumn: boolean;
  /** From API `date_bounds.max` — previews custom / label fallback */
  dataEnd?: string | null;
  /** Actual range from API after load (`timeframe.start`/`end`) */
  resolvedRange?: { start: string; end: string } | null;
  /** From API: human hint when filter could not apply */
  appliedLabel?: string | null;
}) {
  const [customOpen, setCustomOpen] = useState(false);
  const [draftStart, setDraftStart] = useState("");
  const [draftEnd, setDraftEnd] = useState("");
  const [customError, setCustomError] = useState<string | null>(null);

  const active: TimeframePresetId = value.preset;
  const range =
    resolvedRange ??
    (hasDateColumn && active !== "all"
      ? timeframeToQueryRange(value, { dataEnd })
      : null);

  const openCustomDialog = () => {
    if (!hasDateColumn) return;
    const q = timeframeToQueryRange(
      value.preset === "custom"
        ? value
        : { preset: "30d" },
      { dataEnd }
    );
    setDraftStart(q.start ?? "");
    setDraftEnd(q.end ?? "");
    setCustomError(null);
    setCustomOpen(true);
  };

  const applyCustom = () => {
    const a = parseYMDLocal(draftStart);
    const b = parseYMDLocal(draftEnd);
    if (!a || !b) {
      setCustomError("Use a valid start and end date (YYYY-MM-DD).");
      return;
    }
    let start = localYMD(a);
    let end = localYMD(b);
    if (start > end) {
      const t = start;
      start = end;
      end = t;
    }
    setCustomError(null);
    onChange({ preset: "custom", start, end });
    setCustomOpen(false);
  };

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-slate-500">
            Analysis period
          </span>
          <div className="flex flex-wrap gap-1 rounded-2xl border border-slate-200/90 bg-white/80 p-1 shadow-sm">
            {PRESETS.map((p) => (
              <Button
                key={p.id}
                type="button"
                variant={active === p.id ? "default" : "ghost"}
                size="sm"
                disabled={!hasDateColumn && p.id !== "all"}
                className={cn(
                  "h-8 rounded-xl px-3 text-xs font-semibold",
                  active === p.id ? "" : "text-slate-600"
                )}
                title={
                  !hasDateColumn && p.id !== "all"
                    ? "No date field detected in this source"
                    : undefined
                }
                onClick={() => {
                  if (p.id === "all") onChange({ preset: "all" });
                  else if (hasDateColumn) onChange({ preset: p.id });
                }}
              >
                {p.label}
              </Button>
            ))}
            <Button
              type="button"
              variant={active === "custom" ? "default" : "ghost"}
              size="sm"
              disabled={!hasDateColumn}
              className={cn(
                "h-8 gap-1 rounded-xl px-3 text-xs font-semibold",
                active === "custom" ? "" : "text-slate-600"
              )}
              title={
                !hasDateColumn ? "No date field detected in this source" : undefined
              }
              onClick={openCustomDialog}
            >
              <CalendarRange className="h-3.5 w-3.5 opacity-80" />
              Custom
            </Button>
          </div>
        </div>
        {hasDateColumn ? (
          <p className="text-[11px] text-slate-400">
            Rolling windows (7d–60d) anchor to the{" "}
            <span className="font-medium text-slate-500">
              latest observation in the source
            </span>
            , not today’s calendar date.
          </p>
        ) : null}
      </div>
      {hasDateColumn && range?.start && range?.end ? (
        <p className="text-xs font-medium text-slate-500">
          {formatRangeLabel(range.start, range.end)}
        </p>
      ) : null}
      {appliedLabel ? (
        <p className="text-xs text-amber-700">{appliedLabel}</p>
      ) : null}

      <Dialog open={customOpen} onOpenChange={setCustomOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Custom period</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <div className="grid gap-1.5">
              <label className="text-xs font-medium text-slate-600">Start</label>
              <Input
                type="date"
                value={draftStart}
                onChange={(e) => setDraftStart(e.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <label className="text-xs font-medium text-slate-600">End</label>
              <Input
                type="date"
                value={draftEnd}
                onChange={(e) => setDraftEnd(e.target.value)}
              />
            </div>
            {customError ? (
              <p className="text-sm text-destructive">{customError}</p>
            ) : null}
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              type="button"
              variant="outline"
              onClick={() => setCustomOpen(false)}
            >
              Cancel
            </Button>
            <Button type="button" onClick={applyCustom}>
              Apply
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
