import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

const features = [
  {
    title: "Smart Data Cleaning",
    description:
      "Auto-removes duplicates, fixes date formats, handles missing values, and normalizes columns before any analysis begins.",
    icon: "⟳",
  },
  {
    title: "AI-Powered Analysis",
    description:
      "GPT-4o analyzes your data and delivers executive summaries, key metrics, anomaly detection, and actionable recommendations.",
    icon: "◆",
  },
  {
    title: "Auto-Generated Dashboards",
    description:
      "Charts are picked based on your data — line charts for trends, bar charts for comparisons, pie charts for distributions.",
    icon: "◫",
  },
  {
    title: "Chat With Your Data",
    description:
      'Ask plain English questions like "What was my best month?" and get answers grounded in actual computed results.',
    icon: "◉",
  },
  {
    title: "Revenue Forecasting",
    description:
      "Predict future trends with confidence intervals using linear regression on your historical data.",
    icon: "↗",
  },
  {
    title: "Multi-File Intelligence",
    description:
      "Upload multiple files and we auto-detect relationships across datasets for cross-file analysis.",
    icon: "⊞",
  },
];

const pricingTiers = [
  {
    name: "Free",
    price: "₹0",
    period: "forever",
    features: [
      "3 uploads per month",
      "Basic dashboards",
      "Data cleaning",
      "Column detection",
    ],
    cta: "Get Started",
    highlighted: false,
  },
  {
    name: "Pro",
    price: "₹999",
    period: "/month",
    features: [
      "Unlimited uploads",
      "AI analysis (GPT-4o)",
      "AI chat with data",
      "Forecasting",
      "Multi-file relations",
      "Priority support",
    ],
    cta: "Start Free Trial",
    highlighted: true,
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "",
    features: [
      "Everything in Pro",
      "Team workspaces",
      "Shared dashboards",
      "Scheduled reports",
      "Custom integrations",
      "Dedicated support",
    ],
    cta: "Contact Us",
    highlighted: false,
  },
];

export default function LandingPage() {
  return (
    <div className="flex flex-col min-h-screen">
      {/* Nav */}
      <header className="border-b">
        <div className="mx-auto max-w-6xl flex items-center justify-between px-6 h-14">
          <span className="text-lg font-semibold tracking-tight">
            Excel Consultant
          </span>
          <div className="flex items-center gap-4">
            <Link
              href="/upload"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Dashboard
            </Link>
            <Link href="/upload">
              <Button size="sm">Get Started</Button>
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="mx-auto max-w-6xl px-6 py-24 md:py-32 text-center">
        <h1 className="text-4xl md:text-5xl font-bold tracking-tight leading-tight max-w-3xl mx-auto">
          Turn your spreadsheets into{" "}
          <span className="text-primary">business intelligence</span>
        </h1>
        <p className="mt-6 text-lg text-muted-foreground max-w-2xl mx-auto leading-relaxed">
          Upload your Excel or CSV files and get AI-powered dashboards,
          insights, forecasting, and natural language querying — in seconds, not
          days.
        </p>
        <div className="mt-8 flex items-center justify-center gap-4">
          <Link href="/upload">
            <Button size="lg" className="h-12 px-8">
              Upload Your Data
            </Button>
          </Link>
          <Link href="#features">
            <Button variant="outline" size="lg" className="h-12 px-8">
              See How It Works
            </Button>
          </Link>
        </div>
        <p className="mt-4 text-xs text-muted-foreground">
          No signup required. Start analyzing in 30 seconds.
        </p>
      </section>

      {/* Features */}
      <section id="features" className="border-t bg-muted/30 py-20">
        <div className="mx-auto max-w-6xl px-6">
          <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-center">
            Everything you need to understand your data
          </h2>
          <p className="mt-3 text-center text-muted-foreground max-w-xl mx-auto">
            From raw spreadsheets to actionable insights — powered by AI.
          </p>
          <div className="mt-12 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {features.map((feature) => (
              <Card key={feature.title} className="border bg-card">
                <CardContent className="pt-6">
                  <div className="flex h-10 w-10 items-center justify-center rounded-md bg-primary/10 text-lg">
                    {feature.icon}
                  </div>
                  <h3 className="mt-4 text-sm font-semibold">
                    {feature.title}
                  </h3>
                  <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
                    {feature.description}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="py-20">
        <div className="mx-auto max-w-6xl px-6">
          <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-center">
            Three steps to insights
          </h2>
          <div className="mt-12 grid gap-8 md:grid-cols-3">
            {[
              {
                step: "1",
                title: "Upload",
                desc: "Drop your Excel or CSV file and tell us what it represents.",
              },
              {
                step: "2",
                title: "Analyze",
                desc: "We clean, detect columns, and run AI analysis automatically.",
              },
              {
                step: "3",
                title: "Explore",
                desc: "View dashboards, chat with your data, and forecast trends.",
              },
            ].map((item) => (
              <div key={item.step} className="text-center">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-foreground font-bold text-lg">
                  {item.step}
                </div>
                <h3 className="mt-4 font-semibold">{item.title}</h3>
                <p className="mt-2 text-sm text-muted-foreground">
                  {item.desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="border-t bg-muted/30 py-20">
        <div className="mx-auto max-w-6xl px-6">
          <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-center">
            Simple, transparent pricing
          </h2>
          <p className="mt-3 text-center text-muted-foreground">
            Start free, upgrade when you need AI-powered insights.
          </p>
          <div className="mt-12 grid gap-6 md:grid-cols-3">
            {pricingTiers.map((tier) => (
              <Card
                key={tier.name}
                className={`relative ${tier.highlighted ? "border-primary shadow-md" : ""}`}
              >
                {tier.highlighted && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <span className="rounded-full bg-primary px-3 py-1 text-xs font-medium text-primary-foreground">
                      Most Popular
                    </span>
                  </div>
                )}
                <CardContent className="pt-8 pb-6 flex flex-col h-full">
                  <h3 className="font-semibold">{tier.name}</h3>
                  <div className="mt-2 flex items-baseline gap-1">
                    <span className="text-3xl font-bold">{tier.price}</span>
                    <span className="text-sm text-muted-foreground">
                      {tier.period}
                    </span>
                  </div>
                  <ul className="mt-6 space-y-2 flex-1">
                    {tier.features.map((f) => (
                      <li
                        key={f}
                        className="text-sm text-muted-foreground flex items-center gap-2"
                      >
                        <span className="text-green-600 text-xs">&#10003;</span>
                        {f}
                      </li>
                    ))}
                  </ul>
                  <Link href="/upload" className="mt-6 block">
                    <Button
                      className="w-full"
                      variant={tier.highlighted ? "default" : "outline"}
                    >
                      {tier.cta}
                    </Button>
                  </Link>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t py-8">
        <div className="mx-auto max-w-6xl px-6 flex items-center justify-between">
          <span className="text-sm text-muted-foreground">
            Excel Consultant
          </span>
          <span className="text-xs text-muted-foreground">
            Built for businesses that run on spreadsheets.
          </span>
        </div>
      </footer>
    </div>
  );
}
