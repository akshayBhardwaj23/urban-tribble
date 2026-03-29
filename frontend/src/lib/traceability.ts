import { TRACE_SCOPE_FALLBACK_NOTE } from "@/lib/analysis-fallback-copy";

/** Provenance for AI analysis and metrics—used for trust / verification UX. */

export interface TraceSourceFile {
  name: string;
  /** e.g. first sheet for Excel; omit for CSV */
  sheetName?: string;
  rowCount?: number | null;
  columnCount?: number | null;
  datasetId?: string;
}

export interface AnalysisTraceContext {
  /** Short title for dialogs, e.g. "Analysis scope" */
  scopeTitle: string;
  /** One line, e.g. workspace vs single file */
  scopeSubtitle?: string;
  sourceFiles: TraceSourceFile[];
  /** Flat list of column names the pipeline exposed to the model */
  columnsInScope: string[];
  /** Human-readable date window if applicable */
  dateRangeLabel?: string | null;
  /** How many rows the aggregates reflect */
  rowBasisLabel?: string | null;
  /** e.g. GPT-4o + structured JSON */
  modelLabel?: string;
  /** Pipeline / aggregation explanation */
  methodNote: string;
  caveats: string[];
  assumptions: string[];
}

export interface InsightTraceSlice {
  fileName?: string;
  sheetName?: string;
  columnsUsed?: string[];
  dateRange?: string;
  rowCount?: number;
  caveats?: string[];
}

function uniqueStrings(xs: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const x of xs) {
    const t = x.trim();
    if (!t || seen.has(t)) continue;
    seen.add(t);
    out.push(t);
  }
  return out;
}

/** Flatten schema_json column lists for display. */
export function columnsFromSchema(schema: {
  date_columns?: string[];
  revenue_columns?: string[];
  category_columns?: string[];
  numeric_columns?: string[];
  text_columns?: string[];
} | null): string[] {
  if (!schema) return [];
  return uniqueStrings([
    ...(schema.date_columns ?? []),
    ...(schema.revenue_columns ?? []),
    ...(schema.category_columns ?? []),
    ...(schema.numeric_columns ?? []),
    ...(schema.text_columns ?? []),
  ]);
}

export function buildDatasetAiTraceContext(input: {
  datasetName: string;
  datasetId?: string;
  rowCount?: number | null;
  columnCount?: number | null;
  schema: Parameters<typeof columnsFromSchema>[0];
  cleaningStepSummaries?: string[];
}): AnalysisTraceContext {
  const cols = columnsFromSchema(input.schema);
  const caveats: string[] = [];
  if (input.cleaningStepSummaries?.length) {
    caveats.push(
      `Cleaning applied: ${input.cleaningStepSummaries.slice(0, 3).join(" · ")}`
    );
  }
  caveats.push(
    "Date filters on the Overview tab affect charts and live KPIs—they do not automatically re-slice the saved aggregate used for this briefing unless stated."
  );

  const sheetName =
    /\.xlsx?$/i.test(input.datasetName) || /\.xls$/i.test(input.datasetName)
      ? "First worksheet (default import)"
      : undefined;

  return {
    scopeTitle: "Briefing scope",
    scopeSubtitle: "Single file · full-dataset aggregates",
    sourceFiles: [
      {
        name: input.datasetName,
        sheetName,
        rowCount: input.rowCount,
        columnCount: input.columnCount,
        datasetId: input.datasetId,
      },
    ],
    columnsInScope: cols,
    dateRangeLabel: "Full history in the cleaned file (aggregate summary)",
    rowBasisLabel:
      input.rowCount != null
        ? `${input.rowCount.toLocaleString()} rows after cleaning`
        : "Row count from latest ingest",
    modelLabel: "Structured model output (backend config)",
    methodNote:
      "The model sees column roles and statistical summaries from the cleaned file—not raw row exports.",
    caveats,
    assumptions: [
      "Column roles are inferred—wrong labels skew the read.",
      "Unless an insight cites a specific cut, treat figures as operational aggregates, not audited financials.",
    ],
  };
}

export function buildDatasetDashboardTraceContext(input: {
  datasetName: string;
  datasetId?: string;
  rowCount?: number | null;
  columnCount?: number | null;
  schema: Parameters<typeof columnsFromSchema>[0];
  dateRangeLabel: string | null;
  timeframeWarning?: string | null;
}): AnalysisTraceContext {
  const cols = columnsFromSchema(input.schema);
  const caveats: string[] = [];
  if (input.timeframeWarning) caveats.push(input.timeframeWarning);
  caveats.push(
    "Charts and KPI tiles use the live dashboard for this source; they can differ from the static aggregate used in the Briefing tab."
  );

  const sheetName =
    /\.xlsx?$/i.test(input.datasetName) || /\.xls$/i.test(input.datasetName)
      ? "First worksheet (default import)"
      : undefined;

  return {
    scopeTitle: "Charts and KPI scope",
    scopeSubtitle: "Overview tab · filtered when a period is selected",
    sourceFiles: [
      {
        name: input.datasetName,
        sheetName,
        rowCount: input.rowCount,
        columnCount: input.columnCount,
        datasetId: input.datasetId,
      },
    ],
    columnsInScope: cols,
    dateRangeLabel:
      input.dateRangeLabel ?? "All periods (no date filter applied)",
    rowBasisLabel:
      input.rowCount != null
        ? `${input.rowCount.toLocaleString()} rows in source (ingested)`
        : undefined,
    modelLabel: "Server aggregates and chart specs",
    methodNote:
      "Values reflect the schema detected at import and any timeframe you set above. Open Preview to spot-check underlying rows.",
    caveats,
    assumptions: [
      "Numeric and date roles are inferred—misclassified columns will skew visuals.",
    ],
  };
}

export function buildWorkspaceAiTraceContext(input: {
  datasets: { id: string; name: string; row_count?: number | null; column_count?: number | null }[];
  totalRows: number;
}): AnalysisTraceContext {
  const caveats: string[] = [
    "Workspace briefing merges summaries from each listed source; cross-file joins are not automatic unless dimensions align.",
  ];
  return {
    scopeTitle: "Workspace briefing scope",
    scopeSubtitle: `${input.datasets.length} source${input.datasets.length === 1 ? "" : "s"} · ${input.totalRows.toLocaleString()} total rows (ingested)`,
    sourceFiles: input.datasets.map((d) => ({
      name: d.name,
      rowCount: d.row_count,
      columnCount: d.column_count,
      datasetId: d.id,
      ...(/\.xlsx?$/i.test(d.name) || /\.xls$/i.test(d.name)
        ? { sheetName: "First worksheet (per file)" }
        : {}),
    })),
    columnsInScope: [],
    dateRangeLabel: "Each file’s full history in the merged summary payload",
    rowBasisLabel: `${input.totalRows.toLocaleString()} rows combined (ingest counts)`,
    modelLabel: "Structured model output (workspace)",
    methodNote:
      "Each file’s schema and summaries are stacked for one pass—align column names before you act on cross-file claims.",
    caveats,
    assumptions: [
      "Column detail lives on each file’s Schema tab—this pass only sees merged summaries.",
      "File order and naming can nudge emphasis—use each insight’s backing line before you commit.",
      "No double-entry or audit validation.",
    ],
  };
}

export function mergeInsightTrace(
  parent: AnalysisTraceContext | null | undefined,
  slice: InsightTraceSlice | null | undefined
): AnalysisTraceContext | null {
  if (!parent && !slice) return null;
  const base: AnalysisTraceContext = parent ?? {
    scopeTitle: "Finding basis",
    sourceFiles: [],
    columnsInScope: [],
    methodNote: TRACE_SCOPE_FALLBACK_NOTE,
    caveats: [],
    assumptions: [],
  };
  if (!slice) return base;
  const files = [...base.sourceFiles];
  if (slice.fileName) {
    files.unshift({
      name: slice.fileName,
      sheetName: slice.sheetName,
      rowCount: slice.rowCount,
    });
  }
  const cols = uniqueStrings([
    ...base.columnsInScope,
    ...(slice.columnsUsed ?? []),
  ]);
  const caveats = [...base.caveats, ...(slice.caveats ?? [])];
  return {
    ...base,
    sourceFiles: files.length ? files : base.sourceFiles,
    columnsInScope: cols.length ? cols : base.columnsInScope,
    dateRangeLabel: slice.dateRange ?? base.dateRangeLabel,
    caveats,
  };
}
