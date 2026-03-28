export type DatasetClassificationId =
  | "sales_data"
  | "expenses"
  | "marketing_campaigns"
  | "customer_data"
  | "inventory"
  | "tax_accounting"
  | "unknown_dataset";

export const CLASSIFICATION_OPTIONS: { id: DatasetClassificationId; label: string }[] = [
  { id: "sales_data", label: "Sales data" },
  { id: "expenses", label: "Expenses" },
  { id: "marketing_campaigns", label: "Marketing campaigns" },
  { id: "customer_data", label: "Customer data" },
  { id: "inventory", label: "Inventory" },
  { id: "tax_accounting", label: "Tax / accounting" },
  { id: "unknown_dataset", label: "General / other" },
];

export interface IngestionClassification {
  id: DatasetClassificationId;
  label: string;
  confidence: string;
}

export interface IngestionFlag {
  kind: string;
  code: string;
  message: string;
}

export interface IngestionColumnHighlights {
  date_columns: string[];
  revenue_columns: string[];
  category_columns: string[];
  numeric_columns: string[];
  text_columns: string[];
}

export interface IngestionProfile {
  classification: IngestionClassification;
  column_highlights: IngestionColumnHighlights;
  interpretations: string[];
  flags: IngestionFlag[];
}

/** How solid the automatic read looks before the user confirms. */
export type InterpretationReadiness = "ready" | "needs_review" | "missing_field";

export function interpretationReadiness(ingestion: IngestionProfile): InterpretationReadiness {
  const codes = new Set(ingestion.flags.map((f) => f.code));
  if (codes.has("no_date_column") || codes.has("no_amount_column")) {
    return "missing_field";
  }
  if (
    ingestion.flags.some((f) => f.kind === "warning") ||
    ingestion.classification.confidence === "low"
  ) {
    return "needs_review";
  }
  return "ready";
}

export const READINESS_LABELS: Record<InterpretationReadiness, string> = {
  ready: "Ready",
  needs_review: "Needs review",
  missing_field: "Missing a key field",
};

export function fileTypeLabel(ext: string): string {
  const e = ext.toLowerCase().replace(/^\./, "");
  switch (e) {
    case "csv":
      return "Comma-separated (CSV)";
    case "tsv":
      return "Tab-separated (TSV)";
    case "xlsx":
      return "Excel workbook (.xlsx)";
    case "xls":
      return "Excel spreadsheet (.xls)";
    default:
      return e ? e.toUpperCase() : "Spreadsheet";
  }
}

export function classificationLabelForId(id: string): string {
  return CLASSIFICATION_OPTIONS.find((o) => o.id === id)?.label ?? "General dataset";
}

/** Friendly labels for dimension-style columns in copy. */
export function dimensionSummary(columns: string[]): string {
  if (columns.length === 0) return "None picked yet";
  return columns
    .map((c) => c.replace(/_/g, " "))
    .join(" · ");
}
