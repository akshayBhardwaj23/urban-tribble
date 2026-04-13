"use client";

import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { PlanLimitDetail } from "@/lib/api";

export function PlanLimitCallout({
  detail,
  className,
  compact,
}: {
  detail: PlanLimitDetail;
  className?: string;
  /** Tighter layout for inline file rows */
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border border-destructive/25 bg-destructive/5 px-3 py-2.5",
        compact ? "text-xs" : "px-4 py-3 text-sm",
        className
      )}
    >
      <p className={cn("text-foreground/90 leading-snug", compact && "text-[13px]")}>
        {detail.message}
      </p>
      <Link
        href="/pricing"
        className={cn(
          buttonVariants({ variant: "default", size: compact ? "sm" : "sm" }),
          "mt-2 inline-flex w-fit font-medium"
        )}
      >
        View plans & upgrade
      </Link>
    </div>
  );
}
