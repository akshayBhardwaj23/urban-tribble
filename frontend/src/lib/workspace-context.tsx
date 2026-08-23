"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { getSession, signOut, useSession } from "next-auth/react";
import { useQueryClient } from "@tanstack/react-query";

import {
  api,
  getApiAccessToken,
  setApiAccessToken,
  setApiSessionHandlers,
  type ApiUserProfile,
  type ApiWorkspace,
} from "@/lib/api";
import { clearWorkspaceScopedQueries } from "@/lib/workspace-queries";

type Workspace = ApiWorkspace;
type UserProfile = ApiUserProfile;

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
  /** Sign out and land on /login with an explanation. Idempotent. */
  endExpiredSession: () => void;
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
  endExpiredSession: () => {},
});

/** Where an unrecoverable session lands, so /login can explain what happened. */
export const SESSION_EXPIRED_URL = "/login?reason=session-expired";

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const { data: session, status } = useSession();
  const queryClient = useQueryClient();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState(false);
  const [switchingWorkspaceName, setSwitchingWorkspaceName] = useState<
    string | null
  >(null);
  const endingSession = useRef(false);

  useEffect(() => {
    if (status === "authenticated" && session?.accessToken) {
      setApiAccessToken(session.accessToken);
    }
    if (status === "unauthenticated") {
      setApiAccessToken(null);
      setProfile(null);
    }
  }, [status, session?.accessToken]);

  /**
   * Pull a renewed API token from NextAuth, which re-mints it server-side when
   * it is close to expiring. Returns null when nothing newer is available.
   *
   * Deliberately a plain session read rather than useSession().update(): the
   * latter flips the provider to "loading" and blanks the page mid-renewal.
   * The provider's own snapshot catches up on its next refetch, and
   * setApiAccessToken ignores that older token in the meantime.
   */
  const renewAccessToken = useCallback(async (): Promise<string | null> => {
    const previous = getApiAccessToken();
    let next: string | null = null;
    try {
      const fetched = await getSession();
      next = fetched?.accessToken ?? null;
    } catch {
      return null;
    }
    if (!next || next === previous) return null;
    setApiAccessToken(next);
    return next;
  }, []);

  /** Last resort when the session cannot be renewed: send the user to sign in. */
  const endExpiredSession = useCallback(() => {
    if (endingSession.current) return;
    endingSession.current = true;
    setApiAccessToken(null);
    void signOut({ callbackUrl: SESSION_EXPIRED_URL });
  }, []);

  useEffect(() => {
    setApiSessionHandlers({
      renew: renewAccessToken,
      onExpired: endExpiredSession,
    });
  }, [renewAccessToken, endExpiredSession]);

  const syncUser = useCallback(async () => {
    if (!session?.accessToken) return null;
    setApiAccessToken(session.accessToken);

    try {
      const data = await api.syncUser({
        name: session.user?.name ?? null,
        image: session.user?.image ?? null,
      });
      setProfile(data);
      return data;
    } catch {
      /* Expired session, timeout, or offline - handled by the caller's UI. */
      return null;
    }
  }, [session?.accessToken, session?.user?.name, session?.user?.image]);

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
        await api.activateWorkspace(workspaceId);
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

      const workspace = await api.createWorkspace(name);
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
        endExpiredSession,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  return useContext(WorkspaceContext);
}
