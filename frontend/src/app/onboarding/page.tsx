"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useWorkspace } from "@/lib/workspace-context";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { PRODUCT_NAME } from "@/lib/brand";
import { ThemeMenuCompact } from "@/components/theme-menu";
import { trackEvent } from "@/lib/analytics";

export default function OnboardingPage() {
  const { status } = useSession();
  const { createWorkspace, profile, loading } = useWorkspace();
  const router = useRouter();
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/login");
    }
  }, [status, router]);

  useEffect(() => {
    if (!loading && profile && profile.workspaces.length > 0) {
      router.replace("/dashboard");
    }
  }, [loading, profile, router]);

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

  if (profile && profile.workspaces.length > 0) {
    return null;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Workspace name is required");
      return;
    }

    setSubmitting(true);
    setError("");
    try {
      await createWorkspace(trimmed);
      trackEvent("workspace_created");
      router.push("/upload");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-muted/30 px-4">
      <div className="absolute right-4 top-4 sm:right-6 sm:top-6">
        <ThemeMenuCompact />
      </div>
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-bold tracking-tight">
          Welcome to {PRODUCT_NAME}
        </h1>
        <p className="mt-2 text-muted-foreground max-w-md mx-auto">
          Name a workspace to hold your sources and briefings. Next, you&apos;ll import a
          file so charts and the AI briefing can run.
        </p>
        <p className="mt-3 text-xs text-muted-foreground max-w-md mx-auto leading-relaxed">
          By continuing, you agree to our{" "}
          <Link href="/terms" className="underline underline-offset-2">
            Terms
          </Link>{" "}
          and{" "}
          <Link href="/privacy" className="underline underline-offset-2">
            Privacy
          </Link>{" "}
          summary.
        </p>
      </div>

      <Card className="w-full max-w-md">
        <CardContent className="pt-6 pb-6">
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div>
              <label
                htmlFor="workspace-name"
                className="text-sm font-medium block mb-1.5"
              >
                Workspace name
              </label>
              <Input
                id="workspace-name"
                placeholder="e.g. My Business, Acme Corp, Side Hustle"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoFocus
                disabled={submitting}
              />
              <p className="mt-1.5 text-xs text-muted-foreground">
                A workspace isolates data sources, business health views, and
                insights for one business or initiative. Add more workspaces anytime.
              </p>
            </div>

            {error && (
              <p className="text-sm text-red-600">{error}</p>
            )}

            <Button type="submit" disabled={submitting} className="h-11">
              {submitting ? "Creating..." : "Create Workspace"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
