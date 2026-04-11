"use client";

import { useState } from "react";
import { PlanLimitCallout } from "@/components/plan-limit-callout";
import { useWorkspace } from "@/lib/workspace-context";
import { isApiPlanLimitError, type PlanLimitDetail } from "@/lib/api";
import { maxWorkspacesForPlan } from "@/lib/workspace-plan-limits";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ChevronDown } from "lucide-react";

export function WorkspaceSwitcher() {
  const { activeWorkspace, workspaces, switchWorkspace, createWorkspace, profile } =
    useWorkspace();
  const showChevron = workspaces.length > 1;
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createPlanLimit, setCreatePlanLimit] = useState<PlanLimitDetail | null>(
    null
  );

  const plan = (profile?.subscription_plan ?? "free").toLowerCase();
  const workspaceCap = maxWorkspacesForPlan(plan);
  const atWorkspaceCap = workspaces.length >= workspaceCap;

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = newName.trim();
    if (!trimmed) return;

    setCreating(true);
    setCreateError(null);
    setCreatePlanLimit(null);
    try {
      await createWorkspace(trimmed);
      setNewName("");
      setDialogOpen(false);
    } catch (err) {
      if (isApiPlanLimitError(err)) {
        setCreatePlanLimit(err.detail);
        setCreateError(err.message);
      } else {
        setCreateError(err instanceof Error ? err.message : "Could not create workspace");
      }
    } finally {
      setCreating(false);
    }
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger className="w-full text-left rounded-md px-3 py-2 hover:bg-accent transition-colors outline-none focus:ring-2 focus:ring-ring data-[state=open]:[&_.workspace-chevron]:rotate-180">
          <div className="flex items-center gap-2 min-w-0">
            <div className="flex flex-col items-start gap-0.5 overflow-hidden flex-1 min-w-0">
              <span className="text-xs text-muted-foreground font-normal">
                Workspace
              </span>
              <span className="text-sm font-medium truncate w-full">
                {activeWorkspace?.name ?? "Choose workspace"}
              </span>
            </div>
            {showChevron ? (
              <ChevronDown
                className="workspace-chevron h-4 w-4 shrink-0 text-muted-foreground opacity-70 transition-transform duration-200"
                aria-hidden
              />
            ) : null}
          </div>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-52">
          {workspaces.map((ws) => (
            <DropdownMenuItem
              key={ws.id}
              onClick={() => switchWorkspace(ws.id)}
              className={
                ws.id === activeWorkspace?.id ? "bg-accent" : ""
              }
            >
              {ws.name}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem
            disabled={atWorkspaceCap}
            onClick={() => {
              if (!atWorkspaceCap) setDialogOpen(true);
            }}
            title={
              atWorkspaceCap
                ? `Your plan allows ${workspaceCap} workspace(s). Upgrade for more.`
                : undefined
            }
          >
            New workspace
            {atWorkspaceCap ? (
              <span className="block text-[10px] font-normal text-muted-foreground mt-0.5">
                Limit reached — see Plans
              </span>
            ) : null}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog
        open={dialogOpen}
        onOpenChange={(open) => {
          setDialogOpen(open);
          if (!open) {
            setCreateError(null);
            setCreatePlanLimit(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New workspace</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreate} className="flex flex-col gap-4 mt-2">
            {atWorkspaceCap ? (
              <p className="text-sm text-muted-foreground leading-relaxed">
                Your current plan allows up to {workspaceCap} workspace
                {workspaceCap === 1 ? "" : "s"}. Upgrade to add more.
              </p>
            ) : null}
            <Input
              placeholder="Workspace name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              autoFocus
              disabled={creating || atWorkspaceCap}
            />
            {createPlanLimit ? (
              <PlanLimitCallout detail={createPlanLimit} />
            ) : createError ? (
              <p className="text-sm text-destructive">{createError}</p>
            ) : null}
            <Button
              type="submit"
              disabled={creating || !newName.trim() || atWorkspaceCap}
            >
              {creating ? "Creating…" : "Create"}
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
