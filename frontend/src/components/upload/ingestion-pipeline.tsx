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

interface IngestionPipelineProps {
  isLoading: boolean;
  filename: string;
  fileType: string;
  ingestion: IngestionProfile | null;
  className?: string;
}

export function IngestionPipeline({
  isLoading,
  filename,
  fileType,
  ingestion,
  className,
}: IngestionPipelineProps) {
  const [warmup, setWarmup] = useState(0);

  useEffect(() => {
    if (!isLoading) {
      setWarmup(0);
      return;
    }
    setWarmup(0);
    const a = window.setTimeout(() => setWarmup(1), 280);
    const b = window.setTimeout(() => setWarmup(2), 620);
    return () => {
      window.clearTimeout(a);
      window.clearTimeout(b);
    };
  }, [isLoading, filename]);

  const typeDescription = fileTypeLabel(fileType);

  const issuesSubtitle = (() => {
    if (!ingestion) return STAGES[4].subtitleLoading;
    const warns = ingestion.flags.filter((f) => f.kind === "warning");
    if (warns.length === 0 && ingestion.flags.length === 0) {
      return "No structure issues at import—still run your normal read on trends and margin.";
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
    ? `${ingestion.classification.label} · ${ingestion.classification.confidence === "high" ? "Strong match" : ingestion.classification.confidence === "medium" ? "Likely match—confirm if unsure" : "Uncertain—confirm before you rely on it"}`
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
    activeIndex = Math.min(warmup, 2);
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
                    "absolute left-[11px] top-7 bottom-0 w-px",
                    done ? "bg-primary/35" : "bg-border"
                  )}
                  aria-hidden
                />
              )}
              <div className="relative z-1 flex h-6 w-6 shrink-0 items-center justify-center">
                {done ? (
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-semibold">
                    ✓
                  </span>
                ) : current ? (
                  <span className="flex h-6 w-6 items-center justify-center rounded-full border-2 border-primary border-t-transparent animate-spin" />
                ) : (
                  <span className="h-2.5 w-2.5 rounded-full bg-muted-foreground/25" />
                )}
              </div>
              <div className={cn("min-w-0 pt-0.5", pending && "opacity-45")}>
                <p className="text-sm font-medium leading-tight">{stage.title}</p>
                <p className="text-xs text-muted-foreground mt-0.5 leading-snug">
                  {subtitles[i] ?? stage.subtitleLoading}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
