import { NextRequest, NextResponse } from "next/server";

/** Razorpay Standard Checkout posts payment fields to `callback_url` (not GET). */
const CHECKOUT_PARAM_KEYS = [
  "razorpay_payment_id",
  "razorpay_subscription_id",
  "razorpay_signature",
] as const;

async function readRazorpayCallbackParams(
  request: NextRequest
): Promise<URLSearchParams> {
  const out = new URLSearchParams();
  const contentType = request.headers.get("content-type") ?? "";

  if (
    contentType.includes("application/x-www-form-urlencoded") ||
    contentType.includes("multipart/form-data")
  ) {
    const form = await request.formData();
    for (const key of CHECKOUT_PARAM_KEYS) {
      const value = form.get(key);
      if (typeof value === "string" && value.trim()) {
        out.set(key, value.trim());
      }
    }
    return out;
  }

  const raw = await request.text();
  if (!raw.trim()) {
    return out;
  }

  try {
    const json = JSON.parse(raw) as Record<string, unknown>;
    for (const key of CHECKOUT_PARAM_KEYS) {
      const value = json[key];
      if (typeof value === "string" && value.trim()) {
        out.set(key, value.trim());
      }
    }
    if ([...out.keys()].length > 0) {
      return out;
    }
  } catch {
    /* fall through to form parse */
  }

  const parsed = new URLSearchParams(raw);
  for (const key of CHECKOUT_PARAM_KEYS) {
    const value = parsed.get(key);
    if (value?.trim()) {
      out.set(key, value.trim());
    }
  }
  return out;
}

export async function POST(request: NextRequest) {
  const params = await readRazorpayCallbackParams(request);
  const redirectUrl = new URL(request.url);

  for (const [key, value] of params) {
    redirectUrl.searchParams.set(key, value);
  }

  if (!redirectUrl.searchParams.has("razorpay_payment_id")) {
    redirectUrl.searchParams.set("verified", "1");
  }

  return NextResponse.redirect(redirectUrl, 303);
}
