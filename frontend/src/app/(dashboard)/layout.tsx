"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AuthGuard } from "@/components/auth-guard";
import { WorkspaceQueryInvalidator } from "@/components/workspace-query-invalidator";
import { WorkspaceSwitcher } from "@/components/workspace-switcher";
import { UserMenu } from "@/components/user-menu";
import { cn } from "@/lib/utils";
import { PRODUCT_NAME } from "@/lib/brand";

const navItems = [
  { href: "/dashboard", label: "Overview", icon: "◈" },
  { href: "/history", label: "History", icon: "⏱" },
  { href: "/upload", label: "Import", icon: "↑" },
  { href: "/datasets", label: "Sources", icon: "◫" },
  { href: "/pricing", label: "Plans", icon: "◇" },
  { href: "/account", label: "Account", icon: "◎" },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  return (
    <AuthGuard>
      <WorkspaceQueryInvalidator />
      <div className="dashboard-canvas flex h-screen overflow-hidden">
        <aside
          className="sticky top-0 flex h-screen w-[17rem] shrink-0 flex-col border-r border-slate-200/80 bg-white p-5 shadow-[4px_0_24px_-12px_rgba(15,23,42,0.06)] dark:border-white/10 dark:bg-[oklch(0.16_0.012_72)] dark:shadow-[10px_0_44px_-28px_rgba(0,0,0,0.48)]"
        >
          <div className="mb-5 rounded-[1.75rem] border border-white/70 bg-white/72 px-4 py-4 shadow-[0_18px_38px_-28px_rgba(15,23,42,0.18)] dark:border-white/10 dark:bg-white/[0.04] dark:shadow-none">
            <Link
              href="/dashboard"
              className="block text-lg font-bold tracking-tight text-foreground"
            >
              {PRODUCT_NAME}
            </Link>
            <p className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
              Dashboards, sources, briefings, and chat in one workspace.
            </p>
          </div>

          <div className="mb-5">
            <WorkspaceSwitcher />
          </div>

          <nav className="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto">
            {navItems.map((item) => {
              const active =
                item.href === "/dashboard"
                  ? pathname === "/dashboard"
                  : item.href === "/history"
                    ? pathname === "/history" || pathname.startsWith("/history/")
                    : item.href === "/pricing"
                      ? pathname === "/pricing"
                      : item.href === "/account"
                        ? pathname === "/account"
                        : pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-[1.1rem] px-3.5 py-3 text-sm font-semibold transition-all",
                    active
                      ? "bg-white text-foreground shadow-[0_18px_34px_-24px_rgba(15,23,42,0.3)] ring-1 ring-white/70 dark:bg-[rgba(44,57,91,0.9)] dark:text-white dark:ring-white/10 dark:shadow-[0_18px_36px_-24px_rgba(0,0,0,0.55)]"
                      : "text-slate-600 hover:bg-white/65 hover:text-foreground dark:text-slate-300 dark:hover:bg-white/[0.05] dark:hover:text-white"
                  )}
                >
                  <span className="flex h-8 w-8 items-center justify-center rounded-full bg-black/[0.035] text-base opacity-80 dark:bg-white/[0.06]">
                    {item.icon}
                  </span>
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="shrink-0 border-t border-white/60 pt-4 dark:border-white/10">
            <UserMenu />
          </div>
        </aside>
        <main
          id="dashboard-main"
          className="flex-1 overflow-auto px-5 py-5 md:px-7 md:py-7"
        >
          {children}
        </main>
      </div>
    </AuthGuard>
  );
}
