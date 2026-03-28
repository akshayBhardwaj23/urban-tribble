"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
  const queryClient = useQueryClient();
  const [deleteTarget, setDeleteTarget] = useState<DatasetListItem | null>(
    null
  );

  const { data: datasets, isLoading } = useQuery({
    queryKey: ["datasets"],
    queryFn: () =>
      fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/datasets`
      ).then((r) => r.json() as Promise<DatasetListItem[]>),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteDataset(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      setDeleteTarget(null);
    },
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Data Sources</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Every imported file your workspace uses for reporting, insights, and
            forecasts.
          </p>
        </div>
        <Link
          href="/upload"
          className="inline-flex h-9 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          Import Data
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
              No data sources yet. Import a spreadsheet to anchor your first
              metrics.
            </p>
            <Link
              href="/upload"
              className="inline-flex h-9 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              Import Data
            </Link>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3">
          {datasets.map((ds) => (
            <Card
              key={ds.id}
              className="transition-colors hover:bg-accent/50"
            >
              <CardContent className="flex items-center justify-between py-4">
                <Link
                  href={`/datasets/${ds.id}`}
                  className="flex-1 space-y-1"
                >
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
                </Link>
                <div className="flex items-center gap-2 ml-4">
                  <Badge
                    variant={
                      ds.status === "completed" ? "default" : "secondary"
                    }
                    className="text-xs"
                  >
                    {ds.status}
                  </Badge>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:text-destructive h-8 w-8 p-0"
                    onClick={(e) => {
                      e.preventDefault();
                      setDeleteTarget(ds);
                    }}
                  >
                    <span className="text-base">×</span>
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove data source</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            This permanently removes{" "}
            <strong>{deleteTarget?.name}</strong> and all associated insights,
            views, and conversation history. This cannot be undone.
          </p>
          {deleteMutation.isError && (
            <p className="text-sm text-destructive">
              {deleteMutation.error.message}
            </p>
          )}
          <div className="flex justify-end gap-2 mt-2">
            <Button
              variant="outline"
              onClick={() => setDeleteTarget(null)}
              disabled={deleteMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() =>
                deleteTarget && deleteMutation.mutate(deleteTarget.id)
              }
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "Deleting..." : "Delete"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
