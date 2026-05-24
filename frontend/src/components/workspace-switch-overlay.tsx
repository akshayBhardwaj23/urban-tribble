"use client";

import { Loader2 } from "lucide-react";
import { useWorkspace } from "@/lib/workspace-context";

export function WorkspaceSwitchOverlay() {
  const { switching, switchingWorkspaceName } = useWorkspace();

  if (!switching) return null;

  return (
    <div
      className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-background/85 backdrop-blur-[2px]"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" aria-hidden />
      <div className="text-center px-6">
        <p className="text-sm font-medium text-foreground">Switching workspace</p>
        {switchingWorkspaceName ? (
          <p className="mt-1 text-xs text-muted-foreground">{switchingWorkspaceName}</p>
        ) : null}
      </div>
    </div>
  );
}
