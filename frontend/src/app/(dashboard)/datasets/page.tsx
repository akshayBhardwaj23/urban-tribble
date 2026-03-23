"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";

interface DatasetListItem {
  id: string;
  name: string;
  upload_id: string;
  row_count: number | null;
  column_count: number | null;
  status: string;
  user_description: string | null;
  created_at: string;
}

export default function DatasetsPage() {
  const { data: datasets, isLoading } = useQuery({
    queryKey: ["datasets"],
    queryFn: () =>
      fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/datasets`).then(
        (r) => r.json() as Promise<DatasetListItem[]>
      ),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Datasets</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Your uploaded files and their analyses.
          </p>
        </div>
        <Link
          href="/upload"
          className="inline-flex h-9 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          Upload File
        </Link>
      </div>

      {isLoading ? (
        <div className="grid gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : !datasets || datasets.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12 text-center">
            <p className="text-sm text-muted-foreground mb-4">
              No datasets yet. Upload a file to get started.
            </p>
            <Link
              href="/upload"
              className="inline-flex h-9 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              Upload File
            </Link>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3">
          {datasets.map((ds) => (
            <Link key={ds.id} href={`/datasets/${ds.id}`}>
              <Card className="transition-colors hover:bg-accent/50 cursor-pointer">
                <CardContent className="flex items-center justify-between py-4">
                  <div className="space-y-1">
                    <p className="text-sm font-medium">{ds.name}</p>
                    {ds.user_description && (
                      <p className="text-xs text-muted-foreground">
                        {ds.user_description}
                      </p>
                    )}
                    <p className="text-xs text-muted-foreground">
                      {ds.row_count?.toLocaleString()} rows ·{" "}
                      {ds.column_count} columns ·{" "}
                      {new Date(ds.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <Badge
                    variant={
                      ds.status === "completed" ? "default" : "secondary"
                    }
                    className="text-xs"
                  >
                    {ds.status}
                  </Badge>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
