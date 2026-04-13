"use client";

import { useState } from "react";
import Link from "next/link";
import { signIn, useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { api, setApiUserEmail } from "@/lib/api";
import { PRODUCT_NAME } from "@/lib/brand";
import { cn } from "@/lib/utils";

type PlanId = "free" | "starter" | "pro";

const CHECKOUT_SCRIPT_SRC = "https://checkout.razorpay.com/v1/checkout.js";

/** Razorpay may return api.razorpay.com links that fail in-browser; used only as fallback. */
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

function loadRazorpayCheckoutScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (typeof window === "undefined") {
      reject(new Error("No window"));
      return;
    }
    const w = window as unknown as { Razorpay?: unknown };
    if (w.Razorpay) {
      resolve();
      return;
    }
    const existing = document.querySelector<HTMLScriptElement>(
      `script[src="${CHECKOUT_SCRIPT_SRC}"]`
    );
    if (existing) {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener(
        "error",
        () => reject(new Error("Razorpay script failed")),
        { once: true }
      );
      return;
    }
    const s = document.createElement("script");
    s.src = CHECKOUT_SCRIPT_SRC;
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Could not load Razorpay Checkout"));
    document.body.appendChild(s);
  });
}

type RazorpayInstance = {
  open: () => void;
  on: (event: string, handler: (payload: { error?: { description?: string } }) => void) => void;
};

type RazorpayConstructor = new (options: Record<string, unknown>) => RazorpayInstance;

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
      const { short_url, subscription_id, key_id } = await api.razorpayCheckout(planId);

      try {
        await loadRazorpayCheckoutScript();
      } catch {
        window.location.href = normalizeRazorpayCheckoutUrl(short_url);
        return;
      }
      const Ctor = (window as unknown as { Razorpay?: RazorpayConstructor }).Razorpay;
      if (!Ctor || !key_id || !subscription_id) {
        window.location.href = normalizeRazorpayCheckoutUrl(short_url);
        return;
      }

      const description =
        planId === "pro"
          ? "Pro — monthly subscription (authorisation)"
          : "Starter — monthly subscription (authorisation)";

      const userEmail = session.user.email ?? undefined;
      const userName =
        typeof session.user.name === "string" && session.user.name.trim()
          ? session.user.name.trim()
          : undefined;

      type CheckoutSuccess = {
        razorpay_payment_id: string;
        razorpay_subscription_id: string;
        razorpay_signature: string;
      };

      const rzp = new Ctor({
        key: key_id,
        subscription_id,
        name: PRODUCT_NAME,
        description,
        prefill: {
          ...(userEmail ? { email: userEmail } : {}),
          ...(userName ? { name: userName } : {}),
        },
        handler(response: CheckoutSuccess) {
          void (async () => {
            const pid = response?.razorpay_payment_id;
            const sid = response?.razorpay_subscription_id;
            const sig = response?.razorpay_signature;
            if (!pid || !sid || !sig) {
              setErr("Missing payment confirmation from Razorpay.");
              return;
            }
            try {
              await api.razorpayVerifyCheckout({
                razorpay_payment_id: pid,
                razorpay_subscription_id: sid,
                razorpay_signature: sig,
              });
              window.location.href = "/dashboard?subscription=started";
            } catch (verifyErr) {
              setErr(
                verifyErr instanceof Error
                  ? verifyErr.message
                  : "Payment could not be verified. Your plan will update when webhooks arrive, or try again."
              );
            }
          })();
        },
        modal: {
          ondismiss() {
            setBusy(false);
          },
        },
      });

      rzp.on("payment.failed", (payload) => {
        const msg =
          payload?.error?.description ??
          "Payment could not be completed. You can try again or contact support.";
        setErr(msg);
        setBusy(false);
      });

      rzp.open();
      // Modal is open; re-enable the button so the label is not stuck on "Opening checkout…"
      setBusy(false);
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
        {busy ? "Opening checkout…" : cta}
      </Button>
      {err ? (
        <p className="text-center text-xs text-destructive leading-snug px-1">{err}</p>
      ) : null}
    </div>
  );
}
