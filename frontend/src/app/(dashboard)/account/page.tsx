"use client";

import Link from "next/link";
import { useSession } from "next-auth/react";
import { useQuery } from "@tanstack/react-query";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, setApiUserEmail } from "@/lib/api";
import { maxWorkspacesForPlan } from "@/lib/workspace-plan-limits";
import { cn } from "@/lib/utils";

function planLabel(id: string | undefined) {
  const p = (id ?? "free").toLowerCase();
  if (p === "starter") return "Starter";
  if (p === "pro") return "Pro";
  return "Free";
}

export default function AccountPage() {
  const { data: session, status } = useSession();

  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ["auth-me", session?.user?.email ?? "none"],
    queryFn: async () => {
      if (!session?.user?.email) throw new Error("Not signed in");
      setApiUserEmail(session.user.email);
      return api.getAuthMe();
    },
    enabled: status === "authenticated" && Boolean(session?.user?.email),
  });

  if (status === "loading" || (status === "authenticated" && isPending && !data)) {
    return (
      <div className="mx-auto max-w-2xl space-y-6">
        <Skeleton className="h-9 w-48" />
        <Skeleton className="h-40 w-full rounded-xl" />
        <Skeleton className="h-32 w-full rounded-xl" />
      </div>
    );
  }

  if (status !== "authenticated" || !session?.user) {
    return (
      <p className="text-sm text-muted-foreground">
        Sign in to view your account.
      </p>
    );
  }

  if (isError) {
    return (
      <div className="mx-auto max-w-2xl space-y-4">
        <p className="text-sm text-destructive">
          {error instanceof Error ? error.message : "Could not load account."}
        </p>
        <Button type="button" variant="outline" size="sm" onClick={() => void refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  const me = data!;
  const plan = (me.subscription_plan ?? "free").toLowerCase();
  const wsMax = maxWorkspacesForPlan(plan);

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Account
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Your profile, plan, and where to upgrade.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Profile</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Email
            </p>
            <p className="mt-0.5 font-medium text-foreground">{me.email}</p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Name
            </p>
            <p className="mt-0.5 text-foreground">{me.name ?? "—"}</p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Plan & billing</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Current plan
            </p>
            <p className="mt-0.5 text-lg font-semibold text-foreground">
              {planLabel(me.subscription_plan)}
            </p>
            {me.subscription_renews_at ? (
              <p className="mt-1 text-xs text-muted-foreground">
                Renews or period ends:{" "}
                {new Date(me.subscription_renews_at).toLocaleString(undefined, {
                  dateStyle: "medium",
                  timeStyle: "short",
                })}
              </p>
            ) : (
              <p className="mt-1 text-xs text-muted-foreground">
                Renewal date appears here when you have an active paid subscription
                (via Razorpay webhooks).
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-2 pt-1">
            <Link
              href="/pricing"
              className={cn(buttonVariants({ variant: "default", size: "sm" }))}
            >
              View plans & upgrade
            </Link>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed border-t border-border/60 pt-3">
            Manage payment method or cancel in the Razorpay customer flow linked from
            your subscription email, or from the hosted page after checkout—hosted
            &quot;manage subscription&quot; links can be added here later.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Workspaces</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p className="text-muted-foreground">
            Your plan allows up to <strong className="text-foreground">{wsMax}</strong>{" "}
            workspace{wsMax === 1 ? "" : "s"}. Switch or create workspaces from the
            sidebar.
          </p>
          <ul className="list-none space-y-2 m-0 p-0">
            {me.workspaces.map((w) => (
              <li
                key={w.id}
                className="rounded-lg border border-border/70 bg-muted/20 px-3 py-2 flex justify-between gap-2"
              >
                <span className="font-medium truncate">{w.name}</span>
                <span className="text-xs text-muted-foreground shrink-0">
                  {w.id === me.active_workspace_id ? "Active" : ""}
                </span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
