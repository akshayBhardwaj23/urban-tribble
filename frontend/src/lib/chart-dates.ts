/** Parse YYYY-MM-DD as local calendar date (avoids UTC / timezone day shifts). */
export function parseISODateLocal(ymd: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(ymd).trim());
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]) - 1;
  const d = Number(m[3]);
  const dt = new Date(y, mo, d);
  if (dt.getFullYear() !== y || dt.getMonth() !== mo || dt.getDate() !== d) {
    return null;
  }
  return dt;
}

/** Axis labels: show month + day; add year when not the current calendar year. */
export function formatChartAxisDate(value: unknown): string {
  const s = String(value ?? "");
  const d = parseISODateLocal(s);
  if (!d) {
    return s.length > 14 ? `${s.slice(0, 14)}…` : s;
  }
  const y = d.getFullYear();
  const nowY = new Date().getFullYear();
  const opts: Intl.DateTimeFormatOptions = {
    month: "short",
    day: "numeric",
  };
  if (y !== nowY) opts.year = "2-digit";
  return d.toLocaleDateString("en-US", opts);
}

/** Tooltip / title line — slightly fuller than axis ticks. */
export function formatChartTooltipDate(value: unknown): string {
  const s = String(value ?? "");
  const d = parseISODateLocal(s);
  if (!d) {
    try {
      const t = new Date(s);
      if (Number.isFinite(t.getTime())) {
        return t.toLocaleDateString("en-US", {
          weekday: "short",
          month: "short",
          day: "numeric",
          year: "numeric",
        });
      }
    } catch {
      /* ignore */
    }
    return s;
  }
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}
