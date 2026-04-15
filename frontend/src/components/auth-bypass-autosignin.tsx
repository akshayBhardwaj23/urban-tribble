"use client";

import { signIn, useSession } from "next-auth/react";
import { useEffect, useRef } from "react";

/**
 * When NEXT_PUBLIC_AUTH_BYPASS=true and AUTH_BYPASS=true on the server,
 * signs in via the dev-bypass Credentials provider so no Google/OTP is needed.
 * The dev-bypass provider refuses to run when NODE_ENV is production—use
 * backend AUTH_TEST_LOGIN_* + login "test-login" for a production-safe test user.
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
