"use client";

import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { CONTACT_EMAIL, contactMailto } from "@/lib/brand";
import { cn } from "@/lib/utils";

type ContactSectionProps = {
  id?: string;
  className?: string;
  /** Tighter layout for pricing footer area */
  variant?: "default" | "compact";
};

export function ContactSection({
  id = "contact",
  className,
  variant = "default",
}: ContactSectionProps) {
  const mailHref = contactMailto("Snaptix - question");
  const isCompact = variant === "compact";

  return (
    <section
      id={id}
      className={cn(
        "scroll-mt-24",
        isCompact ? "py-10" : "mx-auto max-w-6xl px-6 py-16 md:py-20",
        className
      )}
    >
      <div
        className={cn(
          "rounded-[28px] border border-slate-200/90 bg-white/80 px-6 py-8 shadow-sm dark:border-white/10 dark:bg-card/60 md:px-10 md:py-10",
          !isCompact &&
            "bg-gradient-to-br from-[#f8fafc] via-white to-[#f3f0ff] dark:from-card/80 dark:via-card/60 dark:to-card/40"
        )}
      >
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
          Talk to us
        </p>
        <h2
          className={cn(
            "mt-3 font-semibold tracking-tight text-slate-900 dark:text-white",
            isCompact ? "text-xl" : "text-2xl md:text-3xl"
          )}
        >
          Email the team
        </h2>
        <p
          className={cn(
            "mt-3 max-w-2xl leading-relaxed text-slate-600 dark:text-slate-300",
            isCompact ? "text-sm" : "text-[15px]"
          )}
        >
          Not sure Snaptix fits your spreadsheets, or rolling out to a team? Tell us
          what you use today and we will help you decide next steps. Write to{" "}
          <a
            href={mailHref}
            className="font-medium text-slate-900 underline underline-offset-2 dark:text-white"
          >
            {CONTACT_EMAIL}
          </a>
          .
        </p>

        <div className="mt-6 flex flex-wrap items-center gap-3">
          <a
            href={mailHref}
            className={buttonVariants({
              size: isCompact ? "default" : "lg",
              className: "font-semibold",
            })}
          >
            Email {CONTACT_EMAIL}
          </a>
        </div>

        <p className="mt-4 text-xs text-muted-foreground">
          We reply from {CONTACT_EMAIL} - usually within one business day.
        </p>
      </div>
    </section>
  );
}

/** Compact help line in the authenticated app sidebar */
export function DashboardSidebarContact() {
  const mailHref = contactMailto("Snaptix - help");
  return (
    <div className="mb-3 rounded-md border border-border/80 bg-muted/30 px-3 py-2.5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
        Need help?
      </p>
      <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
        <Link
          href="/help"
          className="font-medium text-foreground underline underline-offset-2"
        >
          Demo & help
        </Link>
        {" · "}
        <a
          href={mailHref}
          className="font-medium text-foreground underline underline-offset-2 break-all"
        >
          {CONTACT_EMAIL}
        </a>
      </p>
    </div>
  );
}

/** Inline footer link row */
export function ContactFooterLinks({ className }: { className?: string }) {
  return (
    <div className={cn("flex flex-wrap items-center gap-x-5 gap-y-2", className)}>
      <Link href="/help" className="hover:text-slate-900 dark:hover:text-white">
        Help & demo
      </Link>
      <Link
        href="/#contact"
        className="hover:text-slate-900 dark:hover:text-white"
      >
        Contact
      </Link>
      <a
        href={contactMailto()}
        className="hover:text-slate-900 dark:hover:text-white"
      >
        {CONTACT_EMAIL}
      </a>
    </div>
  );
}
