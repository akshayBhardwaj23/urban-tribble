"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

const ACCEPTED_TYPES = {
  "text/csv": [".csv"],
  "text/tab-separated-values": [".tsv"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [
    ".xlsx",
  ],
  "application/vnd.ms-excel": [".xls"],
};

interface FileEntry {
  file: File;
  description: string;
  status: "pending" | "uploading" | "done" | "error";
  error?: string;
  datasetId?: string;
}

interface UploadResult {
  dataset_id: string;
}

interface FileDropzoneProps {
  onUpload: (file: File, description: string) => Promise<UploadResult>;
  onAllComplete: (datasetIds: string[]) => void;
}

export function FileDropzone({ onUpload, onAllComplete }: FileDropzoneProps) {
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [uploading, setUploading] = useState(false);

  const onDrop = useCallback((accepted: File[]) => {
    const newEntries: FileEntry[] = accepted.map((file) => ({
      file,
      description: "",
      status: "pending" as const,
    }));
    setEntries((prev) => [...prev, ...newEntries]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_TYPES,
    maxSize: 50 * 1024 * 1024,
    disabled: uploading,
  });

  const updateEntry = (index: number, updates: Partial<FileEntry>) => {
    setEntries((prev) =>
      prev.map((e, i) => (i === index ? { ...e, ...updates } : e))
    );
  };

  const removeEntry = (index: number) => {
    setEntries((prev) => prev.filter((_, i) => i !== index));
  };

  const handleUploadAll = async () => {
    setUploading(true);
    const completedIds: string[] = [];

    for (let i = 0; i < entries.length; i++) {
      const entry = entries[i];
      if (entry.status === "done") {
        if (entry.datasetId) completedIds.push(entry.datasetId);
        continue;
      }

      updateEntry(i, { status: "uploading" });
      try {
        const result = await onUpload(entry.file, entry.description);
        updateEntry(i, { status: "done", datasetId: result.dataset_id });
        completedIds.push(result.dataset_id);
      } catch (err) {
        updateEntry(i, {
          status: "error",
          error: err instanceof Error ? err.message : "Upload failed",
        });
      }
    }

    setUploading(false);

    if (completedIds.length > 0) {
      onAllComplete(completedIds);
    }
  };

  const pendingCount = entries.filter((e) => e.status !== "done").length;
  const currentlyUploading = entries.find((e) => e.status === "uploading");

  if (uploading && currentlyUploading) {
    const doneCount = entries.filter((e) => e.status === "done").length;
    const total = entries.length;

    return (
      <div className="flex flex-col items-center justify-center py-12 gap-5">
        <div className="relative h-16 w-16">
          <div className="absolute inset-0 rounded-full border-4 border-muted" />
          <div className="absolute inset-0 rounded-full border-4 border-primary border-t-transparent animate-spin" />
        </div>
        <div className="text-center space-y-1">
          <p className="text-sm font-medium">
            Processing {currentlyUploading.file.name}...
          </p>
          <p className="text-xs text-muted-foreground">
            Cleaning data, detecting columns, building metadata
          </p>
          <p className="text-xs text-muted-foreground mt-2">
            {doneCount} of {total} files completed
          </p>
        </div>
        <div className="w-full max-w-xs bg-muted rounded-full h-2 overflow-hidden">
          <div
            className="bg-primary h-full rounded-full transition-all duration-500"
            style={{ width: `${((doneCount + 0.5) / total) * 100}%` }}
          />
        </div>
      </div>
    );
  }

  if (entries.length > 0 && !uploading) {
    return (
      <div className="space-y-4">
        {entries.map((entry, index) => (
          <div
            key={`${entry.file.name}-${index}`}
            className={`rounded-lg border p-4 space-y-3 ${
              entry.status === "done"
                ? "bg-green-50 border-green-200 dark:bg-green-950/20 dark:border-green-800"
                : entry.status === "error"
                  ? "bg-red-50 border-red-200 dark:bg-red-950/20 dark:border-red-800"
                  : "bg-card"
            }`}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary/10 text-sm font-medium">
                  {entry.file.name.split(".").pop()?.toUpperCase()}
                </div>
                <div>
                  <p className="text-sm font-medium">{entry.file.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {(entry.file.size / 1024).toFixed(1)} KB
                    {entry.status === "done" && " -- Uploaded"}
                    {entry.status === "error" && ` -- ${entry.error}`}
                  </p>
                </div>
              </div>
              {entry.status === "pending" && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => removeEntry(index)}
                >
                  Remove
                </Button>
              )}
            </div>

            {entry.status !== "done" && (
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground">
                  What does this file represent?
                </label>
                <Textarea
                  placeholder='e.g., "Monthly revenue data", "Customer purchase history"'
                  value={entry.description}
                  onChange={(e) =>
                    updateEntry(index, { description: e.target.value })
                  }
                  rows={2}
                  className="text-sm"
                />
              </div>
            )}
          </div>
        ))}

        <div
          {...getRootProps()}
          className="cursor-pointer rounded-lg border-2 border-dashed p-4 text-center transition-colors border-muted-foreground/25 hover:border-primary/50"
        >
          <input {...getInputProps()} />
          <p className="text-xs text-muted-foreground">
            + Drop more files here or click to add
          </p>
        </div>

        <div className="flex items-center justify-between pt-2">
          <p className="text-sm text-muted-foreground">
            {entries.length} file{entries.length !== 1 ? "s" : ""} selected
          </p>
          <div className="flex gap-2">
            {pendingCount > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  setEntries((prev) => prev.filter((e) => e.status === "done"))
                }
              >
                Clear Pending
              </Button>
            )}
            <Button
              onClick={handleUploadAll}
              disabled={pendingCount === 0}
            >
              Upload & Analyze{pendingCount > 0 ? ` (${pendingCount})` : ""}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      {...getRootProps()}
      className={`cursor-pointer rounded-lg border-2 border-dashed p-12 text-center transition-colors ${
        isDragActive
          ? "border-primary bg-primary/5"
          : "border-muted-foreground/25 hover:border-primary/50"
      }`}
    >
      <input {...getInputProps()} />
      <div className="flex flex-col items-center gap-3">
        <div className="flex h-14 w-14 items-center justify-center rounded-full bg-muted text-2xl">
          ↑
        </div>
        <div>
          <p className="text-sm font-medium">
            {isDragActive
              ? "Drop your files here"
              : "Drag & drop your files here, or click to browse"}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Supports .xlsx, .xls, .csv, .tsv (max 50MB each) -- multiple files
            allowed
          </p>
        </div>
      </div>
    </div>
  );
}
