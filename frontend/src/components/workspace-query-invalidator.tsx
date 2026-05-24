"use client";

import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useWorkspace } from "@/lib/workspace-context";
import { invalidateWorkspaceScopedQueries } from "@/lib/workspace-queries";

/**
 * When the active workspace changes, invalidate scoped dashboard/API data so lists and
 * charts refetch for the correct tenant. (Cache is cleared immediately in switchWorkspace.)
 */
export function WorkspaceQueryInvalidator() {
  const { activeWorkspace, loading, switching } = useWorkspace();
  const queryClient = useQueryClient();
  const prevId = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (loading || switching) return;
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
      invalidateWorkspaceScopedQueries(queryClient);
    }
  }, [activeWorkspace?.id, loading, switching, queryClient]);

  return null;
}
