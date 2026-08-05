"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { useSession } from "next-auth/react";
import { useQueryClient } from "@tanstack/react-query";

import {
  api,
  getApiAccessToken,
  planLimitErrorFromJson,
  setApiAccessToken,
} from "@/lib/api";
import { resolveApiBase } from "@/lib/api-base";
import { clearWorkspaceScopedQueries } from "@/lib/workspace-queries";

interface Workspace {
  id: string;
  name: string;
  is_active?: boolean;
  created_at: string;
  /** Saved Outlook chart source; omit or null = automatic (largest qualifying file). */
  outlook_forecast_dataset_id?: string | null;
  outlook_forecast_date_column?: string | null;
  outlook_forecast_value_column?: string | null;
}

interface UserProfile {
  id: string;
  email: string;
  name: string | null;
  image: string | null;
  active_workspace_id: string | null;
  needs_onboarding: boolean;
  subscription_plan?: string;
  subscription_renews_at?: string | null;
  workspaces: Workspace[];
}

interface WorkspaceContextValue {
  profile: UserProfile | null;
  activeWorkspace: Workspace | null;
  workspaces: Workspace[];
  loading: boolean;
  /** True while activating another workspace and refetching scoped data. */
  switching: boolean;
  switchingWorkspaceName: string | null;
  syncUser: () => Promise<UserProfile | null>;
  switchWorkspace: (workspaceId: string) => Promise<void>;
  createWorkspace: (name: string) => Promise<Workspace>;
  deleteWorkspace: (workspaceId: string) => Promise<void>;
}

const WorkspaceContext = createContext<WorkspaceContextValue>({
  profile: null,
  activeWorkspace: null,
  workspaces: [],
  loading: true,
  switching: false,
  switchingWorkspaceName: null,
  syncUser: async () => null,
  switchWorkspace: async () => {},
  createWorkspace: async () => ({ id: "", name: "", created_at: "" }),
  deleteWorkspace: async () => {},
});

const API_BASE = resolveApiBase();

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = { ...(extra || {}) };
  const token = getApiAccessToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const { data: session, status } = useSession();
  const queryClient = useQueryClient();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState(false);
  const [switchingWorkspaceName, setSwitchingWorkspaceName] = useState<
    string | null
  >(null);

  useEffect(() => {
    if (status === "authenticated" && session?.accessToken) {
      setApiAccessToken(session.accessToken);
    }
    if (status === "unauthenticated") {
      setApiAccessToken(null);
      setProfile(null);
    }
  }, [status, session?.accessToken]);

  const syncUser = useCallback(async () => {
    if (!session?.accessToken) return null;
    setApiAccessToken(session.accessToken);

    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 20_000);
    try {
      const res = await fetch(`${API_BASE}/api/auth/sync`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          name: session.user?.name ?? null,
          image: session.user?.image ?? null,
        }),
        signal: controller.signal,
      });

      if (!res.ok) return null;
      const data: UserProfile = await res.json();
      setProfile(data);
      return data;
    } catch {
      /* Timeout (AbortError), offline, or bad JSON - avoid unhandled rejections */
      return null;
    } finally {
      window.clearTimeout(timeoutId);
    }
  }, [
    session?.accessToken,
    session?.user?.name,
    session?.user?.image,
  ]);

  const switchWorkspace = useCallback(
    async (workspaceId: string) => {
      if (!session?.accessToken) return;
      if (profile?.active_workspace_id === workspaceId) return;
      setApiAccessToken(session.accessToken);

      const target = profile?.workspaces.find((w) => w.id === workspaceId);
      setSwitching(true);
      setSwitchingWorkspaceName(target?.name ?? null);
      clearWorkspaceScopedQueries(queryClient);

      setProfile((prev) =>
        prev ? { ...prev, active_workspace_id: workspaceId } : prev
      );

      try {
        const res = await fetch(
          `${API_BASE}/api/workspaces/${workspaceId}/activate`,
          {
            method: "POST",
            headers: authHeaders(),
          }
        );
        if (!res.ok) {
          throw new Error("Failed to switch workspace");
        }
        await syncUser();
      } catch {
        await syncUser();
        throw new Error("Could not switch workspace");
      } finally {
        setSwitching(false);
        setSwitchingWorkspaceName(null);
      }
    },
    [
      session?.accessToken,
      profile?.active_workspace_id,
      profile?.workspaces,
      queryClient,
      syncUser,
    ]
  );

  const createWorkspace = useCallback(
    async (name: string): Promise<Workspace> => {
      if (!session?.accessToken) throw new Error("Not authenticated");
      setApiAccessToken(session.accessToken);

      const res = await fetch(`${API_BASE}/api/workspaces`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ name }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Failed" }));
        const pl = planLimitErrorFromJson(res.status, err);
        if (pl) throw pl;
        const d = err.detail;
        throw new Error(typeof d === "string" ? d : JSON.stringify(d));
      }

      const workspace: Workspace = await res.json();
      await syncUser();
      return workspace;
    },
    [session?.accessToken, syncUser]
  );

  const deleteWorkspace = useCallback(
    async (workspaceId: string) => {
      if (!session?.accessToken) throw new Error("Not authenticated");
      setApiAccessToken(session.accessToken);
      await api.deleteWorkspace(workspaceId);
      await syncUser();
    },
    [session?.accessToken, syncUser]
  );

  useEffect(() => {
    if (status === "loading") return;

    if (status === "authenticated" && session?.accessToken) {
      void syncUser().finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [status, session?.accessToken, syncUser]);

  const activeWorkspace =
    profile?.workspaces.find(
      (w) => w.id === profile.active_workspace_id
    ) ?? null;

  return (
    <WorkspaceContext.Provider
      value={{
        profile,
        activeWorkspace,
        workspaces: profile?.workspaces ?? [],
        loading,
        switching,
        switchingWorkspaceName,
        syncUser,
        switchWorkspace,
        createWorkspace,
        deleteWorkspace,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  return useContext(WorkspaceContext);
}
