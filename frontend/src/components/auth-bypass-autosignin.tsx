"use client";

import { signIn, useSession } from "next-auth/react";
import { useEffect, useRef } from "react";

/**
 * When NEXT_PUBLIC_AUTH_BYPASS=true and AUTH_BYPASS=true on the server,
 * signs in via the dev-bypass Credentials provider so no Google/OTP is needed.
 * Never enable AUTH_BYPASS in production.
 */
export function AuthBypassAutoSignIn() {
  const { status } = useSession();
  const tried = useRef(false);

  useEffect(() => {
    if (process.env.NEXT_PUBLIC_AUTH_BYPASS !== "true") return;
    if (status !== "unauthenticated") return;
    if (tried.current) return;
    tried.current = true;
    void signIn("dev-bypass", { redirect: false });
  }, [status]);

  return null;
}
