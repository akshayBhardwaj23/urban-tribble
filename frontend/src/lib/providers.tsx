"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SessionProvider } from "next-auth/react";
import { usePathname } from "next/navigation";
import { ThemeProvider } from "next-themes";
import { useState } from "react";
import { AuthBypassAutoSignIn } from "@/components/auth-bypass-autosignin";
import { AppToaster } from "@/components/app-toaster";
import { WorkspaceProvider } from "./workspace-context";

/** Marketing home is always light; elsewhere respects clarus-theme + system. */
function AppThemeProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const forceLight = pathname === "/";

  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      storageKey="clarus-theme"
      disableTransitionOnChange
      forcedTheme={forceLight ? "light" : undefined}
    >
      {children}
    </ThemeProvider>
  );
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30 * 1000,
            retry: 1,
          },
        },
      })
  );

  return (
    <SessionProvider>
      <AuthBypassAutoSignIn />
      <AppThemeProvider>
        <QueryClientProvider client={queryClient}>
          <WorkspaceProvider>
            {children}
            <AppToaster />
          </WorkspaceProvider>
        </QueryClientProvider>
      </AppThemeProvider>
    </SessionProvider>
  );
}
