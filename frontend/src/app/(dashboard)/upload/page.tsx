"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FileDropzone } from "@/components/upload/file-dropzone";
import { api } from "@/lib/api";

export default function UploadPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  const uploadMutation = useMutation({
    mutationFn: ({ file, description }: { file: File; description: string }) =>
      api.uploadFile(file, description),
    onSuccess: (data) => {
      router.push(`/datasets/${data.dataset_id}`);
    },
    onError: (err: Error) => {
      setError(err.message);
    },
  });

  const handleUpload = (file: File, description: string) => {
    setError(null);
    uploadMutation.mutate({ file, description });
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Upload Data</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Upload your business data and let AI analyze it for you.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Select File</CardTitle>
        </CardHeader>
        <CardContent>
          <FileDropzone
            onUpload={handleUpload}
            isUploading={uploadMutation.isPending}
          />
          {error && (
            <p className="mt-3 text-sm text-destructive">{error}</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
