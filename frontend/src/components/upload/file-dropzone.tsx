"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDropzone } from "react-dropzone";
import { ArrowRight, FileSpreadsheet, Sparkles, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { IngestionPipeline } from "@/components/upload/ingestion-pipeline";
import { IngestionReviewCard } from "@/components/upload/ingestion-review-card";
import type { IngestionProfile } from "@/lib/ingestion";
import {
  CUSTOM_ANALYSIS_TEMPLATE,
  type AnalysisTemplate,
  isGuidedTemplate,
} from "@/lib/analysis-templates";
import { ExpectedInputsList } from "@/components/upload/expected-inputs-list";

const ACCEPTED_TYPES = {
  "text/csv": [".csv"],
  "text/tab-separated-values": [".tsv"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [
    ".xlsx",
  ],
  "application/vnd.ms-excel": [".xls"],
};

export interface UploadFileResult {
  dataset_id: string;
  ingestion: IngestionProfile;
  filename: string;
  file_type: string;
  row_count: number;
  column_count: number;
  all_columns: string[];
}

interface FileEntry {
  file: File;
  description: string;
  status: "pending" | "uploading" | "done" | "error";
  error?: string;
  result?: UploadFileResult;
}

interface FileDropzoneProps {
  onUpload: (file: File, description: string) => Promise<UploadFileResult>;
  onContinue: (datasetIds: string[]) => void;
  /** Selected outcome on the upload page; shapes hints and optional context placeholders. */
  analysisTemplate?: AnalysisTemplate;
}

function OutcomeRibbon({ template }: { template: AnalysisTemplate }) {
  if (!isGuidedTemplate(template)) return null;
  return (
    <div
      className={cn(
        "rounded-xl border border-primary/25 bg-primary/7 px-4 py-3.5 space-y-2",
        "shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]"
      )}
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-primary">
        Your outcome
      </p>
      <p className="text-sm font-semibold text-foreground leading-snug">{template.title}</p>
      <p className="text-sm text-muted-foreground leading-relaxed">
        {template.analysisDelivered}
      </p>
      <div className="pt-3 border-t border-primary/15 mt-3 space-y-2">
        <ExpectedInputsList items={template.recommendedInputs} label="Recommended files" />
        {template.bestFor ? (
          <p className="text-[11px] text-muted-foreground leading-relaxed pt-0.5">
            <span className="font-medium text-foreground/80">Typical users:</span>{" "}
            {template.bestFor}
          </p>
        ) : null}
      </div>
    </div>
  );
}

function extensionFromFilename(name: string): string {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i) : "";
}

export function FileDropzone({
  onUpload,
  onContinue,
  analysisTemplate = CUSTOM_ANALYSIS_TEMPLATE,
}: FileDropzoneProps) {
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [phase, setPhase] = useState<"configure" | "processing" | "review">(
    "configure"
  );
  const [processingIndex, setProcessingIndex] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmedIds, setConfirmedIds] = useState<Set<string>>(() => new Set());
  const prevPhaseRef = useRef(phase);
  const entriesRef = useRef(entries);
  useEffect(() => {
    entriesRef.current = entries;
  }, [entries]);

  useEffect(() => {
    if (phase === "review" && prevPhaseRef.current !== "review") {
      setConfirmedIds(new Set());
    }
    prevPhaseRef.current = phase;
  }, [phase]);

  const markFileConfirmed = useCallback((datasetId: string) => {
    setConfirmedIds((prev) => new Set(prev).add(datasetId));
  }, []);

  const onDrop = useCallback((accepted: File[]) => {
    const newEntries: FileEntry[] = accepted.map((file) => ({
      file,
      description: "",
      status: "pending" as const,
    }));
    setEntries((prev) => [...prev, ...newEntries]);
    setPhase("configure");
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_TYPES,
    maxSize: 50 * 1024 * 1024,
    disabled: busy || phase === "processing",
  });

  const updateEntry = (index: number, updates: Partial<FileEntry>) => {
    setEntries((prev) =>
      prev.map((e, i) => (i === index ? { ...e, ...updates } : e))
    );
  };

  const removeEntry = (index: number) => {
    setEntries((prev) => prev.filter((_, i) => i !== index));
  };

  const pendingCount = useMemo(
    () => entries.filter((e) => e.status === "pending" || e.status === "error").length,
    [entries]
  );

  const completedResults = useMemo(
    () =>
      entries.filter((e): e is FileEntry & { result: UploadFileResult } =>
        Boolean(e.status === "done" && e.result)
      ),
    [entries]
  );

  const runPrepare = async () => {
    const list = entriesRef.current;
    const toRun = list
      .map((e, i) => (e.status === "pending" || e.status === "error" ? i : -1))
      .filter((i): i is number => i >= 0);
    if (toRun.length === 0) return;

    setBusy(true);
    setPhase("processing");
    let anySuccess = false;

    for (const i of toRun) {
      const entry = entriesRef.current[i];
      if (!entry || (entry.status !== "pending" && entry.status !== "error")) {
        continue;
      }

      setProcessingIndex(i);
      updateEntry(i, { status: "uploading", error: undefined });

      try {
        const raw = await onUpload(entry.file, entry.description);
        const result: UploadFileResult = {
          dataset_id: raw.dataset_id,
          ingestion: raw.ingestion,
          filename: raw.filename,
          file_type: raw.file_type,
          row_count: raw.row_count,
          column_count: raw.column_count,
          all_columns: raw.all_columns,
        };
        updateEntry(i, { status: "done", result });
        anySuccess = true;
      } catch (err) {
        updateEntry(i, {
          status: "error",
          error: err instanceof Error ? err.message : "Import failed",
        });
      }
    }

    setProcessingIndex(null);
    setBusy(false);
    setPhase(anySuccess ? "review" : "configure");
  };

  const currentProcessingEntry =
    processingIndex !== null ? entries[processingIndex] : null;

  const successIds = completedResults.map((e) => e.result!.dataset_id);
  const allFilesConfirmed =
    completedResults.length > 0 &&
    completedResults.every((e) => confirmedIds.has(e.result!.dataset_id));

  const handleContinue = () => {
    if (successIds.length === 0 || !allFilesConfirmed) return;
    onContinue(successIds);
  };

  const resetReviewAddMore = () => {
    setPhase("configure");
    setEntries((prev) => prev.filter((e) => e.status !== "done"));
  };

  if (phase === "processing" && currentProcessingEntry) {
    const ext =
      currentProcessingEntry.result?.file_type ??
      extensionFromFilename(currentProcessingEntry.file.name);
    return (
      <div className="space-y-6">
        <OutcomeRibbon template={analysisTemplate} />
        <div className="flex items-start gap-3 rounded-lg border border-primary/15 bg-primary/5 px-4 py-3">
          <Sparkles className="h-5 w-5 shrink-0 text-primary mt-0.5" aria-hidden />
          <div>
            <p className="text-sm font-medium">Understanding your file</p>
            <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
              We read the structure, classify the dataset, and get it ready for metrics—not
              just store the upload.
            </p>
          </div>
        </div>
        <IngestionPipeline
          isLoading={currentProcessingEntry.status === "uploading"}
          filename={currentProcessingEntry.file.name}
          fileType={ext}
          ingestion={
            currentProcessingEntry.status === "done" && currentProcessingEntry.result
              ? currentProcessingEntry.result.ingestion
              : null
          }
        />
      </div>
    );
  }

  if (phase === "review" && completedResults.length > 0) {
    return (
      <div className="space-y-6">
        <OutcomeRibbon template={analysisTemplate} />
        <div className="rounded-xl border bg-muted/30 px-4 py-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="flex items-start gap-2">
            <Sparkles className="h-5 w-5 text-primary shrink-0 mt-0.5" aria-hidden />
            <div>
              <p className="text-sm font-medium">Ingestion complete</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {completedResults.length} source
                {completedResults.length !== 1 ? "s" : ""} prepared. Check each card, fix anything
                we misread, then confirm every file before continuing.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 shrink-0">
            <Button type="button" variant="outline" size="sm" onClick={resetReviewAddMore}>
              Add more files
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={handleContinue}
              disabled={!allFilesConfirmed}
              title={
                allFilesConfirmed
                  ? undefined
                  : "Confirm each file below before continuing"
              }
            >
              Continue to workspace
              <ArrowRight className="h-4 w-4 ml-1.5" aria-hidden />
            </Button>
          </div>
        </div>

        {!allFilesConfirmed && (
          <p className="text-xs text-muted-foreground text-center sm:text-left">
            Confirm each file with the button on its card so we know the interpretation is right
            before analysis runs.
          </p>
        )}

        <div className="space-y-4">
          {entries
            .filter((e) => e.status === "error")
            .map((e, idx) => (
              <div
                key={`err-${e.file.name}-${idx}`}
                className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm"
              >
                <span className="font-medium">{e.file.name}</span>
                <span className="text-muted-foreground"> — {e.error}</span>
              </div>
            ))}

          {completedResults.map((entry) => (
            <IngestionReviewCard
              key={entry.result!.dataset_id}
              datasetId={entry.result!.dataset_id}
              filename={entry.result!.filename}
              rowCount={entry.result!.row_count}
              columnCount={entry.result!.column_count}
              allColumns={entry.result!.all_columns}
              ingestion={entry.result!.ingestion}
              onConfirmed={markFileConfirmed}
            />
          ))}
        </div>
      </div>
    );
  }

  if (entries.length > 0) {
    return (
      <div className="space-y-4">
        <OutcomeRibbon template={analysisTemplate} />
        {entries.map((entry, index) => (
          <div
            key={`${entry.file.name}-${index}`}
            className={cn(
              "rounded-xl border p-4 space-y-3 transition-colors",
              entry.status === "done"
                ? "bg-muted/20 border-border"
                : entry.status === "error"
                  ? "bg-destructive/5 border-destructive/25"
                  : "bg-card"
            )}
          >
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3 min-w-0">
                <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-primary/10 text-primary shrink-0">
                  <FileSpreadsheet className="h-5 w-5" aria-hidden />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">{entry.file.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {(entry.file.size / 1024).toFixed(1)} KB
                    {entry.status === "done" && " · Prepared"}
                    {entry.status === "error" && ` · ${entry.error}`}
                  </p>
                </div>
              </div>
              {entry.status === "pending" && (
                <Button
                  variant="ghost"
                  size="sm"
                  type="button"
                  onClick={() => removeEntry(index)}
                >
                  Remove
                </Button>
              )}
            </div>

            {entry.status !== "done" && (
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">
                  What should we know? <span className="font-normal">(optional)</span>
                </label>
                <Textarea
                  placeholder={analysisTemplate.contextPlaceholder}
                  value={entry.description}
                  onChange={(e) =>
                    updateEntry(index, { description: e.target.value })
                  }
                  rows={2}
                  className="text-sm resize-none"
                />
              </div>
            )}
          </div>
        ))}

        <div
          {...getRootProps()}
          className={cn(
            "cursor-pointer rounded-xl border border-dashed p-4 text-center transition-colors",
            "border-muted-foreground/20 hover:border-primary/40 hover:bg-muted/20",
            (busy || phase === "processing") && "pointer-events-none opacity-50"
          )}
        >
          <input {...getInputProps()} />
          <p className="text-xs text-muted-foreground">
            Drop or click to add another file
          </p>
        </div>

        <div className="flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-3 pt-2">
          <p className="text-sm text-muted-foreground">
            {entries.length} file{entries.length !== 1 ? "s" : ""} queued
          </p>
          <div className="flex flex-wrap gap-2 justify-end">
            {pendingCount > 0 && (
              <Button
                variant="outline"
                size="sm"
                type="button"
                onClick={() =>
                  setEntries((prev) => prev.filter((e) => e.status !== "pending"))
                }
              >
                Clear pending
              </Button>
            )}
            <Button
              type="button"
              onClick={() => {
                void runPrepare();
              }}
              disabled={pendingCount === 0 || busy}
            >
              <Sparkles className="h-4 w-4 mr-2" aria-hidden />
              Prepare for analysis
              {pendingCount > 0 ? ` (${pendingCount})` : ""}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <OutcomeRibbon template={analysisTemplate} />
      <div
        {...getRootProps()}
        className={cn(
          "group relative cursor-pointer rounded-2xl border-2 border-dashed p-10 sm:p-14 text-center transition-all duration-300",
          isDragActive
            ? "border-primary bg-primary/5 shadow-[0_0_0_1px_hsl(var(--primary)/0.2)]"
            : "border-muted-foreground/20 bg-linear-to-b from-muted/40 via-background to-background hover:border-primary/35 hover:shadow-md"
        )}
      >
      <input {...getInputProps()} />
      <div className="pointer-events-none absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity bg-[radial-gradient(600px_circle_at_50%_-20%,hsl(var(--primary)/0.08),transparent)]" />
      <div className="relative flex flex-col items-center gap-4 max-w-md mx-auto">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 text-primary ring-1 ring-primary/15">
          <Upload className="h-7 w-7" aria-hidden />
        </div>
        <div>
          <p className="text-base font-semibold tracking-tight">
            {isDragActive ? "Release to add files" : "Drop files here or click to browse"}
          </p>
          <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
            Excel or CSV exports from your systems work well. You can queue several files—each
            will be prepared and reviewed before analysis runs.
          </p>
        </div>
        <p className="text-xs text-muted-foreground">
          .xlsx, .xls, .csv, .tsv · up to 50MB per file
        </p>
      </div>
      </div>
    </div>
  );
}
