import type { QueryClient } from "@tanstack/react-query";

/** Query key prefixes scoped to the active workspace (cleared on switch). */
export const WORKSPACE_SCOPED_QUERY_PREFIXES = new Set([
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

export function clearWorkspaceScopedQueries(queryClient: QueryClient): void {
  queryClient.removeQueries({
    predicate: (q) => {
      const k0 = q.queryKey[0];
      return typeof k0 === "string" && WORKSPACE_SCOPED_QUERY_PREFIXES.has(k0);
    },
  });
}

export function invalidateWorkspaceScopedQueries(queryClient: QueryClient): void {
  queryClient.invalidateQueries({
    predicate: (q) => {
      const k0 = q.queryKey[0];
      return typeof k0 === "string" && WORKSPACE_SCOPED_QUERY_PREFIXES.has(k0);
    },
  });
}
