"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { AuthGuard } from "@/components/auth-guard";
import { WorkspaceQueryInvalidator } from "@/components/workspace-query-invalidator";
import { WorkspaceSwitchOverlay } from "@/components/workspace-switch-overlay";
import { WorkspaceSwitcher } from "@/components/workspace-switcher";
import { UserMenu } from "@/components/user-menu";
import { cn } from "@/lib/utils";
import { BrandLogo } from "@/components/brand-logo";
import { DashboardSidebarContact } from "@/components/marketing/contact-section";

const navItems = [
  { href: "/dashboard", label: "Overview", icon: "◈" },
  { href: "/history", label: "History", icon: "⏱" },
  { href: "/upload", label: "Import", icon: "↑" },
  { href: "/integrations", label: "Integrations", icon: "⇄" },
  { href: "/datasets", label: "Sources", icon: "◫" },
  { href: "/help", label: "Help", icon: "?" },
  { href: "/pricing", label: "Plans", icon: "◇" },
  { href: "/account", label: "Account", icon: "◎" },
];

function isNavItemActive(href: string, pathname: string): boolean {
  const exactOnly = [
    "/dashboard",
    "/help",
    "/pricing",
    "/account",
    "/integrations",
  ];
  if (exactOnly.includes(href)) return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    if (!navOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setNavOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navOpen]);

  const sidebar = (
    <>
      <BrandLogo
        href="/dashboard"
        className="mb-4 px-3 py-2"
        nameClassName="text-lg font-semibold tracking-tight"
      />

      <div className="mb-4">
        <WorkspaceSwitcher />
      </div>

      <nav className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
        {navItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            aria-current={
              isNavItemActive(item.href, pathname) ? "page" : undefined
            }
            // A drawer left open would cover the page the user just picked.
            onClick={() => setNavOpen(false)}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              isNavItemActive(item.href, pathname)
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
            )}
          >
            <span className="text-base opacity-80">{item.icon}</span>
            {item.label}
          </Link>
        ))}
      </nav>

      <DashboardSidebarContact />

      <div className="shrink-0 border-t pt-3">
        <UserMenu />
      </div>
    </>
  );

  return (
    <AuthGuard>
      <WorkspaceQueryInvalidator />
      <div className="flex h-screen overflow-hidden">
        <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-r bg-card p-4 md:flex">
          {sidebar}
        </aside>

        {navOpen && (
          <div className="fixed inset-0 z-50 md:hidden">
            <button
              type="button"
              aria-label="Close navigation"
              className="absolute inset-0 bg-black/50"
              onClick={() => setNavOpen(false)}
            />
            <aside className="relative flex h-full w-64 max-w-[85vw] flex-col border-r bg-card p-4 shadow-xl">
              {sidebar}
            </aside>
          </div>
        )}

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex shrink-0 items-center gap-3 border-b bg-card px-4 py-3 md:hidden">
            <button
              type="button"
              onClick={() => setNavOpen(true)}
              aria-label="Open navigation"
              aria-expanded={navOpen}
              className="inline-flex h-9 w-9 items-center justify-center rounded-md border text-lg leading-none transition-colors hover:bg-accent"
            >
              ☰
            </button>
            <BrandLogo
              href="/dashboard"
              nameClassName="text-base font-semibold tracking-tight"
            />
          </header>

          <main
            id="dashboard-main"
            className="relative flex-1 overflow-auto bg-background p-4 md:p-6"
          >
            <WorkspaceSwitchOverlay />
            {children}
          </main>
        </div>
      </div>
    </AuthGuard>
  );
}
