"use client";

import { useState } from "react";
import { useWorkspace } from "@/lib/workspace-context";
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

export function WorkspaceSwitcher() {
  const { activeWorkspace, workspaces, switchWorkspace, createWorkspace } =
    useWorkspace();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = newName.trim();
    if (!trimmed) return;

    setCreating(true);
    try {
      await createWorkspace(trimmed);
      setNewName("");
      setDialogOpen(false);
    } finally {
      setCreating(false);
    }
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger className="w-full text-left rounded-md px-3 py-2 hover:bg-accent transition-colors outline-none focus:ring-2 focus:ring-ring">
          <div className="flex flex-col items-start gap-0.5 overflow-hidden">
            <span className="text-xs text-muted-foreground font-normal">
              Workspace
            </span>
            <span className="text-sm font-medium truncate w-full">
              {activeWorkspace?.name ?? "Select workspace"}
            </span>
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
          <DropdownMenuItem onClick={() => setDialogOpen(true)}>
            + New Workspace
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create a new workspace</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreate} className="flex flex-col gap-4 mt-2">
            <Input
              placeholder="Workspace name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              autoFocus
              disabled={creating}
            />
            <Button type="submit" disabled={creating || !newName.trim()}>
              {creating ? "Creating..." : "Create"}
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
