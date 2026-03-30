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
  { href: "/upload", label: "Import", icon: "↑" },
  { href: "/datasets", label: "Sources", icon: "◫" },
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
          className="sticky top-0 flex h-screen w-56 shrink-0 flex-col border-r border-border/80 bg-card/80 p-4 shadow-sm backdrop-blur-xl dark:border-border/60 dark:bg-card/90 dark:shadow-[4px_0_32px_-12px_rgba(0,0,0,0.35)]"
        >
          <Link
            href="/dashboard"
            className="mb-2 px-3 py-2 text-lg font-bold tracking-tight text-foreground"
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
                      ? "bg-background text-foreground shadow-md shadow-black/5 dark:bg-accent dark:text-accent-foreground dark:shadow-black/20"
                      : "text-muted-foreground hover:bg-accent/70 hover:text-foreground"
                  )}
                >
                  <span className="text-base opacity-80">{item.icon}</span>
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="shrink-0 border-t border-border/80 pt-3 dark:border-border/60">
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
