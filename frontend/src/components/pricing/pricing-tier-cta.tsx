"use client";

import { useState } from "react";
import Link from "next/link";
import { signIn, useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { api, setApiUserEmail } from "@/lib/api";
import { cn } from "@/lib/utils";

type PlanId = "free" | "starter" | "pro";

/** Razorpay may return api.razorpay.com links that fail in-browser; checkout host serves the UI. */
function normalizeRazorpayCheckoutUrl(url: string): string {
  try {
    const u = new URL(url);
    if (u.hostname === "api.razorpay.com" && u.pathname.includes("/subscriptions/")) {
      u.hostname = "checkout.razorpay.com";
      return u.toString();
    }
  } catch {
    /* ignore */
  }
  return url;
}

export function PricingTierCTA({
  planId,
  cta,
  featured,
}: {
  planId: PlanId;
  cta: string;
  featured: boolean;
}) {
  const { data: session, status } = useSession();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  if (planId === "free") {
    return (
      <Link href="/login" className="block">
        <Button
          className={cn(
            "min-h-12 w-full rounded-xl font-semibold",
            featured
              ? "h-12 text-base shadow-lg shadow-violet-600/25 dark:shadow-violet-900/40"
              : "h-12 text-[15px]",
          )}
          size="lg"
          variant={featured ? "default" : "outline"}
        >
          {cta}
        </Button>
      </Link>
    );
  }

  const runCheckout = async () => {
    setErr(null);
    if (status !== "authenticated" || !session?.user?.email) {
      void signIn(undefined, { callbackUrl: "/pricing" });
      return;
    }
    setBusy(true);
    try {
      setApiUserEmail(session.user.email);
      const { short_url } = await api.razorpayCheckout(planId);
      window.location.href = normalizeRazorpayCheckoutUrl(short_url);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Checkout failed");
      setBusy(false);
    }
  };

  return (
    <div className="w-full space-y-2">
      <Button
        type="button"
        className={cn(
          "min-h-12 w-full rounded-xl font-semibold",
          featured
            ? "h-12 text-base shadow-lg shadow-violet-600/25 dark:shadow-violet-900/40"
            : "h-12 text-[15px]",
        )}
        size="lg"
        variant={featured ? "default" : "outline"}
        disabled={busy || status === "loading"}
        onClick={() => void runCheckout()}
      >
        {busy ? "Redirecting…" : cta}
      </Button>
      {err ? (
        <p className="text-center text-xs text-destructive leading-snug px-1">{err}</p>
      ) : null}
    </div>
  );
}
