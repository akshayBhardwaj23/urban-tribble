"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { api, setApiUserEmail } from "@/lib/api";
import { PRODUCT_NAME } from "@/lib/brand";
import { useWorkspace } from "@/lib/workspace-context";
import type { RazorpayCheckoutSuccess } from "@/lib/razorpay-checkout";

function readCheckoutParams(
  searchParams: URLSearchParams
): RazorpayCheckoutSuccess | null {
  const razorpay_payment_id = searchParams.get("razorpay_payment_id");
  const razorpay_subscription_id = searchParams.get("razorpay_subscription_id");
  const razorpay_signature = searchParams.get("razorpay_signature");
  if (!razorpay_payment_id || !razorpay_subscription_id || !razorpay_signature) {
    return null;
  }
  return {
    razorpay_payment_id,
    razorpay_subscription_id,
    razorpay_signature,
  };
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

    const email = session?.user?.email;
    if (!email) return;

    let cancelled = false;

    const run = async () => {
      setApiUserEmail(email);
      const params = readCheckoutParams(searchParams);

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
  }, [status, session?.user?.email, searchParams, router, syncUser]);

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
