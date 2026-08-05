"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { api, setApiAccessToken } from "@/lib/api";
import { PRODUCT_NAME } from "@/lib/brand";
import { useWorkspace } from "@/lib/workspace-context";
import type { RazorpayCheckoutSuccess } from "@/lib/razorpay-checkout";

/**
 * Collect the checkout result from the server-side handoff cookie.
 *
 * The ids are deliberately absent from the URL, so there is nothing sensitive
 * in browser history or in a Referer header sent to a third party.
 */
async function readCheckoutParams(): Promise<RazorpayCheckoutSuccess | null> {
  try {
    const res = await fetch("/api/billing/razorpay/handoff", {
      cache: "no-store",
    });
    if (!res.ok) return null;
    const body = (await res.json()) as { params: RazorpayCheckoutSuccess | null };
    return body.params ?? null;
  } catch {
    return null;
  }
}

function PricingSuccessContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: session, status } = useSession();
  const { syncUser } = useWorkspace();
  const [message, setMessage] = useState("Confirming your subscription…");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (status === "loading") return;

    if (status === "unauthenticated") {
      const returnTo = `/pricing/success?${searchParams.toString()}`;
      router.replace(`/login?callbackUrl=${encodeURIComponent(returnTo)}`);
      return;
    }

    const token = session?.accessToken;
    if (!token) return;

    let cancelled = false;

    const run = async () => {
      setApiAccessToken(token);
      const params =
        searchParams.get("pending") === "1" ? await readCheckoutParams() : null;

      if (params) {
        try {
          const result = await api.razorpayVerifyCheckout(params);
          if (!cancelled && result.subscription_plan) {
            setMessage(
              `Your ${result.subscription_plan === "pro" ? "Pro" : "Starter"} plan is active.`
            );
          }
        } catch (e) {
          if (!cancelled) {
            setMessage(
              "Payment received. Your plan should update shortly via our billing system."
            );
            setError(
              e instanceof Error
                ? e.message
                : "Could not verify payment signature."
            );
          }
        }
      } else if (searchParams.get("verified") !== "1") {
        setMessage("Thanks for subscribing. Checking your plan…");
      }

      await syncUser();

      if (!cancelled) {
        router.replace("/dashboard?subscription=started");
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [status, session?.accessToken, searchParams, router, syncUser]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-muted/30 px-4 text-center">
      <div className="max-w-md space-y-4">
        <h1 className="text-xl font-semibold tracking-tight">
          {error ? "Almost there" : `Welcome to ${PRODUCT_NAME}`}
        </h1>
        <p className="text-sm text-muted-foreground leading-relaxed">{message}</p>
        {error ? (
          <p className="text-xs text-destructive leading-relaxed">{error}</p>
        ) : null}
        <p className="text-xs text-muted-foreground">
          Redirecting to your dashboard…
        </p>
        <Link
          href="/dashboard"
          className={cn(buttonVariants({ variant: "outline", size: "sm" }))}
        >
          Go to dashboard now
        </Link>
      </div>
    </div>
  );
}

export default function PricingSuccessPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center">
          <p className="text-sm text-muted-foreground">Loading…</p>
        </div>
      }
    >
      <PricingSuccessContent />
    </Suspense>
  );
}
