/** Shared Razorpay Standard Checkout helpers for /pricing. */

export const CHECKOUT_SCRIPT_SRC = "https://checkout.razorpay.com/v1/checkout.js";

/** Hosted short_url only when modal is blocked (ad blockers, CSP). */
export const useRazorpayHostedCheckout =
  process.env.NEXT_PUBLIC_RAZORPAY_HOSTED_CHECKOUT === "true";

export type RazorpayCheckoutSuccess = {
  razorpay_payment_id: string;
  razorpay_subscription_id: string;
  razorpay_signature: string;
};

export function checkoutSuccessPath(): string {
  return "/pricing/success";
}

export function checkoutSuccessUrl(): string {
  if (typeof window !== "undefined") {
    return `${window.location.origin}${checkoutSuccessPath()}`;
  }
  return checkoutSuccessPath();
}

/** Razorpay may return api.razorpay.com links that fail in-browser. */
export function normalizeRazorpayCheckoutUrl(url: string): string {
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

export function loadRazorpayCheckoutScript(): Promise<void> {
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

export type RazorpayInstance = {
  open: () => void;
  on: (event: string, handler: (payload: { error?: { description?: string } }) => void) => void;
};

export type RazorpayConstructor = new (options: Record<string, unknown>) => RazorpayInstance;
