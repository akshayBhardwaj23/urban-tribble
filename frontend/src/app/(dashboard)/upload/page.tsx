"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  CalendarRange,
  Compass,
  LineChart,
  Megaphone,
  Sparkles,
  TrendingDown,
  Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FileDropzone } from "@/components/upload/file-dropzone";
import { ExpectedInputsList } from "@/components/upload/expected-inputs-list";
import { api } from "@/lib/api";
import type { UploadFileResult } from "@/components/upload/file-dropzone";
import { cn } from "@/lib/utils";
import {
  ANALYSIS_TEMPLATES,
  CUSTOM_ANALYSIS_TEMPLATE,
  type AnalysisTemplate,
} from "@/lib/analysis-templates";

type FlowStep = "choose" | "guided" | "manual";

const TEMPLATE_ICONS: Record<string, LucideIcon> = {
  monthly_business_review: CalendarRange,
  profit_leak_audit: TrendingDown,
  sales_performance: LineChart,
  campaign_efficiency: Megaphone,
  customer_value: Users,
};

export default function UploadPage() {
  const router = useRouter();
  const [flow, setFlow] = useState<FlowStep>("choose");
  const [guidedTemplate, setGuidedTemplate] = useState<AnalysisTemplate | null>(
    null
  );

  const handleUpload = useCallback(
    async (file: File, description: string): Promise<UploadFileResult> => {
      const result = await api.uploadFile(file, description);
      return {
        dataset_id: result.dataset_id,
        ingestion: result.ingestion,
        filename: result.filename,
        file_type: result.file_type,
        row_count: result.row_count,
        column_count: result.column_count,
        all_columns: result.all_columns,
      };
    },
    []
  );

  const handleContinue = useCallback(
    (datasetIds: string[]) => {
      if (datasetIds.length === 1) {
        router.push(`/datasets/${datasetIds[0]}`);
      } else {
        router.push("/datasets");
      }
    },
    [router]
  );

  const goChoose = useCallback(() => {
    setFlow("choose");
    setGuidedTemplate(null);
  }, []);

  const pickGuided = useCallback((t: AnalysisTemplate) => {
    setGuidedTemplate(t);
    setFlow("guided");
  }, []);

  const pickManual = useCallback(() => {
    setGuidedTemplate(null);
    setFlow("manual");
  }, []);

  const activeTemplate: AnalysisTemplate =
    flow === "guided" && guidedTemplate
      ? guidedTemplate
      : CUSTOM_ANALYSIS_TEMPLATE;

  const dropzoneKey =
    flow === "guided" && guidedTemplate ? guidedTemplate.id : "manual";

  return (
    <div className="mx-auto max-w-4xl space-y-10 pb-8">
      {flow === "choose" && (
        <>
          <header className="space-y-8">
            <div className="inline-flex items-center gap-2 rounded-full border border-primary/15 bg-primary/5 px-3.5 py-1.5 text-xs font-medium text-primary">
              <Sparkles className="h-3.5 w-3.5" aria-hidden />
              Import
            </div>

            <div className="space-y-3 max-w-2xl">
              <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-foreground">
                Choose how you want to work
              </h1>
              <p className="text-base text-muted-foreground leading-relaxed">
                Start from a defined business outcome—we show what to upload and what
                analysis you get—or import on your own terms when you already know your
                files.
              </p>
            </div>

            <section
              className="rounded-2xl border border-border/80 bg-card/50 backdrop-blur-sm shadow-sm overflow-hidden"
              aria-labelledby="templates-heading"
            >
              <div className="px-6 sm:px-8 pt-7 pb-5 border-b border-border/50 bg-muted/15">
                <h2
                  id="templates-heading"
                  className="text-sm font-semibold uppercase tracking-wide text-muted-foreground"
                >
                  Analysis templates
                </h2>
                <p className="mt-2 text-sm text-foreground/90 leading-relaxed max-w-xl">
                  Practical, commercially relevant paths. Pick one to see file guidance
                  and the analysis framing before you upload.
                </p>
              </div>

              <ul className="grid gap-3 sm:grid-cols-2 list-none m-0 p-6 sm:p-8 pt-6">
                {ANALYSIS_TEMPLATES.map((t) => {
                  const Icon = TEMPLATE_ICONS[t.id] ?? LineChart;
                  return (
                    <li key={t.id}>
                      <button
                        type="button"
                        onClick={() => pickGuided(t)}
                        className={cn(
                          "w-full h-full text-left rounded-xl border px-5 py-4 transition-all duration-200",
                          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                          "border-border/70 bg-background/90 hover:border-primary/40 hover:bg-background",
                          "shadow-[0_1px_0_rgba(0,0,0,0.03)]"
                        )}
                      >
                        <div className="flex gap-4">
                          <div
                            className={cn(
                              "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
                              "bg-muted/90 text-foreground"
                            )}
                          >
                            <Icon className="h-5 w-5" aria-hidden />
                          </div>
                          <div className="min-w-0 space-y-1.5">
                            <h3 className="text-sm font-semibold text-foreground leading-snug">
                              {t.title}
                            </h3>
                            <p className="text-xs text-muted-foreground leading-relaxed">
                              {t.summary}
                            </p>
                          </div>
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>

              <div className="px-6 sm:px-8 pb-8 pt-0">
                <div className="rounded-xl border border-dashed border-border/70 bg-muted/10 px-5 py-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                  <div className="flex gap-3 min-w-0">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-background border border-border/80">
                      <Compass className="h-5 w-5 text-muted-foreground" aria-hidden />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-foreground">
                        Upload data manually
                      </p>
                      <p className="text-xs text-muted-foreground leading-relaxed mt-0.5">
                        {CUSTOM_ANALYSIS_TEMPLATE.summary}
                      </p>
                    </div>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    className="shrink-0"
                    onClick={pickManual}
                  >
                    Continue without a template
                  </Button>
                </div>
              </div>
            </section>
          </header>
        </>
      )}

      {flow !== "choose" && (
        <>
          <div className="flex items-center">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="-ml-2 text-muted-foreground hover:text-foreground"
              onClick={goChoose}
            >
              <ArrowLeft className="h-4 w-4 mr-1.5" aria-hidden />
              Change path
            </Button>
          </div>

          {flow === "guided" && guidedTemplate && (
            <div className="space-y-8">
              <header className="space-y-2 max-w-2xl">
                <p className="text-xs font-semibold uppercase tracking-wide text-primary">
                  Selected template
                </p>
                <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight text-foreground">
                  {guidedTemplate.title}
                </h1>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {guidedTemplate.summary}
                </p>
              </header>

              <div className="grid gap-5 md:grid-cols-2">
                <div
                  className={cn(
                    "rounded-xl border border-border/80 bg-card/60 px-5 py-5",
                    "shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
                  )}
                >
                  <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    What to upload
                  </h2>
                  <ExpectedInputsList
                    items={guidedTemplate.recommendedInputs}
                    label="Recommended files"
                    className="mt-3"
                  />
                  <p className="mt-3 text-xs text-muted-foreground leading-relaxed">
                    {guidedTemplate.suggestedFiles}
                  </p>
                  {guidedTemplate.bestFor && (
                    <p className="mt-3 text-xs text-muted-foreground leading-relaxed">
                      <span className="font-medium text-foreground/85">Typical users:</span>{" "}
                      {guidedTemplate.bestFor}
                    </p>
                  )}
                </div>
                <div
                  className={cn(
                    "rounded-xl border border-primary/20 bg-primary/5 px-5 py-5",
                    "shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]"
                  )}
                >
                  <h2 className="text-xs font-semibold uppercase tracking-wide text-primary">
                    What you&apos;ll get
                  </h2>
                  <p className="mt-3 text-sm text-foreground leading-relaxed">
                    {guidedTemplate.analysisDelivered}
                  </p>
                </div>
              </div>

              <Card className="border-border/80 shadow-md shadow-black/3 overflow-hidden">
                <CardHeader className="border-b bg-muted/15 pb-5 pt-6 px-6 sm:px-8">
                  <CardTitle className="text-lg font-semibold tracking-tight">
                    Import
                  </CardTitle>
                  <p className="text-sm text-muted-foreground font-normal mt-2 leading-relaxed max-w-2xl">
                    Add one or more files below. Each file is classified and mapped; you
                    confirm before analysis runs. Optional notes help match your intent.
                  </p>
                </CardHeader>
                <CardContent className="pt-8 pb-8 px-6 sm:px-8">
                  <FileDropzone
                    key={dropzoneKey}
                    onUpload={handleUpload}
                    onContinue={handleContinue}
                    analysisTemplate={activeTemplate}
                  />
                </CardContent>
              </Card>
            </div>
          )}

          {flow === "manual" && (
            <div className="space-y-8">
              <header className="space-y-2 max-w-2xl">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Manual import
                </p>
                <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight text-foreground">
                  {CUSTOM_ANALYSIS_TEMPLATE.title}
                </h1>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {CUSTOM_ANALYSIS_TEMPLATE.analysisDelivered}
                </p>
              </header>

              <div
                className={cn(
                  "rounded-xl border border-border/80 bg-card/50 px-5 py-4",
                  "shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
                )}
              >
                <ExpectedInputsList
                  items={CUSTOM_ANALYSIS_TEMPLATE.recommendedInputs}
                  label="Typical inputs"
                />
              </div>

              <Card className="border-border/80 shadow-md shadow-black/3 overflow-hidden">
                <CardHeader className="border-b bg-muted/15 pb-5 pt-6 px-6 sm:px-8">
                  <CardTitle className="text-lg font-semibold tracking-tight">
                    Import
                  </CardTitle>
                  <p className="text-sm text-muted-foreground font-normal mt-2 leading-relaxed max-w-2xl">
                    Structured tables work best—rows as records, columns as fields. You can
                    upload several files in one go; each is understood on its own, then
                    combined in your workspace after you confirm.
                  </p>
                </CardHeader>
                <CardContent className="pt-8 pb-8 px-6 sm:px-8">
                  <FileDropzone
                    key={dropzoneKey}
                    onUpload={handleUpload}
                    onContinue={handleContinue}
                    analysisTemplate={CUSTOM_ANALYSIS_TEMPLATE}
                  />
                </CardContent>
              </Card>
            </div>
          )}
        </>
      )}
    </div>
  );
}
