import { NextRequest, NextResponse } from "next/server";

import { RAZORPAY_HANDOFF_COOKIE } from "../callback/route";

/**
 * Hand the checkout result to the success page once, then clear it.
 *
 * The cookie is httpOnly and bound to the browser that completed checkout, and
 * the backend independently re-verifies the HMAC signature and that the
 * subscription belongs to the caller, so reading it here grants nothing extra.
 */
export async function GET(request: NextRequest) {
  const raw = request.cookies.get(RAZORPAY_HANDOFF_COOKIE)?.value;

  const clear = (body: unknown, status = 200) => {
    const response = NextResponse.json(body, { status });
    response.cookies.set({
      name: RAZORPAY_HANDOFF_COOKIE,
      value: "",
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: 0,
    });
    return response;
  };

  if (!raw) {
    return NextResponse.json({ params: null });
  }

  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const payment = parsed.razorpay_payment_id;
    const subscription = parsed.razorpay_subscription_id;
    const signature = parsed.razorpay_signature;
    if (
      typeof payment !== "string" ||
      typeof subscription !== "string" ||
      typeof signature !== "string"
    ) {
      return clear({ params: null });
    }
    return clear({
      params: {
        razorpay_payment_id: payment,
        razorpay_subscription_id: subscription,
        razorpay_signature: signature,
      },
    });
  } catch {
    return clear({ params: null });
  }
}
