/** Marketing copy for `/pricing` — enforced caps live in `backend/services/subscription_usage.py` + route checks. */

export type PricingPlan = {
  id: "free" | "starter" | "pro";
  name: string;
  priceDisplay: string;
  period: string;
  subtitle: string;
  features: string[];
  limitations?: string[];
  valueLine?: string;
  cta: string;
  featured: boolean;
  badge?: string;
};

export const PRICING_PLANS: PricingPlan[] = [
  {
    id: "free",
    name: "Free",
    priceDisplay: "₹0",
    period: "",
    subtitle: "Try one business review",
    features: [
      "1 workspace",
      "Up to 2 data uploads",
      "2 analysis runs",
      "Basic dashboard view",
      "Limited AI insights",
    ],
    limitations: [
      "No history tracking",
      "No alerts",
      "No recurring summaries",
    ],
    cta: "Start free",
    featured: false,
  },
  {
    id: "starter",
    name: "Starter",
    priceDisplay: "₹999",
    period: "/ month",
    subtitle: "Run a monthly business review",
    features: [
      "1 workspace",
      "Up to 10 data updates per month",
      "10–15 analysis runs",
      '"What changed" insights',
      "Basic history (last 3 periods)",
      "AI chat for questions",
      "Operator summary and key signals",
    ],
    valueLine:
      "Perfect for founders who want a clear monthly read on revenue, cost, and profit.",
    cta: "Start Starter plan",
    featured: false,
  },
  {
    id: "pro",
    name: "Pro",
    priceDisplay: "₹1999",
    period: "/ month",
    subtitle: "Continuously monitor and improve your business",
    badge: "Most popular",
    features: [
      "Everything in Starter",
      "3–5 workspaces",
      "Up to 30 data updates per month",
      "Full history tracking",
      "Advanced comparisons across periods",
      "Alerts when something changes or breaks",
      "Weekly and monthly summaries",
      "Deeper AI insights and analysis",
      "Priority processing",
    ],
    valueLine: "Built for ongoing use — not one-time analysis.",
    cta: "Upgrade to Pro",
    featured: true,
  },
];

export const PRICING_VALUE_HEADLINE = "Why businesses keep using Snaptix";

export const PRICING_VALUE_POINTS = [
  "See what changed, not just what exists",
  "Catch problems before they grow",
  "Track trends across time, not static snapshots",
  "Get clear actions, not just charts",
];

export const PRICING_ROI_LINE =
  "If Snaptix helps you avoid one bad decision or spot one missed opportunity, it pays for itself.";

export type PricingFaqItem = { q: string; a: string };

export const PRICING_FAQ: PricingFaqItem[] = [
  {
    q: "Do I need to upload data every time?",
    a: "You can upload new data whenever you want updated insights. Over time, Snaptix builds history to show trends and changes.",
  },
  {
    q: "What kind of files can I upload?",
    a: "Excel and CSV files such as revenue reports, expenses, marketing data, customer data, and more.",
  },
  {
    q: "Can I cancel anytime?",
    a: "Yes, you can cancel your subscription anytime. Your data remains accessible based on your plan limits.",
  },
  {
    q: "What's the difference between Starter and Pro?",
    a: "Starter is designed for monthly reviews. Pro is built for continuous monitoring with alerts, history, and deeper insights.",
  },
  {
    q: "Is my data secure?",
    a: "Your data stays private to your workspace and is not shared or used outside your account.",
  },
];
