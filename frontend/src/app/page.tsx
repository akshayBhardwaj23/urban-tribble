import type { ReactNode } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ThemeMenuCompact } from "@/components/theme-menu";
import {
  LandingFooterPrimaryCta,
  LandingHeaderAuth,
  LandingHeroPrimaryCta,
  LandingPricingCta,
} from "@/components/landing-auth";
import {
  POSITIONING_LINE,
  PRODUCT_NAME,
  PRODUCT_TAGLINE,
} from "@/lib/brand";

/** Six outcome-sharp capabilities—titles are hooks, bodies stay under ~2 lines */
const features = [
  {
    title: "Files cleaned before they’re summarized",
    description:
      "Duplicates, broken dates, and junk columns get fixed first. Nothing downstream is built on numbers that don’t tie.",
  },
  {
    title: "A written read—not a wall of widgets",
    description:
      "Bottom line, the KPIs that anchor decisions, what moved, and what looks wrong. Charts only when they clarify revenue, mix, or trend.",
  },
  {
    title: "Questions in the language you already use",
    description:
      "Ask about margin by region, best month, or heavy cost lines. Answers pull from your actual aggregates—not canned AI filler.",
  },
  {
    title: "See trajectory when your series allow it",
    description:
      "Trend and breakdown views from your columns. Enough to align the team on growth and cost without building a deck from scratch.",
  },
  {
    title: "Forward bands from your own history",
    description:
      "Simple forecasts and intervals to pressure-test next quarter’s plan. Honest about uncertainty—useful for planning, not prophecy.",
  },
  {
    title: "One workspace, every ledger",
    description:
      "Revenue next to spend next to campaigns. Cross-file questions so separate tabs stop hiding how the month actually landed.",
  },
];

const pricingTiers = [
  {
    name: "Free",
    price: "₹0",
    period: "forever",
    features: [
      "3 uploads / month",
      "Cleaning & structure",
      "Core views from your metrics",
      "Workspace for your files",
    ],
    cta: "Start free",
    highlighted: false,
  },
  {
    name: "Pro",
    price: "₹999",
    period: "/month",
    features: [
      "Unlimited uploads",
      "Full analyst briefing (model-backed)",
      "Plain-English Q&A on your data",
      "Forecasts from your history",
      "Multi-file & overview",
      "Priority support",
    ],
    cta: "Start free trial",
    highlighted: true,
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "",
    features: [
      "Everything in Pro",
      "Team workspaces",
      "Leadership-ready views",
      "Scheduled exports (roadmap)",
      "Integrations on request",
      "Dedicated support",
    ],
    cta: "Contact us",
    highlighted: false,
  },
];

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
      {children}
    </p>
  );
}

export default function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-border/80 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-6">
          <Link
            href="/"
            className="text-base font-semibold tracking-tight text-foreground hover:opacity-80"
          >
            {PRODUCT_NAME}
          </Link>
          <nav className="flex items-center gap-4 sm:gap-6">
            <ThemeMenuCompact className="sm:mr-1" />
            <Link
              href="#value"
              className="hidden text-sm text-muted-foreground transition-colors hover:text-foreground sm:inline"
            >
              Why {PRODUCT_NAME}
            </Link>
            <Link
              href="#features"
              className="hidden text-sm text-muted-foreground transition-colors hover:text-foreground sm:inline"
            >
              Capabilities
            </Link>
            <Link
              href="#pricing"
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              Pricing
            </Link>
            <LandingHeaderAuth />
          </nav>
        </div>
      </header>

      <section className="mx-auto max-w-5xl px-6 pb-20 pt-16 text-center md:pb-24 md:pt-20">
        <SectionLabel>{POSITIONING_LINE}</SectionLabel>
        <h1 className="mx-auto mt-5 max-w-[36rem] text-balance text-4xl font-bold leading-[1.08] tracking-tight text-foreground md:text-[2.75rem] md:leading-[1.06]">
          Know what to do next on{" "}
          <span className="text-primary">growth, profit, and spend</span>—from
          the files you already have.
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-muted-foreground md:text-[17px] md:leading-7">
          Upload the spreadsheets your business already runs on—revenue sheets,
          expense ledgers, P&amp;L extracts, inventory, payroll summaries, and
          other operational files. {PRODUCT_NAME} turns them into a clear view of
          what&apos;s working, where profit is under pressure, and which levers
          deserve a decision this week—not another pile of charts to interpret.
        </p>
        <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
          <LandingHeroPrimaryCta />
          <Link href="#how-it-works">
            <Button variant="outline" size="lg" className="h-12 px-8 font-semibold">
              See how it works
            </Button>
          </Link>
        </div>
        <p className="mx-auto mt-5 max-w-md text-xs leading-relaxed text-muted-foreground">
          Free to start, no card required. Sign in with Google, add a workspace,
          and upload in minutes—your data stays in your account.
        </p>
      </section>

      {/* 1. Value proposition — owners, not analysts */}
      <section
        id="value"
        className="border-t border-border/60 bg-muted/20 py-24 md:py-32"
      >
        <div className="mx-auto max-w-5xl px-6">
          <div className="grid gap-14 lg:grid-cols-12 lg:gap-12 lg:items-start">
            <div className="lg:col-span-7">
              <SectionLabel>Who it&apos;s for</SectionLabel>
              <h2 className="mt-5 text-3xl font-bold leading-[1.15] tracking-tight text-foreground md:text-4xl md:leading-[1.12]">
                Built for the person who signs the checks—not the person who
                lives in a spreadsheet all day.
              </h2>
              <p className="mt-6 max-w-xl text-base leading-relaxed text-muted-foreground md:text-[17px] md:leading-7">
                If you close the month, green-light spend, and carry the P&amp;L
                in your head, you shouldn&apos;t need a data team or a six-week
                project to know whether revenue and margin moved for the right
                reasons. {PRODUCT_NAME} is built for that job: fast reads on
                real files, written so you can act—not so an analyst can tinker.
              </p>
            </div>
            <div className="lg:col-span-5 lg:pt-10">
              <ul className="space-y-0 divide-y divide-border/80 border-t border-border/80">
                {[
                  {
                    t: "Decisions, not dashboards",
                    d: "You get a stance on growth, profit, and waste—then you hire, price, or cut.",
                  },
                  {
                    t: "No new vocabulary",
                    d: "Upload Excel or CSV. Ask in plain language. No query language or training week.",
                  },
                  {
                    t: "Your rows, your risk",
                    d: "Answers trace to the files you uploaded—not generic benchmarks or filler.",
                  },
                ].map((row) => (
                  <li key={row.t} className="py-6 first:pt-6">
                    <p className="font-semibold text-foreground">{row.t}</p>
                    <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                      {row.d}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* 2. Features grid — 6 cards */}
      <section id="features" className="border-t border-border/60 py-24 md:py-32">
        <div className="mx-auto max-w-5xl px-6">
          <div className="max-w-2xl">
            <SectionLabel>What you get</SectionLabel>
            <h2 className="mt-5 text-3xl font-bold tracking-tight text-foreground md:text-4xl">
              Everything that turns files into a point of view
            </h2>
            <p className="mt-4 text-base leading-relaxed text-muted-foreground md:text-[17px]">
              Six capabilities. Each one exists so you spend less time
              reconciling and more time choosing what to do about revenue, cost,
              and cash.
            </p>
          </div>
          <div className="mt-16 grid gap-px bg-border/60 sm:grid-cols-2 lg:grid-cols-3">
            {features.map((feature) => (
              <div
                key={feature.title}
                className="bg-background p-8 md:p-10"
              >
                <h3 className="text-[15px] font-semibold leading-snug tracking-tight text-foreground">
                  {feature.title}
                </h3>
                <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                  {feature.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 3. How it works — 3 steps */}
      <section
        id="how-it-works"
        className="border-t border-border/60 bg-muted/15 py-24 md:py-32"
      >
        <div className="mx-auto max-w-5xl px-6">
          <div className="mx-auto max-w-2xl text-center">
            <SectionLabel>Flow</SectionLabel>
            <h2 className="mt-5 text-3xl font-bold tracking-tight text-foreground md:text-4xl">
              Three steps from file to decision
            </h2>
            <p className="mt-4 text-base text-muted-foreground">
              No implementation. No empty template. You bring what you already
              run the business on.
            </p>
          </div>
          <div className="mx-auto mt-20 max-w-3xl space-y-12 md:space-y-16">
            {[
              {
                step: "01",
                title: "Upload your real files",
                desc: "Revenue, expenses, inventory, payroll—Excel or CSV. One line of context per file so the briefing lands in the right frame.",
              },
              {
                step: "02",
                title: `${PRODUCT_NAME} prepares and reads them`,
                desc: "We clean structure, run the analyst pass, and surface the bottom line, KPIs, downside and upside, and concrete moves tied to your numbers.",
              },
              {
                step: "03",
                title: "You act",
                desc: "Skim the take, ask follow-ups in chat, check trends. Then reprice, reallocate, or cut—on purpose, not on gut alone.",
              },
            ].map((item) => (
              <div
                key={item.step}
                className="flex flex-col gap-5 border-b border-border/50 pb-12 last:border-0 last:pb-0 md:flex-row md:items-start md:gap-10 md:pb-16"
              >
                <span className="font-mono text-sm font-medium tabular-nums text-primary md:w-12 md:shrink-0">
                  {item.step}
                </span>
                <div>
                  <h3 className="text-xl font-semibold tracking-tight text-foreground md:text-2xl">
                    {item.title}
                  </h3>
                  <p className="mt-3 max-w-xl text-sm leading-relaxed text-muted-foreground md:text-base md:leading-relaxed">
                    {item.desc}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="pricing" className="border-t border-border/60 py-24 md:py-32">
        <div className="mx-auto max-w-5xl px-6">
          <div className="text-center">
            <SectionLabel>Pricing</SectionLabel>
            <h2 className="mt-5 text-3xl font-bold tracking-tight text-foreground md:text-4xl">
              Prove it free. Go deep when it earns the time back.
            </h2>
            <p className="mx-auto mt-4 max-w-lg text-base text-muted-foreground">
              Start on Free. Move to Pro when you&apos;re in the product every
              week for real calls on margin and growth.
            </p>
          </div>
          <div className="mt-16 grid gap-6 md:grid-cols-3">
            {pricingTiers.map((tier) => (
              <Card
                key={tier.name}
                className={`relative border-border/80 ${tier.highlighted ? "border-primary shadow-lg ring-1 ring-primary/20" : "shadow-sm"}`}
              >
                {tier.highlighted && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <span className="rounded-full bg-primary px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-primary-foreground">
                      Most popular
                    </span>
                  </div>
                )}
                <CardContent className="flex h-full flex-col pb-6 pt-9">
                  <h3 className="font-semibold text-foreground">{tier.name}</h3>
                  <div className="mt-2 flex items-baseline gap-1">
                    <span className="text-3xl font-bold tracking-tight text-foreground">
                      {tier.price}
                    </span>
                    <span className="text-sm text-muted-foreground">
                      {tier.period}
                    </span>
                  </div>
                  <ul className="mt-6 flex-1 space-y-2.5">
                    {tier.features.map((f) => (
                      <li
                        key={f}
                        className="flex gap-2 text-sm text-muted-foreground"
                      >
                        <span className="mt-0.5 shrink-0 text-xs text-primary">
                          &#10003;
                        </span>
                        {f}
                      </li>
                    ))}
                  </ul>
                  <LandingPricingCta
                    tierName={tier.name}
                    cta={tier.cta}
                    highlighted={tier.highlighted}
                  />
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* 4. Final CTA — upload + demo */}
      <section
        id="cta"
        className="border-t border-border/60 bg-gradient-to-b from-muted/30 to-muted/50 py-24 md:py-32"
      >
        <div className="mx-auto max-w-3xl px-6 text-center">
          <h2 className="text-3xl font-bold tracking-tight text-foreground md:text-4xl">
            Put your numbers where you can argue with them
          </h2>
          <p className="mx-auto mt-5 max-w-lg text-base leading-relaxed text-muted-foreground">
            Upload a revenue or expense file and get a first read in minutes—or
            walk the three steps above if you want the full picture before you
            sign in.
          </p>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <LandingFooterPrimaryCta />
            <Link href="#how-it-works">
              <Button variant="outline" size="lg" className="h-12 px-8 font-semibold">
                See the demo walkthrough
              </Button>
            </Link>
          </div>
          <p className="mx-auto mt-6 max-w-sm text-xs leading-relaxed text-muted-foreground">
            Same Google account you use today. No card on the free tier.
          </p>
        </div>
      </section>

      <footer className="border-t border-border/80 py-12">
        <div className="mx-auto flex max-w-5xl flex-col gap-4 px-6 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-sm font-semibold text-foreground">
              {PRODUCT_NAME}
            </p>
            <p className="mt-1 max-w-sm text-xs leading-relaxed text-muted-foreground">
              {POSITIONING_LINE}
            </p>
          </div>
          <p className="max-w-xs text-xs leading-relaxed text-muted-foreground sm:text-right">
            {PRODUCT_TAGLINE}
          </p>
        </div>
      </footer>
    </div>
  );
}
