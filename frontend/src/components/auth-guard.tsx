"use client";

import { signOut, useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useWorkspace } from "@/lib/workspace-context";
import { setApiAccessToken } from "@/lib/api";
import { resolveApiBase } from "@/lib/api-base";
import {
  API_UNAVAILABLE_DESCRIPTION,
  API_UNAVAILABLE_TITLE,
} from "@/lib/api-errors";
import { Button } from "@/components/ui/button";

const IS_DEV = process.env.NODE_ENV === "development";
const API_URL = resolveApiBase();

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { status, data: session } = useSession();
  const { profile, loading, syncUser, endExpiredSession } = useWorkspace();
  const router = useRouter();
  const [retrying, setRetrying] = useState(false);
  const sessionExpired = session?.error === "SessionExpired";

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/login");
    }
  }, [status, router]);

  // NextAuth could not renew the API token (backend down long enough for it to
  // lapse, or the account is gone). Only a fresh sign-in recovers from here.
  useEffect(() => {
    if (status === "authenticated" && sessionExpired) {
      endExpiredSession();
    }
  }, [status, sessionExpired, endExpiredSession]);

  useEffect(() => {
    if (!loading && profile && profile.needs_onboarding) {
      router.replace("/onboarding");
    }
  }, [loading, profile, router]);

  useEffect(() => {
    if (session?.accessToken) {
      setApiAccessToken(session.accessToken);
    }
  }, [session?.accessToken]);

  if (status === "loading" || loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (status === "unauthenticated") {
    return null;
  }

  // Sign-out is already under way; don't flash a config error on the way out.
  if (sessionExpired) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">
          Your session expired. Taking you to sign in…
        </p>
      </div>
    );
  }

  // Signed into NextAuth but bootstrap never issued an API token (usually a
  // mismatched INTERNAL_AUTH_SECRET). Show a clear failure instead of an empty shell.
  if (!loading && status === "authenticated" && !session?.accessToken) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
        <div className="max-w-md space-y-2">
          <h1 className="text-lg font-semibold tracking-tight">
            Could not connect your session to the API
          </h1>
          <p className="text-sm text-muted-foreground leading-relaxed">
            Sign-in succeeded, but the app could not obtain an API access token.
            Confirm INTERNAL_AUTH_SECRET matches on the frontend and backend, then
            sign out and try again.
          </p>
          {IS_DEV ? (
            <p className="text-xs text-muted-foreground break-all">{API_URL}</p>
          ) : null}
        </div>
        <Button
          type="button"
          onClick={() => void signOut({ callbackUrl: "/login" })}
        >
          Back to sign in
        </Button>
      </div>
    );
  }

  if (!loading && session?.accessToken && !profile) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
        <div className="max-w-md space-y-2">
          <h1 className="text-lg font-semibold tracking-tight">
            {API_UNAVAILABLE_TITLE}
          </h1>
          <p className="text-sm text-muted-foreground leading-relaxed">
            {API_UNAVAILABLE_DESCRIPTION}
          </p>
          {IS_DEV ? (
            <p className="text-xs text-muted-foreground break-all">{API_URL}</p>
          ) : null}
        </div>
        <Button
          type="button"
          disabled={retrying}
          onClick={async () => {
            setRetrying(true);
            try {
              await syncUser();
            } finally {
              setRetrying(false);
            }
          }}
        >
          {retrying ? "Retrying…" : "Retry"}
        </Button>
      </div>
    );
  }

  if (profile?.needs_onboarding) {
    return null;
  }

  return <>{children}</>;
}
