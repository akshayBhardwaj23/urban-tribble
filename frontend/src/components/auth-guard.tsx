"use client";

import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useWorkspace } from "@/lib/workspace-context";
import { setApiUserEmail } from "@/lib/api";
import { Button } from "@/components/ui/button";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { status, data: session } = useSession();
  const { profile, loading, syncUser } = useWorkspace();
  const router = useRouter();
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/login");
    }
  }, [status, router]);

  useEffect(() => {
    if (!loading && profile && profile.needs_onboarding) {
      router.replace("/onboarding");
    }
  }, [loading, profile, router]);

  useEffect(() => {
    if (session?.user?.email) {
      setApiUserEmail(session.user.email);
    }
  }, [session?.user?.email]);

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

  if (!loading && session?.user?.email && !profile) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-8 text-center">
        <div className="max-w-md space-y-2">
          <h1 className="text-lg font-semibold tracking-tight">
            Can&apos;t reach the API
          </h1>
          <p className="text-sm text-muted-foreground leading-relaxed">
            The app could not load your account from the backend. Start the API
            (usually port 8000), confirm{" "}
            <code className="rounded bg-muted px-1 py-0.5 text-xs">
              NEXT_PUBLIC_API_URL
            </code>{" "}
            in{" "}
            <code className="rounded bg-muted px-1 py-0.5 text-xs">
              frontend/.env.local
            </code>{" "}
            matches that server, then retry.
          </p>
          <p className="text-xs text-muted-foreground break-all">
            {API_URL}
          </p>
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
