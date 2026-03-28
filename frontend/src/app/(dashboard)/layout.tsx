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
  { href: "/dashboard", label: "Business Health", icon: "◈" },
  { href: "/upload", label: "Import Data", icon: "↑" },
  { href: "/datasets", label: "Data Sources", icon: "◫" },
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
      <div className="flex h-screen overflow-hidden">
        <aside
          className="sticky top-0 flex h-screen w-56 shrink-0 flex-col border-r border-white/50 bg-white/65 p-4 shadow-[4px_0_32px_-12px_rgba(99,102,241,0.08)] backdrop-blur-xl"
        >
          <Link
            href="/dashboard"
            className="mb-2 px-3 py-2 text-lg font-bold tracking-tight text-slate-800"
          >
            {PRODUCT_NAME}
          </Link>

          <div className="mb-4">
            <WorkspaceSwitcher />
          </div>

          <nav className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
            {navItems.map((item) => {
              const active =
                item.href === "/dashboard"
                  ? pathname === "/dashboard"
                  : pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition-all",
                    active
                      ? "bg-white text-slate-900 shadow-md shadow-indigo-500/10"
                      : "text-slate-500 hover:bg-white/70 hover:text-slate-800"
                  )}
                >
                  <span className="text-base opacity-80">{item.icon}</span>
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="shrink-0 border-t border-slate-200/60 pt-3">
            <UserMenu />
          </div>
        </aside>
        <main className="dashboard-canvas flex-1 overflow-auto p-6 md:p-8">
          {children}
        </main>
      </div>
    </AuthGuard>
  );
}
