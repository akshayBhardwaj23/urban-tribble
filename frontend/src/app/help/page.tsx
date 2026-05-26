import type { Metadata } from "next";
import Link from "next/link";
import { BrandLogo } from "@/components/brand-logo";
import { ContactFooterLinks } from "@/components/marketing/contact-section";
import { HelpPageWithAuth } from "@/components/marketing/help-page-with-auth";
import { LandingHeaderAuth } from "@/components/landing-auth";
import { ThemeMenuCompact } from "@/components/theme-menu";
import { CANONICAL_SITE_URL, PRODUCT_NAME } from "@/lib/brand";

export const metadata: Metadata = {
  title: "Help & demo",
  description: `Watch the ${PRODUCT_NAME} demo and learn how to import data, run briefings, and get support.`,
  alternates: {
    canonical: "/help",
  },
  openGraph: {
    title: `Help & demo - ${PRODUCT_NAME}`,
    description: `Product walkthrough and getting started with ${PRODUCT_NAME}.`,
    url: `${CANONICAL_SITE_URL}/help`,
  },
};

export default function PublicHelpPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="border-b border-border/80 bg-card/60 backdrop-blur-sm">
        <header className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-4 sm:px-6">
          <BrandLogo href="/" nameClassName="text-base font-semibold" />
          <div className="flex items-center gap-3">
            <ThemeMenuCompact />
            <LandingHeaderAuth />
          </div>
        </header>
      </div>

      <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 md:py-14">
        <HelpPageWithAuth />
        <div className="mx-auto mt-12 flex max-w-3xl flex-wrap items-center justify-center gap-4 text-sm">
          <Link
            href="/dashboard"
            className="font-medium text-foreground underline underline-offset-2"
          >
            Back to dashboard
          </Link>
          <span className="text-muted-foreground" aria-hidden>
            ·
          </span>
          <Link
            href="/login"
            className="font-medium text-foreground underline underline-offset-2"
          >
            Sign in
          </Link>
        </div>
      </div>

      <footer className="border-t border-border/80 py-8">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-4 text-sm text-muted-foreground sm:flex-row sm:px-6">
          <Link href="/" className="font-semibold text-foreground">
            {PRODUCT_NAME}
          </Link>
          <ContactFooterLinks />
        </div>
      </footer>
    </main>
  );
}
