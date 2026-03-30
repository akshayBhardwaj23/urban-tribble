"use client";

import { useEffect, useState } from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useTheme } from "next-themes";
import { cn } from "@/lib/utils";

/** Nested “Theme” submenu for use inside an existing `DropdownMenu` (e.g. user menu). */
export function ThemeAppearanceSubmenu() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  return (
    <DropdownMenuSub>
      <DropdownMenuSubTrigger className="gap-2">
        <Sun className="opacity-70" aria-hidden />
        Theme
      </DropdownMenuSubTrigger>
      <DropdownMenuSubContent className="min-w-[10.5rem]">
        {mounted ? (
          <DropdownMenuRadioGroup
            value={theme ?? "system"}
            onValueChange={(v) => setTheme(v)}
          >
            <DropdownMenuRadioItem value="light" className="gap-2">
              <Sun className="opacity-70" aria-hidden />
              Light
            </DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="dark" className="gap-2">
              <Moon className="opacity-70" aria-hidden />
              Dark
            </DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="system" className="gap-2">
              <Monitor className="opacity-70" aria-hidden />
              System
            </DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
        ) : (
          <div className="px-2 py-2 text-xs text-muted-foreground">Theme…</div>
        )}
      </DropdownMenuSubContent>
    </DropdownMenuSub>
  );
}

/**
 * Standalone icon dropdown for marketing / auth pages (not inside another menu).
 * Reserves space before mount to avoid layout shift.
 */
export function ThemeMenuCompact({ className }: { className?: string }) {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        type="button"
        className={cn(
          "inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-border/80 bg-background text-foreground shadow-sm outline-none transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:ring-2 focus-visible:ring-ring",
          className
        )}
        aria-label="Theme: light, dark, or system"
      >
        {mounted ? (
          resolvedTheme === "dark" ? (
            <Moon className="h-4 w-4" aria-hidden />
          ) : (
            <Sun className="h-4 w-4" aria-hidden />
          )
        ) : (
          <span className="h-4 w-4 rounded-sm bg-muted" aria-hidden />
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[10.5rem]">
        {mounted ? (
          <DropdownMenuRadioGroup
            value={theme ?? "system"}
            onValueChange={(v) => setTheme(v)}
          >
            <DropdownMenuRadioItem value="light" className="gap-2">
              <Sun className="opacity-70" aria-hidden />
              Light
            </DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="dark" className="gap-2">
              <Moon className="opacity-70" aria-hidden />
              Dark
            </DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="system" className="gap-2">
              <Monitor className="opacity-70" aria-hidden />
              System
            </DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
        ) : (
          <div className="px-2 py-2 text-xs text-muted-foreground">Loading…</div>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
