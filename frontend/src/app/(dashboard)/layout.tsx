"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AuthGuard } from "@/components/auth-guard";
import { WorkspaceQueryInvalidator } from "@/components/workspace-query-invalidator";
import { WorkspaceSwitchOverlay } from "@/components/workspace-switch-overlay";
import { WorkspaceSwitcher } from "@/components/workspace-switcher";
import { UserMenu } from "@/components/user-menu";
import { cn } from "@/lib/utils";
import { BrandLogo } from "@/components/brand-logo";

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
      <div className="flex h-screen overflow-hidden">
        <aside className="sticky top-0 flex h-screen w-56 shrink-0 flex-col border-r bg-card p-4">
          <BrandLogo
            href="/dashboard"
            className="mb-4 px-3 py-2"
            nameClassName="text-lg font-semibold tracking-tight"
          />

          <div className="mb-4">
            <WorkspaceSwitcher />
          </div>

          <nav className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
            {navItems.map((item) => {
              const active =
                item.href === "/dashboard"
                  ? pathname === "/dashboard"
                  : item.href === "/history"
                    ? pathname === "/history" ||
                      pathname.startsWith("/history/")
                    : item.href === "/pricing"
                      ? pathname === "/pricing"
                      : item.href === "/account"
                        ? pathname === "/account"
                        : pathname === item.href ||
                          pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    active
                      ? "bg-accent text-accent-foreground"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                  )}
                >
                  <span className="text-base opacity-80">{item.icon}</span>
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="shrink-0 border-t pt-3">
            <UserMenu />
          </div>
        </aside>
        <main
          id="dashboard-main"
          className="relative flex-1 overflow-auto bg-background p-6"
        >
          <WorkspaceSwitchOverlay />
          {children}
        </main>
      </div>
    </AuthGuard>
  );
}
