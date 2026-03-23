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

interface FileDropzoneProps {
  onUpload: (file: File, description: string) => void;
  isUploading: boolean;
}

export function FileDropzone({ onUpload, isUploading }: FileDropzoneProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [description, setDescription] = useState("");

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted.length > 0) {
      setSelectedFile(accepted[0]);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_TYPES,
    maxFiles: 1,
    maxSize: 50 * 1024 * 1024,
  });

  const handleSubmit = () => {
    if (selectedFile) {
      onUpload(selectedFile, description);
    }
  };

  const handleReset = () => {
    setSelectedFile(null);
    setDescription("");
  };

  if (selectedFile) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between rounded-lg border bg-card p-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary/10 text-sm font-medium">
              {selectedFile.name.split(".").pop()?.toUpperCase()}
            </div>
            <div>
              <p className="text-sm font-medium">{selectedFile.name}</p>
              <p className="text-xs text-muted-foreground">
                {(selectedFile.size / 1024).toFixed(1)} KB
              </p>
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={handleReset}>
            Remove
          </Button>
        </div>

        <div className="space-y-2">
          <label
            htmlFor="description"
            className="text-sm font-medium leading-none"
          >
            What does this file represent?
          </label>
          <Textarea
            id="description"
            placeholder='e.g., "Monthly revenue data from Jan 2023 to Dec 2025", "Customer purchase history", "Quarterly expense report"'
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
          />
          <p className="text-xs text-muted-foreground">
            This helps the AI understand your data better and provide more
            accurate analysis.
          </p>
        </div>

        <Button
          onClick={handleSubmit}
          disabled={isUploading}
          className="w-full"
        >
          {isUploading ? "Uploading & Analyzing..." : "Upload & Analyze"}
        </Button>
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
              ? "Drop your file here"
              : "Drag & drop your file here, or click to browse"}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Supports .xlsx, .xls, .csv, .tsv (max 50MB)
          </p>
        </div>
      </div>
    </div>
  );
}
