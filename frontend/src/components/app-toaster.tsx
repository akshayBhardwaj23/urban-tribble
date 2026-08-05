"use client";

import { useTheme } from "next-themes";
import { Toaster } from "sonner";
import { useMounted } from "@/lib/use-mounted";

export function AppToaster() {
  const { resolvedTheme } = useTheme();
  const mounted = useMounted();

  if (!mounted) return null;

  return (
    <Toaster
      richColors
      closeButton
      position="top-center"
      theme={resolvedTheme === "dark" ? "dark" : "light"}
    />
  );
}
