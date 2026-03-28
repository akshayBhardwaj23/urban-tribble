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
  /** Short title for dialogs, e.g. "AI analysis scope" */
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
    "Dashboard date filters apply to charts on the Business Health tab—they do not re-slice the aggregate summary sent to this AI pass unless the product explicitly says so."
  );

  const sheetName =
    /\.xlsx?$/i.test(input.datasetName) || /\.xls$/i.test(input.datasetName)
      ? "First worksheet (default import)"
      : undefined;

  return {
    scopeTitle: "AI analysis scope",
    scopeSubtitle: "Single source — full-dataset aggregates",
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
    dateRangeLabel: "Full history in cleaned file (aggregate summary)",
    rowBasisLabel:
      input.rowCount != null
        ? `${input.rowCount.toLocaleString()} rows after cleaning`
        : "Row count from latest ingest",
    modelLabel: "Model + structured JSON (see backend config)",
    methodNote:
      "The model receives column metadata and statistical summaries (data_summary) derived from the cleaned dataset, not raw row-level dumps.",
    caveats,
    assumptions: [
      "Insights infer commercial meaning from detected column roles (date, revenue-like, category, numeric)—mislabeled columns can skew conclusions.",
      "Unless an insight cites a specific comparison, treat numbers as descriptive aggregates, not audited financials.",
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
    "Chart series and KPI tiles come from the dashboard endpoint for this source—they can differ from the static aggregate blob used for AI analysis."
  );

  const sheetName =
    /\.xlsx?$/i.test(input.datasetName) || /\.xls$/i.test(input.datasetName)
      ? "First worksheet (default import)"
      : undefined;

  return {
    scopeTitle: "Charts & KPI scope",
    scopeSubtitle: "Business Health tab — filtered view when a period is selected",
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
    modelLabel: "Server-side aggregates + chart specs",
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
    "Workspace analysis merges summaries from each listed source; cross-file joins are not automatic unless dimensions align.",
  ];
  return {
    scopeTitle: "Workspace AI analysis scope",
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
    dateRangeLabel: "Per-file full history in merged summary payload",
    rowBasisLabel: `${input.totalRows.toLocaleString()} rows combined (ingest counts)`,
    modelLabel: "Model + structured JSON (workspace overview)",
    methodNote:
      "Each file’s schema slices and summaries are concatenated for the model; verify column names across files before acting on cross-source claims.",
    caveats,
    assumptions: [
      "Column-level detail lives on each dataset’s Schema tab—this workspace pass only sees merged metadata summaries.",
      "File order and naming may influence which source the model emphasizes—check evidence lines on each insight.",
      "No double-entry accounting validation is performed.",
    ],
  };
}

export function mergeInsightTrace(
  parent: AnalysisTraceContext | null | undefined,
  slice: InsightTraceSlice | null | undefined
): AnalysisTraceContext | null {
  if (!parent && !slice) return null;
  const base: AnalysisTraceContext = parent ?? {
    scopeTitle: "Insight provenance",
    sourceFiles: [],
    columnsInScope: [],
    methodNote: "Insight-level trace supplied by the model or UI fallback.",
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
