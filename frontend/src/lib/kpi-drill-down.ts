/** KPI drill-down payload (mirrors backend `details` on dashboard KPIs). */

export interface KpiDrillDownDetails {
  metric_title?: string;
  definition: string;
  formula_summary?: string;
  source_file: string;
  columns_used: string[];
  aggregation?: string | null;
  source_column?: string | null;
  date_column?: string | null;
  date_range_label: string;
  row_count: number;
}

function str(v: unknown): string {
  return typeof v === "string" ? v.trim() : "";
}

function num(v: unknown): number {
  return typeof v === "number" && Number.isFinite(v) ? v : 0;
}

export function parseKpiDrillDown(raw: unknown): KpiDrillDownDetails | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const definition = str(o.definition);
  const source_file = str(o.source_file);
  if (!definition || !source_file) return null;
  const cols = o.columns_used;
  const columns_used = Array.isArray(cols)
    ? cols.filter((x): x is string => typeof x === "string" && x.trim().length > 0)
    : [];
  return {
    metric_title: str(o.metric_title) || undefined,
    definition,
    formula_summary: str(o.formula_summary) || undefined,
    source_file,
    columns_used,
    aggregation: str(o.aggregation) || null,
    source_column: str(o.source_column) || null,
    date_column: str(o.date_column) || null,
    date_range_label: str(o.date_range_label) || "—",
    row_count: num(o.row_count),
  };
}

/** When KPIs are rendered from static `data_summary` (no live dashboard KPI row yet). */
export function buildStaticSummaryKpiDetails(input: {
  title: string;
  datasetName: string;
  column?: string;
  aggregationLabel: string;
  formula_summary: string;
  /** Shown under row count — clarify full-file vs filtered */
  scopeNote: string;
}): KpiDrillDownDetails {
  const col = input.column;
  return {
    metric_title: input.title,
    definition: `${input.title}: ${input.scopeNote}`,
    formula_summary: input.formula_summary,
    source_file: input.datasetName,
    columns_used: col ? [col] : [],
    aggregation: input.aggregationLabel,
    source_column: col ?? null,
    date_column: null,
    date_range_label: "Full cleaned file (summary stats—not the live filtered frame)",
    row_count: 0,
  };
}

/** Client-side parity when API returns KPIs without `details` (older responses). */
/** Workspace Business Health tiles (overview KPI slots). */
export function buildWorkspaceMetricSlotDetails(input: {
  label: string;
  sourceName: string | null;
  note: string | null;
  totalRowsWorkspace: number;
  totalDatasets: number;
}): KpiDrillDownDetails {
  const src =
    input.sourceName ??
    (input.totalDatasets > 0
      ? `${input.totalDatasets} workspace source${input.totalDatasets === 1 ? "" : "s"}`
      : "Workspace");
  return {
    metric_title: input.label,
    definition: `This tile is filled by matching your workspace overview KPI list to “${input.label}” using label heuristics (and AI key-metric text when present). It is not a custom SQL query per session.${
      input.note ? ` ${input.note}` : ""
    }`,
    formula_summary:
      "Backend: aggregated metrics from each ingested dataset, then best match by keyword patterns for this slot.",
    source_file: src,
    columns_used: [],
    aggregation: "server-defined",
    source_column: null,
    date_column: null,
    date_range_label:
      "Each source uses its own ingested range; workspace view does not apply a single date filter here.",
    row_count: input.totalRowsWorkspace,
  };
}

export function buildHeuristicKpiDetails(input: {
  title: string;
  datasetName: string;
  column?: string | null;
  aggregation?: string | null;
  filteredRowCount: number;
  dateRangeLabel: string;
  dateColumn: string | null;
}): KpiDrillDownDetails {
  const col = input.column ?? undefined;
  const agg = (input.aggregation || "sum").toLowerCase();
  if (!col || col === "__row_count__") {
    return {
      metric_title: input.title,
      definition: `"${input.title}" reflects a row count on the filtered dataframe (${input.filteredRowCount.toLocaleString()} rows).`,
      formula_summary: "pandas: len(df) after any date filter.",
      source_file: input.datasetName,
      columns_used: [],
      aggregation: "count",
      source_column: null,
      date_column: input.dateColumn,
      date_range_label: input.dateRangeLabel,
      row_count: input.filteredRowCount,
    };
  }
  if (col === "__column_count__") {
    return {
      metric_title: input.title,
      definition: `"${input.title}" is the column count on the filtered dataframe.`,
      formula_summary: "pandas: len(df.columns)",
      source_file: input.datasetName,
      columns_used: [],
      aggregation: "count",
      source_column: null,
      date_column: input.dateColumn,
      date_range_label: input.dateRangeLabel,
      row_count: input.filteredRowCount,
    };
  }
  return {
    metric_title: input.title,
    definition: `"${input.title}" is the ${agg} of \`${col}\` over ${input.filteredRowCount.toLocaleString()} filtered rows.`,
    formula_summary: `pandas: df['${col}'].${agg}()`,
    source_file: input.datasetName,
    columns_used: [col],
    aggregation: agg,
    source_column: col,
    date_column: input.dateColumn,
    date_range_label: input.dateRangeLabel,
    row_count: input.filteredRowCount,
  };
}
