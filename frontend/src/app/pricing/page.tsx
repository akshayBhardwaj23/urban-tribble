import type { ReactNode } from "react";
import Link from "next/link";
import { DM_Serif_Display } from "next/font/google";
import { PricingTierCTA } from "@/components/pricing/pricing-tier-cta";
import { LandingHeaderAuth } from "@/components/landing-auth";
import { ThemeMenuCompact } from "@/components/theme-menu";
import { PRODUCT_NAME } from "@/lib/brand";
import {
  PRICING_FAQ,
  PRICING_PLANS,
  PRICING_ROI_LINE,
  PRICING_VALUE_HEADLINE,
  PRICING_VALUE_POINTS,
} from "@/lib/pricing-plans";
import { cn } from "@/lib/utils";

const serif = DM_Serif_Display({ subsets: ["latin"], weight: "400" });

function Tag({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex rounded-full border border-slate-300/80 bg-white/95 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.19em] text-slate-600 shadow-sm dark:border-white/15 dark:bg-card/80 dark:text-muted-foreground">
      {children}
    </span>
  );
}

export default function PricingPage() {
  return (
    <main className="min-h-screen bg-[#f6f4ef] text-slate-900 dark:bg-background dark:text-foreground">
      <div className="border-b border-slate-200/80 bg-white/70 backdrop-blur-sm dark:border-white/10 dark:bg-card/60">
        <header className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-4 sm:px-6">
          <Link
            href="/"
            className="min-w-0 shrink text-base font-semibold tracking-tight text-slate-900 dark:text-white"
          >
            {PRODUCT_NAME}
          </Link>
          <nav className="flex shrink-0 items-center gap-3 text-sm text-slate-600 dark:text-slate-300 sm:gap-5">
            <Link href="/" className="hidden hover:text-slate-900 dark:hover:text-white sm:inline">
              Home
            </Link>
            <span className="hidden font-medium text-slate-900 dark:text-white sm:inline">
              Pricing
            </span>
            <ThemeMenuCompact />
            <LandingHeaderAuth />
          </nav>
        </header>
      </div>

      {/* Hero */}
      <section className="mx-auto max-w-3xl px-4 pb-14 pt-12 text-center sm:px-6 md:pb-20 md:pt-16">
        <Tag>Pricing</Tag>
        <h1
          className={`${serif.className} mt-5 text-balance text-[2rem] leading-[1.12] tracking-tight text-slate-900 dark:text-white sm:text-4xl md:text-[2.65rem]`}
        >
          Run your business with clarity, not guesswork.
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-base leading-7 text-slate-600 dark:text-slate-300 sm:text-[17px] sm:leading-8">
          Snaptix turns your spreadsheets into ongoing business insights—so you know what changed,
          what matters, and what to do next.
        </p>
        <p className="mx-auto mt-6 max-w-xl text-sm leading-relaxed text-slate-500 dark:text-slate-400">
          Start free. Upgrade when you want continuous monitoring and deeper insights.
        </p>
      </section>

      {/* Cards — Pro visually dominant on lg+; stacked readable on small screens */}
      <section className="mx-auto max-w-7xl px-4 pb-20 sm:px-6 lg:pb-28">
        <div
          className={cn(
            "mx-auto grid max-w-[1180px] grid-cols-1 gap-8",
            "lg:grid-cols-3 lg:items-stretch lg:gap-5 xl:gap-8",
            "lg:pt-4",
          )}
        >
          {PRICING_PLANS.map((plan) => {
            const featured = plan.featured;
            return (
              <article
                key={plan.id}
                className={cn(
                  "relative flex min-h-0 flex-col rounded-3xl border",
                  featured
                    ? cn(
                        "z-10 border-violet-400/90 bg-linear-to-b from-white via-violet-50/90 to-white",
                        "shadow-[0_24px_60px_-20px_rgba(109,40,217,0.35)] ring-2 ring-violet-300/80",
                        "dark:border-violet-500/70 dark:from-slate-900 dark:via-violet-950/50 dark:to-slate-900",
                        "dark:shadow-[0_28px_70px_-24px_rgba(76,29,149,0.45)] dark:ring-violet-600/45",
                        "lg:-my-3 lg:scale-[1.045] lg:px-0 lg:py-1",
                        "p-8 sm:p-8 lg:p-10",
                      )
                    : cn(
                        "border-slate-200/95 bg-white/95 shadow-sm dark:border-slate-700 dark:bg-slate-900/85",
                        "p-7 sm:p-8",
                      ),
                )}
              >
                {plan.badge ? (
                  <span
                    className={cn(
                      "absolute left-1/2 top-0 -translate-x-1/2 -translate-y-1/2 whitespace-nowrap rounded-full px-4 py-1.5",
                      "text-[10px] font-bold uppercase tracking-[0.14em] text-white",
                      "bg-violet-600 shadow-md shadow-violet-600/30 dark:bg-violet-500",
                    )}
                  >
                    {plan.badge}
                  </span>
                ) : null}

                <div className={cn(featured && plan.badge ? "mt-4" : "")}>
                  <p
                    className={cn(
                      "font-semibold text-slate-900 dark:text-white",
                      featured ? "text-base sm:text-lg" : "text-sm",
                    )}
                  >
                    {plan.name}
                  </p>
                  <div
                    className={cn(
                      "mt-4 flex flex-wrap items-end gap-x-1.5 gap-y-1",
                      featured && "mt-5",
                    )}
                  >
                    <span
                      className={cn(
                        "font-semibold tracking-tight text-slate-900 dark:text-white",
                        featured ? "text-4xl sm:text-5xl" : "text-4xl",
                      )}
                    >
                      {plan.priceDisplay}
                    </span>
                    {plan.period ? (
                      <span
                        className={cn(
                          "text-slate-500 dark:text-slate-400",
                          featured ? "pb-1.5 text-sm sm:text-base" : "pb-1 text-sm",
                        )}
                      >
                        {plan.period}
                      </span>
                    ) : null}
                  </div>
                  <p
                    className={cn(
                      "leading-relaxed text-slate-600 dark:text-slate-300",
                      featured ? "mt-4 text-[15px] sm:text-base" : "mt-3 text-sm",
                    )}
                  >
                    {plan.subtitle}
                  </p>
                </div>

                <ul
                  className={cn(
                    "mt-8 flex-1 border-t pt-6 dark:border-slate-700/80",
                    featured
                      ? "border-violet-200/70 dark:border-violet-800/60"
                      : "border-slate-100 dark:border-slate-700/80",
                  )}
                  role="list"
                >
                  {plan.features.map((f) => (
                    <li
                      key={f}
                      className={cn(
                        "grid grid-cols-[1.125rem_minmax(0,1fr)] gap-x-3 border-b border-slate-100 py-3 last:border-b-0 dark:border-slate-700/55",
                        featured && "dark:border-violet-950/40",
                      )}
                    >
                      <span
                        className={cn(
                          "pt-0.5 text-center text-sm font-semibold leading-snug text-violet-600 dark:text-violet-400",
                          featured && "text-base",
                        )}
                        aria-hidden
                      >
                        ✓
                      </span>
                      <span
                        className={cn(
                          "text-[15px] leading-snug text-slate-700 dark:text-slate-200",
                          featured && "sm:text-[15px]",
                        )}
                      >
                        {f}
                      </span>
                    </li>
                  ))}
                </ul>

                {plan.limitations?.length ? (
                  <ul
                    className="mt-6 space-y-2 border-t border-slate-200/80 pt-6 dark:border-slate-700"
                    role="list"
                  >
                    {plan.limitations.map((line) => (
                      <li
                        key={line}
                        className="pl-1 text-xs leading-relaxed text-slate-500 dark:text-slate-500"
                      >
                        {line}
                      </li>
                    ))}
                  </ul>
                ) : null}

                {plan.valueLine ? (
                  <p
                    className={cn(
                      "mt-6 border-t pt-6 text-sm font-medium leading-relaxed text-slate-800 dark:border-slate-700 dark:text-slate-200",
                      featured &&
                        "border-violet-200/60 text-slate-900 dark:border-violet-900/50 dark:text-white",
                    )}
                  >
                    {plan.valueLine}
                  </p>
                ) : null}

                <div className={cn("mt-8", featured && "mt-10")}>
                  <PricingTierCTA
                    planId={plan.id}
                    cta={plan.cta}
                    featured={featured}
                  />
                </div>
              </article>
            );
          })}
        </div>
      </section>

      {/* Value */}
      <section className="border-t border-slate-200/80 bg-white/50 py-16 dark:border-slate-700 dark:bg-slate-900/25 sm:py-20 md:py-24">
        <div className="mx-auto max-w-3xl px-4 text-center sm:px-6">
          <h2
            className={`${serif.className} text-balance text-3xl tracking-tight text-slate-900 dark:text-white md:text-4xl`}
          >
            {PRICING_VALUE_HEADLINE}
          </h2>
          <ul className="mx-auto mt-12 max-w-xl space-y-5 text-left text-[15px] leading-7 text-slate-600 dark:text-slate-300 sm:mt-14">
            {PRICING_VALUE_POINTS.map((point) => (
              <li key={point} className="flex gap-3.5">
                <span
                  className="mt-2 h-2 w-2 shrink-0 rounded-full bg-violet-500"
                  aria-hidden
                />
                <span>{point}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* ROI */}
      <section className="mx-auto max-w-2xl px-4 py-14 text-center sm:px-6 md:py-16">
        <p className="text-base leading-8 text-slate-700 dark:text-slate-300 sm:text-lg sm:leading-8">
          {PRICING_ROI_LINE}
        </p>
      </section>

      {/* FAQ */}
      <section className="border-t border-slate-200/80 bg-[#f7f5f2] py-16 dark:border-slate-700 dark:bg-slate-900/35 sm:py-20 md:py-24">
        <div className="mx-auto max-w-2xl px-4 sm:px-6">
          <h2
            className={`${serif.className} text-center text-3xl tracking-tight text-slate-900 dark:text-white md:text-4xl`}
          >
            FAQ
          </h2>
          <div className="mt-10 space-y-3 sm:mt-12">
            {PRICING_FAQ.map((item) => (
              <details
                key={item.q}
                className="group rounded-2xl border border-slate-200 bg-white px-4 py-1 dark:border-slate-700 dark:bg-slate-900/80 sm:px-5"
              >
                <summary className="cursor-pointer list-none py-4 text-left text-sm font-semibold leading-snug text-slate-900 outline-none dark:text-white sm:text-[15px] [&::-webkit-details-marker]:hidden">
                  <span className="flex items-start justify-between gap-4">
                    <span className="min-w-0 flex-1 pr-2">{item.q}</span>
                    <span
                      className="mt-0.5 shrink-0 text-slate-400 transition-transform duration-200 group-open:rotate-180"
                      aria-hidden
                    >
                      ▼
                    </span>
                  </span>
                </summary>
                <p className="border-t border-slate-100 pb-4 pt-3 text-sm leading-relaxed text-slate-600 dark:border-slate-700 dark:text-slate-300 sm:text-[15px] sm:leading-7">
                  {item.a}
                </p>
              </details>
            ))}
          </div>
        </div>
      </section>

      <footer className="border-t border-slate-200/80 py-10 dark:border-slate-700">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-4 text-sm text-slate-600 dark:text-slate-400 sm:flex-row sm:px-6">
          <Link href="/" className="font-semibold text-slate-900 dark:text-white">
            {PRODUCT_NAME}
          </Link>
          <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2">
            <Link href="/" className="hover:text-slate-900 dark:hover:text-white">
              Back to home
            </Link>
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
