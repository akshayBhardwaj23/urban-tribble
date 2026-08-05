"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";
import type { IngestionProfile } from "@/lib/ingestion";
import { fileTypeLabel } from "@/lib/ingestion";

const STAGES: { key: string; title: string; subtitleLoading: string }[] = [
  { key: "uploaded", title: "File received", subtitleLoading: "Upload complete" },
  { key: "type", title: "Format identified", subtitleLoading: "Checking structure" },
  { key: "classify", title: "Type assigned", subtitleLoading: "Matching to your context" },
  { key: "columns", title: "Fields mapped", subtitleLoading: "Profiling columns" },
  { key: "issues", title: "Quick quality pass", subtitleLoading: "Scanning for gaps" },
  { key: "ready", title: "Ready for charts and briefing", subtitleLoading: "Handing off to workspace" },
];

/** Map server processing_stage values onto the UI stage index. */
const SERVER_STAGE_INDEX: Record<string, number> = {
  queued: 0,
  reading: 1,
  cleaning: 2,
  profiling: 3,
  planning: 4,
  saving: 5,
};

interface IngestionPipelineProps {
  isLoading: boolean;
  filename: string;
  fileType: string;
  ingestion: IngestionProfile | null;
  /** When present, drives progress from the worker instead of a timer. */
  processingStage?: string | null;
  className?: string;
}

export function IngestionPipeline({
  isLoading,
  filename,
  fileType,
  ingestion,
  processingStage,
  className,
}: IngestionPipelineProps) {
  const runId = `${isLoading}:${filename}:${processingStage ?? ""}`;
  const [progress, setProgress] = useState({ run: runId, value: 0 });
  const warmup = progress.run === runId ? progress.value : 0;

  useEffect(() => {
    if (!isLoading || processingStage) return;
    const a = window.setTimeout(() => setProgress({ run: runId, value: 1 }), 280);
    const b = window.setTimeout(() => setProgress({ run: runId, value: 2 }), 620);
    return () => {
      window.clearTimeout(a);
      window.clearTimeout(b);
    };
  }, [isLoading, runId, processingStage]);

  const typeDescription = fileTypeLabel(fileType);

  const issuesSubtitle = (() => {
    if (!ingestion) return STAGES[4].subtitleLoading;
    const warns = ingestion.flags.filter((f) => f.kind === "warning");
    if (warns.length === 0 && ingestion.flags.length === 0) {
      return "No structure issues at import-still run your normal read on trends and margin.";
    }
    if (warns.length === 0) {
      return `${ingestion.flags.length} note${ingestion.flags.length === 1 ? "" : "s"} for you below.`;
    }
    return `${warns.length} item${warns.length === 1 ? "" : "s"} worth a quick look.`;
  })();

  const columnSubtitle = ingestion
    ? ingestion.interpretations.slice(0, 2).join(" · ")
    : STAGES[3].subtitleLoading;

  const classifySubtitle = ingestion
    ? `${ingestion.classification.label} · ${ingestion.classification.confidence === "high" ? "Strong match" : ingestion.classification.confidence === "medium" ? "Likely match-confirm if unsure" : "Uncertain-confirm before you rely on it"}`
    : STAGES[2].subtitleLoading;

  const subtitles: string[] = [
    filename,
    typeDescription,
    classifySubtitle,
    columnSubtitle,
    issuesSubtitle,
    "Open the source for KPIs, charts, and the full briefing.",
  ];

  let activeIndex = 0;
  if (isLoading) {
    if (processingStage && processingStage in SERVER_STAGE_INDEX) {
      activeIndex = SERVER_STAGE_INDEX[processingStage];
    } else {
      activeIndex = Math.min(warmup, 2);
    }
  } else if (ingestion) {
    activeIndex = STAGES.length;
  }

  return (
    <div className={cn("rounded-xl border bg-card/80 backdrop-blur-sm p-5 shadow-sm", className)}>
      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-4">
        Preparing file
      </p>
      <ol className="space-y-0">
        {STAGES.map((stage, i) => {
          const done = activeIndex > i || (!isLoading && ingestion !== null);
          const current = isLoading && activeIndex === i;
          const pending = !done && !current;

          return (
            <li key={stage.key} className="relative flex gap-3 pb-5 last:pb-0">
              {i < STAGES.length - 1 && (
                <div
                  className={cn(
                    "absolute left-[9px] top-5 h-[calc(100%-8px)] w-px",
                    done ? "bg-primary/40" : "bg-border"
                  )}
                />
              )}
              <div
                className={cn(
                  "mt-0.5 flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full border text-[10px]",
                  done && "border-primary bg-primary text-primary-foreground",
                  current && "border-primary text-primary",
                  pending && "border-muted-foreground/30 text-muted-foreground/50"
                )}
              >
                {done ? "✓" : i + 1}
              </div>
              <div className="min-w-0 pt-0.5">
                <p
                  className={cn(
                    "text-sm font-medium leading-none",
                    pending && "text-muted-foreground/60"
                  )}
                >
                  {stage.title}
                </p>
                <p className="mt-1 text-xs text-muted-foreground leading-snug">
                  {current || done ? subtitles[i] : stage.subtitleLoading}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
