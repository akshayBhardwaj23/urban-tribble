"use client";

import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useWorkspace } from "@/lib/workspace-context";
import { setApiUserEmail } from "@/lib/api";
import {
  API_UNAVAILABLE_DESCRIPTION,
  API_UNAVAILABLE_TITLE,
} from "@/lib/api-errors";
import { Button } from "@/components/ui/button";

const IS_DEV = process.env.NODE_ENV === "development";
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
