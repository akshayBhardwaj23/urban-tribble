"use client";

import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useWorkspace } from "@/lib/workspace-context";

const INVALIDATE_PREFIXES = new Set([
  "overview",
  "overview-analysis",
  "summaries-latest",
  "workspace-timeline",
  "workspace-compare",
  "datasets",
  "datasets-list",
  "dataset",
  "analysis",
  "dashboard-data",
  "dataset-preview",
]);

/**
 * When the active workspace changes, drop cached dashboard/API data so lists and
 * charts refetch for the correct tenant.
 */
export function WorkspaceQueryInvalidator() {
  const { activeWorkspace, loading } = useWorkspace();
  const queryClient = useQueryClient();
  const prevId = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (loading) return;
    const id = activeWorkspace?.id;
    if (!id) {
      prevId.current = undefined;
      return;
    }
    if (prevId.current === undefined) {
      prevId.current = id;
      return;
    }
    if (prevId.current !== id) {
      prevId.current = id;
      queryClient.invalidateQueries({
        predicate: (q) => {
          const k0 = q.queryKey[0];
          return typeof k0 === "string" && INVALIDATE_PREFIXES.has(k0);
        },
      });
    }
  }, [activeWorkspace?.id, loading, queryClient]);

  return null;
}
