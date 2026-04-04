"use client";

import { signIn, useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { LOGIN_HEADLINE, PRODUCT_NAME } from "@/lib/brand";
import { ThemeMenuCompact } from "@/components/theme-menu";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function LoginPage() {
  const { status } = useSession();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<"email" | "code">("email");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (status === "authenticated") {
      router.replace("/dashboard");
    }
  }, [status, router]);

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  async function sendCode(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/auth/otp/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
      });
      const text = await res.text();
      if (!res.ok) {
        try {
          const j = JSON.parse(text) as { detail?: string };
          setError(j.detail ?? "Could not send code.");
        } catch {
          setError("Could not send code.");
        }
        return;
      }
      setStep("code");
      setCode("");
    } finally {
      setBusy(false);
    }
  }

  async function verifyCode(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const res = await signIn("email-otp", {
        email: email.trim(),
        code: code.replace(/\D/g, "").slice(0, 6),
        redirect: false,
        callbackUrl: "/dashboard",
      });
      if (res?.error) {
        setError("Invalid or expired code. Try again or request a new one.");
        return;
      }
      router.replace("/dashboard");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-muted/30 px-4">
      <div className="absolute right-4 top-4 sm:right-6 sm:top-6">
        <ThemeMenuCompact />
      </div>
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-bold tracking-tight">{PRODUCT_NAME}</h1>
        <p className="mt-2 text-muted-foreground">{LOGIN_HEADLINE}</p>
      </div>

      <Card className="w-full max-w-sm">
        <CardContent className="flex flex-col gap-4 pt-6 pb-6">
          <p className="text-center text-sm text-muted-foreground">
            Sign in to open your workspaces
          </p>

          {step === "email" ? (
                <form onSubmit={sendCode} className="flex flex-col gap-3">
                  <Input
                    type="email"
                    name="email"
                    autoComplete="email"
                    placeholder="you@company.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    disabled={busy}
                    className="h-11"
                  />
                  {error ? (
                    <p className="text-center text-xs text-destructive">
                      {error}
                    </p>
                  ) : null}
                  <Button type="submit" className="h-11 w-full" disabled={busy}>
                    {busy ? "Sending…" : "Email me a code"}
                  </Button>
                </form>
              ) : (
                <form onSubmit={verifyCode} className="flex flex-col gap-3">
                  <p className="text-center text-xs text-muted-foreground">
                    Enter the 6-digit code sent to{" "}
                    <span className="font-medium text-foreground">
                      {email.trim()}
                    </span>
                  </p>
                  <Input
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    placeholder="000000"
                    maxLength={6}
                    value={code}
                    onChange={(e) =>
                      setCode(e.target.value.replace(/\D/g, "").slice(0, 6))
                    }
                    required
                    disabled={busy}
                    className="h-11 text-center font-mono text-lg tracking-[0.3em]"
                  />
                  {error ? (
                    <p className="text-center text-xs text-destructive">
                      {error}
                    </p>
                  ) : null}
                  <Button type="submit" className="h-11 w-full" disabled={busy}>
                    {busy ? "Checking…" : "Sign in"}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="text-muted-foreground"
                    disabled={busy}
                    onClick={() => {
                      setStep("email");
                      setError("");
                      setCode("");
                    }}
                  >
                    Use a different email
                  </Button>
                </form>
              )}

              <div className="relative py-2">
                <div className="absolute inset-0 flex items-center">
                  <span className="w-full border-t border-border" />
                </div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-card px-2 text-muted-foreground">
                    Or
                  </span>
                </div>
              </div>

          <Button
            className="h-11 w-full gap-2"
            variant="outline"
            type="button"
            onClick={() => signIn("google", { callbackUrl: "/dashboard" })}
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24">
              <path
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
                fill="#4285F4"
              />
              <path
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                fill="#34A853"
              />
              <path
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                fill="#FBBC05"
              />
              <path
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                fill="#EA4335"
              />
            </svg>
            Continue with Google
          </Button>
        </CardContent>
      </Card>

      <p className="mt-6 max-w-xs text-center text-xs text-muted-foreground">
        By signing in, you agree to our Terms of Service and Privacy Policy.
      </p>
    </div>
  );
}
