"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SessionProvider } from "next-auth/react";
import { ThemeProvider } from "next-themes";
import { useState } from "react";
import { AuthBypassAutoSignIn } from "@/components/auth-bypass-autosignin";
import { WorkspaceProvider } from "./workspace-context";

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
      <ThemeProvider
        attribute="class"
        defaultTheme="system"
        enableSystem
        storageKey="clarus-theme"
        disableTransitionOnChange
      >
        <QueryClientProvider client={queryClient}>
          <WorkspaceProvider>{children}</WorkspaceProvider>
        </QueryClientProvider>
      </ThemeProvider>
    </SessionProvider>
  );
}
