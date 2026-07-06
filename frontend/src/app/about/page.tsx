import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { DM_Serif_Display } from "next/font/google";
import { BrandLogo } from "@/components/brand-logo";
import { ContactFooterLinks } from "@/components/marketing/contact-section";
import { LandingHeaderAuth } from "@/components/landing-auth";
import { ThemeMenuCompact } from "@/components/theme-menu";
import {
  CANONICAL_SITE_URL,
  POSITIONING_LINE,
  PRODUCT_NAME,
  PRODUCT_TAGLINE,
} from "@/lib/brand";
import { cn } from "@/lib/utils";

const serif = DM_Serif_Display({ subsets: ["latin"], weight: "400" });

export const metadata: Metadata = {
  title: "About us",
  description: `Meet the founders behind ${PRODUCT_NAME} — building the AI decision layer for spreadsheet-first businesses.`,
  alternates: {
    canonical: "/about",
  },
  openGraph: {
    title: `About us - ${PRODUCT_NAME}`,
    description: `Meet the founders building ${PRODUCT_NAME}, the AI business analyst for modern operators.`,
    url: `${CANONICAL_SITE_URL}/about`,
  },
};

const FOUNDERS = [
  {
    name: "Rishav Bhardwaj",
    role: "Co-Founder",
    image: "/founders/rishav-bhardwaj.png",
    bio: "Driving product vision and go-to-market at Snaptix — turning spreadsheet chaos into a category-defining decision platform for operators worldwide.",
  },
  {
    name: "Akshay Bhardwaj",
    role: "Co-Founder",
    image: "/founders/akshay-bhardwaj.png",
    bio: "Architecting the intelligence layer behind Snaptix — from data ingestion and AI pipelines to the systems that deliver grounded, executive-grade insight at scale.",
  },
  {
    name: "Mayank Tyagi",
    role: "Co-Founder",
    image: "/founders/mayank-tyagi.png",
    bio: "Shaping customer experience and growth at Snaptix — ensuring every upload becomes clarity, every briefing becomes action, and every team moves faster with confidence.",
  },
] as const;

const PILLARS = [
  {
    title: "Decision velocity",
    body: "We compress weeks of reporting into minutes of clarity — so leaders act while the signal is still fresh.",
  },
  {
    title: "Grounded intelligence",
    body: "Our AI runs on your real numbers, not generic narratives — every insight is built to be verified and acted upon.",
  },
  {
    title: "Compounding context",
    body: "Each upload strengthens the workspace — what changed, what matters, and what to do next stays in one place.",
  },
] as const;

function FounderCard({
  founder,
  index,
}: {
  founder: (typeof FOUNDERS)[number];
  index: number;
}) {
  return (
    <article
      className="fade-up group relative flex flex-col"
      style={{ animationDelay: `${index * 100}ms` }}
    >
      <div className="relative overflow-hidden rounded-[28px] border border-slate-200/90 bg-white shadow-[0_24px_60px_-28px_rgba(15,23,42,0.35)] ring-1 ring-slate-900/[0.04] transition duration-500 group-hover:-translate-y-1 group-hover:shadow-[0_32px_70px_-24px_rgba(15,23,42,0.4)] dark:border-white/10 dark:bg-slate-900/60 dark:ring-white/[0.06]">
        <div className="relative aspect-[3/4] w-full overflow-hidden bg-gradient-to-b from-slate-100 to-slate-200 dark:from-slate-800 dark:to-slate-900">
          <Image
            src={founder.image}
            alt={`${founder.name}, ${founder.role} at ${PRODUCT_NAME}`}
            fill
            className="object-cover object-top transition duration-700 group-hover:scale-[1.03]"
            sizes="(max-width: 768px) 100vw, 33vw"
            priority={index === 0}
          />
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-slate-950/75 via-slate-950/10 to-transparent" />
          <div className="absolute bottom-0 left-0 right-0 p-6">
            <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-emerald-300/90">
              Co-Founder · {PRODUCT_NAME}
            </p>
            <h3
              className={cn(
                serif.className,
                "mt-2 text-2xl leading-tight text-white md:text-[1.65rem]",
              )}
            >
              {founder.name}
            </h3>
          </div>
        </div>
        <div className="border-t border-slate-100 px-6 py-5 dark:border-white/[0.08]">
          <p className="text-[14px] leading-7 text-slate-600 dark:text-slate-300">
            {founder.bio}
          </p>
        </div>
      </div>
    </article>
  );
}

export default function AboutPage() {
  return (
    <main className="min-h-screen bg-[#f6f4ef] text-slate-900 dark:bg-background dark:text-foreground">
      <div className="border-b border-slate-200/80 bg-white/70 backdrop-blur-md dark:border-white/10 dark:bg-card/55">
        <header className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-4 sm:px-6">
          <BrandLogo href="/" nameClassName="text-base font-semibold" />
          <div className="flex items-center gap-3">
            <ThemeMenuCompact />
            <LandingHeaderAuth />
          </div>
        </header>
      </div>

      {/* Hero */}
      <section className="relative overflow-hidden border-b border-slate-200/80 dark:border-white/10">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_80%_60%_at_50%_-10%,rgba(139,92,246,0.14),transparent_55%)] dark:bg-[radial-gradient(ellipse_80%_60%_at_50%_-10%,rgba(124,58,237,0.2),transparent_55%)]" />
        <div className="pointer-events-none absolute -right-24 top-20 h-72 w-72 rounded-full bg-emerald-200/30 blur-3xl dark:bg-emerald-500/10" />
        <div className="relative mx-auto max-w-4xl px-4 py-16 text-center sm:px-6 md:py-24">
          <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500 dark:text-slate-400">
            About Snaptix
          </p>
          <h1
            className={cn(
              serif.className,
              "fade-up mt-5 text-balance text-4xl leading-[1.05] text-slate-900 dark:text-white md:text-5xl lg:text-6xl",
            )}
          >
            The team building {PRODUCT_NAME}
          </h1>
          <p className="fade-up mx-auto mt-6 max-w-2xl text-[17px] leading-8 text-slate-600 dark:text-slate-300">
            <strong className="font-semibold text-slate-900 dark:text-white">{PRODUCT_NAME}</strong>{" "}
            is the AI business analyst for spreadsheet-first teams — {POSITIONING_LINE.toLowerCase()}.{" "}
            {PRODUCT_TAGLINE}
          </p>
        </div>
      </section>

      {/* Mission */}
      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 md:py-20">
        <div className="rounded-[32px] border border-slate-200/90 bg-white/90 px-8 py-10 shadow-sm dark:border-white/10 dark:bg-slate-900/50 md:px-14 md:py-14">
          <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-violet-600 dark:text-violet-400">
            Our mission
          </p>
          <p
            className={cn(
              serif.className,
              "mt-4 max-w-3xl text-2xl leading-snug text-slate-900 dark:text-white md:text-3xl",
            )}
          >
            We exist to eliminate the gap between having data and knowing what to do
            with it.
          </p>
          <p className="mt-5 max-w-3xl text-[15px] leading-7 text-slate-600 dark:text-slate-300">
            Most companies do not fail from lack of information — they fail from delayed
            clarity. {PRODUCT_NAME} transforms familiar spreadsheets into automated dashboards,
            executive briefings, and grounded answers so operators, finance teams, and
            founders can move with strategic velocity every single week.
          </p>
        </div>
      </section>

      {/* Founders */}
      <section className="border-y border-slate-200/80 bg-white/50 dark:border-white/10 dark:bg-slate-950/30">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 md:py-24">
          <div className="mx-auto max-w-2xl text-center">
            <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-slate-500 dark:text-slate-400">
              Leadership
            </p>
            <h2
              className={cn(
                serif.className,
                "mt-4 text-3xl text-slate-900 dark:text-white md:text-4xl",
              )}
            >
              Meet the founders of {PRODUCT_NAME}
            </h2>
            <p className="mt-4 text-[15px] leading-7 text-slate-600 dark:text-slate-300">
              Three builders behind {PRODUCT_NAME} — united by one conviction: the future
              of business intelligence is AI-native, spreadsheet-native, and built for the
              people who actually run the numbers.
            </p>
          </div>

          <div className="mt-14 grid gap-8 md:grid-cols-3 md:gap-6 lg:gap-8">
            {FOUNDERS.map((founder, index) => (
              <FounderCard key={founder.name} founder={founder} index={index} />
            ))}
          </div>
        </div>
      </section>

      {/* Pillars */}
      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 md:py-20">
        <div className="grid gap-6 md:grid-cols-3">
          {PILLARS.map((pillar, i) => (
            <div
              key={pillar.title}
              className="fade-up rounded-2xl border border-slate-200/90 bg-white/80 p-7 dark:border-white/10 dark:bg-slate-900/40"
              style={{ animationDelay: `${i * 80}ms` }}
            >
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-emerald-600 dark:text-emerald-400">
                0{i + 1}
              </p>
              <h3 className="mt-3 text-lg font-semibold text-slate-900 dark:text-white">
                {pillar.title}
              </h3>
              <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                {pillar.body}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="border-t border-slate-200/80 bg-gradient-to-b from-transparent to-white/80 dark:border-white/10 dark:to-slate-950/50">
        <div className="mx-auto max-w-3xl px-4 py-16 text-center sm:px-6 md:py-20">
          <h2
            className={cn(
              serif.className,
              "text-3xl text-slate-900 dark:text-white md:text-4xl",
            )}
          >
            Join the {PRODUCT_NAME} journey
          </h2>
          <p className="mt-4 text-[15px] leading-7 text-slate-600 dark:text-slate-300">
            We are just getting started — building {PRODUCT_NAME} for teams who believe
            better decisions should not wait for better tools.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
            <Link
              href="/login"
              className="inline-flex h-11 items-center rounded-full bg-emerald-500 px-8 text-sm font-semibold text-white shadow-md transition hover:bg-emerald-600"
            >
              Get started free
            </Link>
            <Link
              href="/pricing"
              className="inline-flex h-11 items-center rounded-full border border-slate-300 bg-white px-8 text-sm font-semibold text-slate-800 transition hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800"
            >
              View plans
            </Link>
          </div>
        </div>
      </section>

      <footer className="border-t border-slate-200/80 py-10 dark:border-slate-700">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-4 text-sm text-slate-600 dark:text-slate-300 sm:flex-row sm:px-6">
          <Link href="/" className="font-semibold text-slate-900 dark:text-white">
            {PRODUCT_NAME}
          </Link>
          <div className="flex flex-wrap items-center justify-center gap-5">
            <ContactFooterLinks />
            <Link href="/privacy" className="hover:text-slate-900 dark:hover:text-white">
              Privacy
            </Link>
            <Link href="/terms" className="hover:text-slate-900 dark:hover:text-white">
              Terms
            </Link>
          </div>
        </div>
      </footer>
    </main>
  );
}
