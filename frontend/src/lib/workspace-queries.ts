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
  // Chat and integrations are per-workspace too: leaving them cached meant the
  // previous workspace's conversation stayed on screen after a switch.
  "chat-history",
  "integrations",
  "integration-oauth-session",
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
