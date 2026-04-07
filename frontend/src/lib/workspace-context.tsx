"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { useSession } from "next-auth/react";

interface Workspace {
  id: string;
  name: string;
  is_active?: boolean;
  created_at: string;
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
  syncUser: () => Promise<UserProfile | null>;
  switchWorkspace: (workspaceId: string) => Promise<void>;
  createWorkspace: (name: string) => Promise<Workspace>;
}

const WorkspaceContext = createContext<WorkspaceContextValue>({
  profile: null,
  activeWorkspace: null,
  workspaces: [],
  loading: true,
  syncUser: async () => null,
  switchWorkspace: async () => {},
  createWorkspace: async () => ({ id: "", name: "", created_at: "" }),
});

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const { data: session, status } = useSession();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  const syncUser = useCallback(async () => {
    if (!session?.user?.email) return null;

    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 20_000);
    try {
      const res = await fetch(`${API_BASE}/api/auth/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: session.user.email,
          name: session.user.name,
          image: session.user.image,
        }),
        signal: controller.signal,
      });

      if (!res.ok) return null;
      const data: UserProfile = await res.json();
      setProfile(data);
      return data;
    } catch {
      /* Timeout (AbortError), offline, or bad JSON — avoid unhandled rejections */
      return null;
    } finally {
      window.clearTimeout(timeoutId);
    }
  }, [session?.user?.email, session?.user?.name, session?.user?.image]);

  const switchWorkspace = useCallback(
    async (workspaceId: string) => {
      if (!session?.user?.email) return;

      await fetch(`${API_BASE}/api/workspaces/${workspaceId}/activate`, {
        method: "POST",
        headers: { "X-User-Email": session.user.email },
      });

      await syncUser();
    },
    [session?.user?.email, syncUser]
  );

  const createWorkspace = useCallback(
    async (name: string): Promise<Workspace> => {
      if (!session?.user?.email) throw new Error("Not authenticated");

      const res = await fetch(`${API_BASE}/api/workspaces`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-User-Email": session.user.email,
        },
        body: JSON.stringify({ name }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Failed" }));
        const d = err.detail;
        if (
          res.status === 403 &&
          d &&
          typeof d === "object" &&
          !Array.isArray(d) &&
          (d as { code?: string }).code === "plan_limit"
        ) {
          throw new Error(String((d as { message?: string }).message ?? "Plan limit"));
        }
        throw new Error(typeof d === "string" ? d : JSON.stringify(d));
      }

      const workspace: Workspace = await res.json();
      await syncUser();
      return workspace;
    },
    [session?.user?.email, syncUser]
  );

  useEffect(() => {
    if (status === "loading") return;

    if (status === "authenticated" && session?.user?.email) {
      void syncUser().finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [status, session?.user?.email, syncUser]);

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
        syncUser,
        switchWorkspace,
        createWorkspace,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  return useContext(WorkspaceContext);
}
