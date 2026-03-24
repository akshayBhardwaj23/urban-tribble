"use client";

import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useWorkspace } from "@/lib/workspace-context";
import { setApiUserEmail } from "@/lib/api";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { status, data: session } = useSession();
  const { profile, loading } = useWorkspace();
  const router = useRouter();

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

  if (profile?.needs_onboarding) {
    return null;
  }

  return <>{children}</>;
}
