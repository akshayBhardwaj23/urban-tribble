"use client";

import { useCallback } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FileDropzone } from "@/components/upload/file-dropzone";
import { api } from "@/lib/api";

export default function UploadPage() {
  const router = useRouter();

  const handleUpload = useCallback(
    async (file: File, description: string) => {
      const result = await api.uploadFile(file, description);
      return { dataset_id: result.dataset_id };
    },
    []
  );

  const handleAllComplete = useCallback(
    (datasetIds: string[]) => {
      if (datasetIds.length === 1) {
        router.push(`/datasets/${datasetIds[0]}`);
      } else {
        router.push("/datasets");
      }
    },
    [router]
  );

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Upload Data</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Upload your business data and let AI analyze it for you. You can
          upload multiple files at once.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Select Files</CardTitle>
        </CardHeader>
        <CardContent>
          <FileDropzone
            onUpload={handleUpload}
            onAllComplete={handleAllComplete}
          />
        </CardContent>
      </Card>
    </div>
  );
}
