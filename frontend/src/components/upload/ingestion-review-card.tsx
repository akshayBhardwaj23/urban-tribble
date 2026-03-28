"use client";

import { useCallback, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  CLASSIFICATION_OPTIONS,
  type DatasetClassificationId,
  type IngestionProfile,
  interpretationReadiness,
  READINESS_LABELS,
  dimensionSummary,
} from "@/lib/ingestion";
import { api } from "@/lib/api";
import { CheckCircle2, CircleAlert, CircleHelp } from "lucide-react";

interface IngestionReviewCardProps {
  datasetId: string;
  filename: string;
  rowCount: number;
  columnCount: number;
  allColumns: string[];
  ingestion: IngestionProfile;
  onConfirmed: (datasetId: string) => void;
  className?: string;
}

function readinessBadgeVariant(
  r: ReturnType<typeof interpretationReadiness>
): "default" | "secondary" | "destructive" | "outline" {
  if (r === "missing_field") return "destructive";
  if (r === "needs_review") return "outline";
  return "secondary";
}

export function IngestionReviewCard({
  datasetId,
  filename,
  rowCount,
  columnCount,
  allColumns,
  ingestion,
  onConfirmed,
  className,
}: IngestionReviewCardProps) {
  const h = ingestion.column_highlights;
  const initialDate = h.date_columns[0] ?? "";
  const initialAmount = h.revenue_columns[0] ?? h.numeric_columns[0] ?? "";
  const initialSegments = useMemo(
    () => [...(h.category_columns ?? [])].slice(0, 5),
    [h.category_columns]
  );

  const [classification, setClassification] = useState<DatasetClassificationId>(
    ingestion.classification.id as DatasetClassificationId
  );
  const [dateColumn, setDateColumn] = useState(initialDate);
  const [amountColumn, setAmountColumn] = useState(initialAmount);
  const [segmentColumns, setSegmentColumns] = useState<string[]>(initialSegments);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);

  const readiness = interpretationReadiness(ingestion);

  const amountChoices = useMemo(() => {
    const preferred = new Set([...h.revenue_columns, ...h.numeric_columns]);
    const rest = allColumns.filter((c) => !preferred.has(c));
    return [...[...preferred].sort(), ...rest.sort()];
  }, [allColumns, h.revenue_columns, h.numeric_columns]);

  const dateChoices = useMemo(() => {
    const preferred = new Set(h.date_columns);
    const rest = allColumns.filter((c) => !preferred.has(c));
    return [...[...preferred].sort(), ...rest.sort()];
  }, [allColumns, h.date_columns]);

  const segmentChoices = useMemo(
    () => allColumns.filter((c) => c !== dateColumn && c !== amountColumn),
    [allColumns, dateColumn, amountColumn]
  );

  const toggleSegment = useCallback((col: string) => {
    setSegmentColumns((prev) => {
      if (prev.includes(col)) return prev.filter((x) => x !== col);
      if (prev.length >= 4) return prev;
      return [...prev, col];
    });
  }, []);

  const handleConfirm = useCallback(async () => {
    setError(null);
    setSaving(true);
    try {
      await api.patchDataset(datasetId, {
        business_classification: classification,
        primary_date_column: dateColumn || null,
        primary_amount_column: amountColumn || null,
        segment_columns: segmentColumns,
      });
      setConfirmed(true);
      onConfirmed(datasetId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save");
    } finally {
      setSaving(false);
    }
  }, [
    datasetId,
    classification,
    dateColumn,
    amountColumn,
    segmentColumns,
    onConfirmed,
  ]);

  const selectClass =
    "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background " +
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 " +
    "disabled:cursor-not-allowed disabled:opacity-50";

  return (
    <div
      className={cn(
        "rounded-xl border bg-card p-5 shadow-sm space-y-5",
        confirmed && "border-emerald-200/80 dark:border-emerald-900/40",
        className
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <p className="text-sm font-semibold tracking-tight truncate" title={filename}>
            {filename}
          </p>
          <p className="text-xs text-muted-foreground">
            {rowCount.toLocaleString()} rows · {columnCount} columns
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          {confirmed ? (
            <Badge className="gap-1 font-normal bg-emerald-600 hover:bg-emerald-600">
              <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />
              Confirmed
            </Badge>
          ) : (
            <>
              <Badge variant={readinessBadgeVariant(readiness)} className="font-normal">
                {readiness === "missing_field" && (
                  <CircleAlert className="h-3.5 w-3.5 mr-1" aria-hidden />
                )}
                {readiness === "needs_review" && (
                  <CircleHelp className="h-3.5 w-3.5 mr-1" aria-hidden />
                )}
                {READINESS_LABELS[readiness]}
              </Badge>
              <Badge variant="outline" className="font-normal text-muted-foreground">
                {ingestion.classification.label}
              </Badge>
            </>
          )}
        </div>
      </div>

      <p className="text-sm text-muted-foreground leading-relaxed">
        Here is how we read your file for trends and KPIs. Adjust anything that looks off, then
        confirm so analysis matches how you think about this data.
      </p>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-foreground" htmlFor={`dc-${datasetId}`}>
            Dataset type
          </label>
          <select
            id={`dc-${datasetId}`}
            className={selectClass}
            value={classification}
            disabled={saving || confirmed}
            onChange={(e) =>
              setClassification(e.target.value as DatasetClassificationId)
            }
          >
            {CLASSIFICATION_OPTIONS.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
          <p className="text-[11px] text-muted-foreground">
            Shapes summaries and language (sales, spend, campaigns, etc.).
          </p>
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-foreground" htmlFor={`dt-${datasetId}`}>
            Timeline column
          </label>
          <select
            id={`dt-${datasetId}`}
            className={selectClass}
            value={dateColumn}
            disabled={saving || confirmed}
            onChange={(e) => setDateColumn(e.target.value)}
          >
            <option value="">Not set — optional for some views</option>
            {dateChoices.map((c) => (
              <option key={c} value={c}>
                {c.replace(/_/g, " ")}
              </option>
            ))}
          </select>
          <p className="text-[11px] text-muted-foreground">
            Used for trends over time. Pick the column that is really your calendar or period.
          </p>
        </div>

        <div className="space-y-1.5 sm:col-span-2">
          <label className="text-xs font-medium text-foreground" htmlFor={`amt-${datasetId}`}>
            Primary amount column
          </label>
          <select
            id={`amt-${datasetId}`}
            className={selectClass}
            value={amountColumn}
            disabled={saving || confirmed}
            onChange={(e) => setAmountColumn(e.target.value)}
          >
            <option value="">Not set</option>
            {amountChoices.map((c) => (
              <option key={c} value={c}>
                {c.replace(/_/g, " ")}
              </option>
            ))}
          </select>
          <p className="text-[11px] text-muted-foreground">
            Revenue, cost, quantity, or another number you want rolled up into KPIs and charts.
          </p>
        </div>
      </div>

      <div className="space-y-2">
        <p className="text-xs font-medium text-foreground">Breakdowns</p>
        <p className="text-[11px] text-muted-foreground">
          Region, product, customer, campaign — choose fields we should treat as segments.
        </p>
        <div className="flex flex-wrap gap-2">
          {segmentChoices.length === 0 ? (
            <p className="text-xs text-muted-foreground italic">
              Other columns will show here once timeline and amount use different fields.
            </p>
          ) : (
            segmentChoices.map((col) => {
              const on = segmentColumns.includes(col);
              return (
                <button
                  key={col}
                  type="button"
                  disabled={saving || confirmed}
                  onClick={() => toggleSegment(col)}
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                    on
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border bg-muted/40 text-muted-foreground hover:bg-muted"
                  )}
                >
                  {col.replace(/_/g, " ")}
                </button>
              );
            })
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          Selected: {dimensionSummary(segmentColumns)}
        </p>
      </div>

      {ingestion.interpretations.length > 0 && (
        <div className="rounded-lg bg-muted/40 px-3 py-2.5 space-y-1">
          <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">
            Our read
          </p>
          <ul className="text-sm text-foreground/90 space-y-1 list-disc list-inside">
            {ingestion.interpretations.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        </div>
      )}

      {ingestion.flags.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground">Notes</p>
          <ul className="space-y-2">
            {ingestion.flags.map((f) => (
              <li
                key={f.code}
                className={cn(
                  "text-sm rounded-lg px-3 py-2 border",
                  f.kind === "warning"
                    ? "border-amber-200/80 bg-amber-50/80 text-amber-950 dark:border-amber-900/50 dark:bg-amber-950/25 dark:text-amber-100"
                    : "border-border bg-muted/30"
                )}
              >
                {f.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {error && <p className="text-sm text-destructive">{error}</p>}

      {!confirmed && (
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pt-1 border-t border-border/60">
          <p className="text-xs text-muted-foreground max-w-md">
            When this looks right, confirm — we will save your choices and use them for dashboards
            and analysis.
          </p>
          <Button type="button" onClick={() => void handleConfirm()} disabled={saving}>
            {saving ? "Saving…" : "Confirm this file"}
          </Button>
        </div>
      )}
    </div>
  );
}
