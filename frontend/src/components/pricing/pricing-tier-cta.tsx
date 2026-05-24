"use client";

import { useState } from "react";
import Link from "next/link";
import { signIn, useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import { api, setApiUserEmail } from "@/lib/api";
import { PRODUCT_NAME } from "@/lib/brand";
import {
  checkoutCallbackUrl,
  checkoutSuccessUrl,
  loadRazorpayCheckoutScript,
  normalizeRazorpayCheckoutUrl,
  useRazorpayHostedCheckout,
  type RazorpayCheckoutSuccess,
  type RazorpayConstructor,
} from "@/lib/razorpay-checkout";
import { cn } from "@/lib/utils";

type PlanId = "free" | "starter" | "pro";

async function completeCheckout(response: RazorpayCheckoutSuccess): Promise<void> {
  await api.razorpayVerifyCheckout(response);
  window.location.href = `${checkoutSuccessUrl()}?verified=1`;
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
              ? "h-12 text-base shadow-lg shadow-amber-500/20 dark:shadow-[0_12px_40px_-12px_oklch(0.5_0.08_74_/_0.45)]"
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

      if (useRazorpayHostedCheckout) {
        window.location.assign(normalizeRazorpayCheckoutUrl(short_url));
        return;
      }

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
          ? "Pro - monthly subscription (authorisation)"
          : "Starter - monthly subscription (authorisation)";

      const userEmail = session.user.email ?? undefined;
      const userName =
        typeof session.user.name === "string" && session.user.name.trim()
          ? session.user.name.trim()
          : undefined;

      const rzp = new Ctor({
        key: key_id,
        subscription_id,
        name: PRODUCT_NAME,
        description,
        callback_url: checkoutCallbackUrl(),
        redirect: true,
        prefill: {
          ...(userEmail ? { email: userEmail } : {}),
          ...(userName ? { name: userName } : {}),
        },
        handler(response: RazorpayCheckoutSuccess) {
          void (async () => {
            const pid = response?.razorpay_payment_id;
            const sid = response?.razorpay_subscription_id;
            const sig = response?.razorpay_signature;
            if (!pid || !sid || !sig) {
              setErr("Missing payment confirmation from Razorpay.");
              return;
            }
            try {
              await completeCheckout({
                razorpay_payment_id: pid,
                razorpay_subscription_id: sid,
                razorpay_signature: sig,
              });
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
            ? "h-12 text-base shadow-lg shadow-amber-500/20 dark:shadow-[0_12px_40px_-12px_oklch(0.5_0.08_74_/_0.45)]"
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
