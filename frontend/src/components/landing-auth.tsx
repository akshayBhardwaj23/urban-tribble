"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { signOut, useSession } from "next-auth/react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ThemeAppearanceSubmenu } from "@/components/theme-menu";

export function LandingHeaderAuth() {
  const { data: session, status } = useSession();
  const router = useRouter();

  if (status === "loading") {
    return (
      <div className="flex items-center gap-2" aria-hidden>
        <div className="h-8 w-8 shrink-0 rounded-full bg-muted animate-pulse" />
        <div className="hidden h-4 w-28 rounded bg-muted animate-pulse sm:block" />
      </div>
    );
  }

  if (session?.user) {
    const name = session.user.name ?? "User";
    const email = session.user.email ?? "";
    const initials = name
      .split(" ")
      .map((w) => w[0])
      .join("")
      .toUpperCase()
      .slice(0, 2);

    return (
      <DropdownMenu>
        <DropdownMenuTrigger
          type="button"
          className="flex max-w-[min(100%,14rem)] items-center gap-2 rounded-lg py-1.5 pl-1.5 pr-2 outline-none transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring"
        >
          {session.user.image ? (
            <img
              src={session.user.image}
              alt=""
              className="h-8 w-8 shrink-0 rounded-full object-cover"
              referrerPolicy="no-referrer"
            />
          ) : (
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-medium text-primary-foreground">
              {initials}
            </span>
          )}
          <span className="min-w-0 truncate text-sm font-medium text-foreground">
            {name}
          </span>
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="shrink-0 text-muted-foreground"
            aria-hidden
          >
            <path d="m7 15 5 5 5-5" />
            <path d="m7 9 5-5 5 5" />
          </svg>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-52">
          <div className="px-2 py-2">
            <p className="text-sm font-medium truncate">{name}</p>
            {email ? (
              <p className="text-xs text-muted-foreground truncate">{email}</p>
            ) : null}
          </div>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => router.push("/dashboard")}>
            Dashboard
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <ThemeAppearanceSubmenu />
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onClick={() => signOut({ callbackUrl: "/" })}
            className="text-destructive focus:text-destructive"
          >
            Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    );
  }

  return (
    <>
      <Link
        href="/login"
        className="text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        Sign in
      </Link>
      <Link href="/login">
        <Button size="sm" className="font-semibold">
          Start free
        </Button>
      </Link>
    </>
  );
}

function useGuestAppHref(): { href: string; isAuthed: boolean } {
  const { data: session, status } = useSession();
  if (status === "loading") return { href: "/login", isAuthed: false };
  if (session?.user) return { href: "/dashboard", isAuthed: true };
  return { href: "/login", isAuthed: false };
}

export function LandingHeroPrimaryCta() {
  const { href, isAuthed } = useGuestAppHref();
  return (
    <Link href={href}>
      <Button size="lg" className="h-12 px-8 font-semibold">
        {isAuthed ? "Open dashboard" : "Get clarity on my numbers"}
      </Button>
    </Link>
  );
}

export function LandingFooterPrimaryCta() {
  const { href, isAuthed } = useGuestAppHref();
  return (
    <Link href={href}>
      <Button size="lg" className="h-12 px-8 font-semibold">
        {isAuthed ? "Open dashboard" : "Upload my first file"}
      </Button>
    </Link>
  );
}

export function LandingPricingCta({
  tierName,
  cta,
  highlighted,
}: {
  tierName: string;
  cta: string;
  highlighted: boolean;
}) {
  const { isAuthed } = useGuestAppHref();
  const enterprise = tierName === "Enterprise";
  const label = isAuthed && !enterprise ? "Open app" : cta;
  const to = isAuthed && !enterprise ? "/dashboard" : "/login";

  return (
    <Link href={to} className="mt-8 block">
      <Button
        className="w-full font-semibold"
        variant={highlighted ? "default" : "outline"}
      >
        {label}
      </Button>
    </Link>
  );
}
