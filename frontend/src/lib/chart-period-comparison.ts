import { parseISODateLocal } from "@/lib/chart-dates";

export type PeriodComparison = {
  available: boolean;
  description?: string;
  current?: { start: string; end: string } | null;
  previous?: { start: string; end: string } | null;
};

/** Short legend label, e.g. "Apr 16 – May 15, '25". */
export function formatPeriodRangeLabel(start: string, end: string): string {
  const a = parseISODateLocal(start);
  const b = parseISODateLocal(end);
  if (!a || !b) return `${start} – ${end}`;
  const opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
  const endOpts: Intl.DateTimeFormatOptions = {
    month: "short",
    day: "numeric",
    year: a.getFullYear() === b.getFullYear() ? undefined : "2-digit",
  };
  const startStr = a.toLocaleDateString("en-US", opts);
  const endStr = b.toLocaleDateString("en-US", endOpts);
  if (a.getTime() === b.getTime()) return startStr;
  return `${startStr} – ${endStr}`;
}

export function seriesLabelsFromComparison(pc: PeriodComparison | null | undefined): {
  current: string;
  previous: string;
} | null {
  if (!pc?.available || !pc.current || !pc.previous) return null;
  return {
    current: formatPeriodRangeLabel(pc.current.start, pc.current.end),
    previous: formatPeriodRangeLabel(pc.previous.start, pc.previous.end),
  };
}

export function addDaysYmd(ymd: string, delta: number): string {
  const d = parseISODateLocal(ymd);
  if (!d) return ymd;
  d.setDate(d.getDate() + delta);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function eachDayInRange(start: string, end: string): string[] {
  if (!start || !end || end < start) return [];
  const out: string[] = [];
  let cur = start;
  let guard = 0;
  while (cur <= end && guard < 4000) {
    out.push(cur);
    if (cur === end) break;
    cur = addDaysYmd(cur, 1);
    guard += 1;
  }
  return out;
}

export function dayInRange(day: string, start: string, end: string): boolean {
  return day >= start && day <= end;
}

/** Whole-day offset from start → day (inclusive), e.g. same start gives 0. */
export function daysBetweenYmd(start: string, day: string): number {
  const a = parseISODateLocal(start);
  const b = parseISODateLocal(day);
  if (!a || !b) return 0;
  const ms = b.getTime() - a.getTime();
  return Math.max(0, Math.round(ms / 86_400_000));
}
