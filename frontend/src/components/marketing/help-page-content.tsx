import Link from "next/link";
import { DemoVideoEmbed } from "@/components/marketing/demo-video-embed";
import { Card, CardContent } from "@/components/ui/card";
import { CONTACT_EMAIL, PRODUCT_NAME, contactMailto } from "@/lib/brand";
import { cn } from "@/lib/utils";

const quickStartSteps = [
  {
    title: "Import your spreadsheets",
    body: "Upload Excel or CSV exports from finance, sales, or ops. Snaptix reads structure and prepares charts and briefings.",
    href: "/upload",
    cta: "Go to Import",
  },
  {
    title: "Run a workspace briefing",
    body: "On Overview, run a briefing to get snapshot tiles, operator summary, and a full AI read across your sources.",
    href: "/dashboard",
    cta: "Open Overview",
  },
  {
    title: "Ask questions in Q&A",
    body: "Use workspace chat to compare sources without double-counting revenue. Answers stay grounded in what you imported.",
    href: "/dashboard",
    cta: "Try Q&A",
  },
] as const;

const faqItems = [
  {
    q: "What files work best?",
    a: "Structured exports with clear date and amount columns - monthly P&L by channel, order detail, campaign spend, SKU margin, and similar.",
  },
  {
    q: "Can I use more than one file?",
    a: "Yes. Each file is a source in your workspace. The overview briefing merges them, but revenue totals should not be added across overlapping sources.",
  },
  {
    q: "How do I get help from the team?",
    a: `Email ${CONTACT_EMAIL} with your question, plan, or rollout context. We usually reply within one business day.`,
  },
] as const;

type HelpPageContentProps = {
  /** When true, CTAs assume the user is already in the signed-in app */
  inApp?: boolean;
  className?: string;
};

export function HelpPageContent({ inApp = false, className }: HelpPageContentProps) {
  const mailHref = contactMailto("Snaptix - help");

  return (
    <div className={cn("mx-auto max-w-3xl space-y-10", className)}>
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Help
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground md:text-3xl">
          Demo and getting started
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
          Watch how {PRODUCT_NAME} turns spreadsheet exports into briefings, charts,
          and Q&A - then follow the steps below to run your first workspace review.
        </p>
      </div>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold tracking-tight text-foreground">
          Product demo
        </h2>
        <DemoVideoEmbed />
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold tracking-tight text-foreground">
          Quick start
        </h2>
        <div className="grid gap-4">
          {quickStartSteps.map((step, index) => (
            <Card key={step.title} className="border-border/80 shadow-sm">
              <CardContent className="p-5">
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                  Step {index + 1}
                </p>
                <h3 className="mt-2 text-base font-semibold text-foreground">
                  {step.title}
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  {step.body}
                </p>
                {inApp ? (
                  <Link
                    href={step.href}
                    className="mt-4 inline-flex h-8 items-center rounded-lg border border-border bg-background px-3 text-sm font-medium hover:bg-muted"
                  >
                    {step.cta}
                  </Link>
                ) : (
                  <Link
                    href="/login"
                    className="mt-4 inline-flex h-8 items-center rounded-lg border border-border bg-background px-3 text-sm font-medium hover:bg-muted"
                  >
                    Sign in to start
                  </Link>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold tracking-tight text-foreground">
          Common questions
        </h2>
        <div className="space-y-3">
          {faqItems.map((item) => (
            <details
              key={item.q}
              className="group rounded-xl border border-border/80 bg-card px-4 py-3 shadow-sm"
            >
              <summary className="cursor-pointer list-none text-sm font-medium text-foreground [&::-webkit-details-marker]:hidden">
                <span className="flex items-center justify-between gap-3">
                  {item.q}
                  <span className="text-muted-foreground transition-transform group-open:rotate-180">
                    ▾
                  </span>
                </span>
              </summary>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                {item.a}
              </p>
            </details>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-border/80 bg-muted/30 px-5 py-6">
        <h2 className="text-base font-semibold text-foreground">Still stuck?</h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Email{" "}
          <a
            href={mailHref}
            className="font-medium text-foreground underline underline-offset-2"
          >
            {CONTACT_EMAIL}
          </a>{" "}
          with your workspace question, billing issue, or rollout plan.
        </p>
        <a
          href={mailHref}
          className="mt-4 inline-flex h-8 items-center rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          Email {CONTACT_EMAIL}
        </a>
      </section>
    </div>
  );
}
