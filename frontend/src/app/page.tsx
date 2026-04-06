import type { ReactNode } from "react";
import Link from "next/link";
import { DM_Serif_Display } from "next/font/google";
import { Button } from "@/components/ui/button";
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
import { cn } from "@/lib/utils";

const serif = DM_Serif_Display({ subsets: ["latin"], weight: "400" });

const trustLogos = ["ATLAS", "LINEAR", "NOTIONX", "OGILVY", "SONY", "TESCO"];

const pricingTiers = [
  {
    name: "Free",
    price: "₹0",
    period: "forever",
    features: [
      "3 file uploads / month",
      "Cleaning and structure",
      "Core views from your metrics",
      "Single workspace",
    ],
    cta: "Start free",
    featured: false,
  },
  {
    name: "Pro",
    price: "₹999",
    period: "/month",
    features: [
      "Unlimited uploads",
      "Full analyst briefing",
      "Natural-language Q&A on your data",
      "Forecasting + trend analysis",
      "Multi-workspace support",
      "Priority support",
    ],
    cta: "Start free trial",
    featured: true,
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "",
    features: [
      "Everything in Pro",
      "Team workspaces",
      "Leadership-ready reporting",
      "Priority support",
      "Security and compliance controls",
    ],
    cta: "Contact sales",
    featured: false,
  },
];

function Tag({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex rounded-full border border-slate-300/80 bg-white/95 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.19em] text-slate-600 shadow-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-300",
        className,
      )}
    >
      {children}
    </span>
  );
}

function WindowFrame({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-[30px] border border-slate-300/70 bg-white/95 p-3 shadow-[0_42px_95px_-52px_rgba(15,23,42,0.58)] dark:border-slate-700 dark:bg-slate-900/80 md:p-4">
      <div className="rounded-[24px] border border-slate-200 bg-slate-50/85 p-4 dark:border-slate-700 dark:bg-slate-900/40 md:p-5">
        <div className="flex items-center justify-between">
          <div className="flex gap-2">
            <span className="h-2 w-2 rounded-full bg-rose-300" />
            <span className="h-2 w-2 rounded-full bg-amber-300" />
            <span className="h-2 w-2 rounded-full bg-emerald-300" />
          </div>
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
            {title}
          </p>
          <div className="h-7 w-16 rounded-full border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800" />
        </div>
        <div className="mt-4">{children}</div>
      </div>
    </div>
  );
}

function SectionIntro({
  tag,
  title,
  body,
}: {
  tag: string;
  title: string;
  body: string;
}) {
  return (
    <div className="fade-up">
      <Tag>{tag}</Tag>
      <h2
        className={`${serif.className} mt-4 text-balance text-4xl leading-[0.95] text-slate-900 dark:text-white md:text-5xl`}
      >
        {title}
      </h2>
      <p className="mt-5 max-w-xl text-[15px] leading-7 text-slate-600 dark:text-slate-300">
        {body}
      </p>
    </div>
  );
}

function HeroVisual() {
  return (
    <WindowFrame title="Executive analytics workspace">
      <div className="grid gap-3 lg:grid-cols-[1.7fr_1fr]">
        <div className="rounded-2xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900/70">
          <div className="grid grid-cols-3 gap-2">
            {[
              { k: "Revenue", v: "$2.1M", delta: "+12%", tone: "bg-[#ede7ff]" },
              { k: "Gross margin", v: "67%", delta: "+2.1%", tone: "bg-[#eaf3ff]" },
              { k: "Growth", v: "+18%", delta: "QoQ", tone: "bg-[#e7f7ef]" },
            ].map((item) => (
              <div key={item.k} className={`rounded-xl p-3 ${item.tone}`}>
                <p className="text-[11px] text-slate-500">{item.k}</p>
                <p className="mt-1 text-sm font-semibold text-slate-900">{item.v}</p>
                <p className="text-[11px] text-slate-500">{item.delta}</p>
              </div>
            ))}
          </div>
          <div className="mt-3 rounded-xl border border-slate-100 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800/70">
            <div className="grid h-40 grid-cols-[1fr_0.38fr] gap-3">
              <div className="relative overflow-hidden rounded-lg bg-white p-2 dark:bg-slate-900/80">
                <div className="absolute inset-0 bg-[linear-gradient(to_bottom,transparent_0%,transparent_24%,rgba(148,163,184,0.12)_24%,rgba(148,163,184,0.12)_26%,transparent_26%,transparent_49%,rgba(148,163,184,0.12)_49%,rgba(148,163,184,0.12)_51%,transparent_51%,transparent_74%,rgba(148,163,184,0.12)_74%,rgba(148,163,184,0.12)_76%,transparent_76%)]" />
                <span className="absolute right-2 top-2 rounded-full bg-indigo-50 px-2 py-1 text-[10px] font-semibold text-indigo-700">
                  Forecast +14%
                </span>
                <svg viewBox="0 0 280 120" className="relative h-full w-full">
                  <path
                    d="M0,94 C22,85 36,86 57,72 C78,59 95,64 117,52 C139,40 158,42 181,33 C203,25 229,24 252,17 C263,14 272,12 280,11"
                    fill="none"
                    stroke="rgb(79 70 229)"
                    strokeWidth="3.5"
                  />
                  <path
                    d="M0,102 C24,96 42,95 63,84 C87,72 107,76 126,68 C150,58 170,60 194,53 C215,46 241,43 280,32"
                    fill="none"
                    stroke="rgb(129 140 248 / 0.65)"
                    strokeWidth="2.2"
                    strokeDasharray="5 5"
                  />
                </svg>
              </div>
              <div className="flex h-full items-end gap-1.5 rounded-lg bg-white px-2 py-2 dark:bg-slate-900/80">
                {[34, 40, 45, 52, 57, 63, 69, 72, 78, 83].map((value, i) => (
                  <div
                    key={`bar-${i}`}
                    className="w-full rounded-sm bg-gradient-to-t from-violet-500 to-indigo-400"
                    style={{ height: `${value}%` }}
                  />
                ))}
              </div>
            </div>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <div className="rounded-lg border border-slate-200 bg-white px-2.5 py-2 dark:border-slate-700 dark:bg-slate-900/80">
                <p className="text-[10px] text-slate-500 dark:text-slate-400">Orders</p>
                <p className="text-xs font-semibold text-slate-900 dark:text-white">14.2k</p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-white px-2.5 py-2 dark:border-slate-700 dark:bg-slate-900/80">
                <p className="text-[10px] text-slate-500 dark:text-slate-400">Cost trend</p>
                <p className="text-xs font-semibold text-slate-900 dark:text-white">-2.4%</p>
              </div>
            </div>
          </div>
        </div>
        <div className="space-y-3">
          <div className="rounded-2xl border border-slate-200 bg-[#ede7ff] p-3 shadow-sm dark:border-slate-700 dark:bg-violet-900/30">
            <p className="text-[11px] font-semibold text-violet-700 dark:text-violet-300">
              AI Summary
            </p>
            <p className="mt-1 text-xs leading-5 text-slate-700 dark:text-slate-200">
              Q2 uplift driven by repeat order retention and CAC improvement.
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-[#fff6d8] p-3 shadow-sm dark:border-slate-700 dark:bg-amber-900/30">
            <p className="text-[11px] font-semibold text-amber-700 dark:text-amber-300">
              Recommendation
            </p>
            <p className="mt-1 text-xs leading-5 text-slate-700 dark:text-slate-200">
              Reduce discount depth by 3% in low-sensitivity segments.
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-700 dark:bg-slate-900/70">
            <p className="text-[11px] text-slate-500 dark:text-slate-400">
              Forecast confidence
            </p>
            <div className="mt-2 h-2 rounded-full bg-slate-100 dark:bg-slate-700">
              <div className="h-2 w-2/3 rounded-full bg-gradient-to-r from-[#8b5cf6] to-[#4f46e5]" />
            </div>
            <p className="mt-2 text-[11px] text-slate-500 dark:text-slate-400">88% model certainty</p>
          </div>
        </div>
      </div>
    </WindowFrame>
  );
}

function HeroFloatingSet() {
  return (
    <>
      <div className="floating hidden xl:block" style={{ left: "2.2rem", top: "7.6rem", transform: "rotate(-4deg)" }}>
        <div className="floating-drift rounded-3xl border border-slate-200 bg-white/95 p-2 shadow-[0_20px_40px_-24px_rgba(15,23,42,0.45)]">
          <div className="rounded-2xl bg-[#ede7ff] p-3">
            <p className="text-[10px] text-violet-700">Revenue +12%</p>
            <p className="mt-1 text-xs text-slate-700">vs last period</p>
          </div>
        </div>
      </div>
      <div className="floating hidden xl:block" style={{ left: "4.8rem", top: "16.7rem", transform: "rotate(-5deg)" }}>
        <div className="floating-drift rounded-3xl border border-slate-200 bg-white/95 p-2 shadow-[0_20px_40px_-24px_rgba(15,23,42,0.45)]" style={{ animationDelay: "1s" }}>
          <div className="rounded-2xl border border-slate-200 bg-white p-3">
            <p className="text-[10px] text-slate-500">Top 3 cost drivers?</p>
            <p className="mt-1 text-xs text-slate-800">Shipping, CAC, Returns</p>
          </div>
        </div>
      </div>
      <div className="floating hidden xl:block" style={{ left: "13.8rem", top: "11.7rem", transform: "rotate(-3deg)" }}>
        <div
          className="floating-drift rounded-3xl border border-violet-100 bg-[#ede7ff] px-3 py-2 shadow-[0_16px_34px_-18px_rgba(79,70,229,0.35)]"
          style={{ animationDelay: "1.4s" }}
        >
          <p className="text-[11px] font-semibold text-violet-700">Executive AI brief</p>
        </div>
      </div>

      <div className="floating hidden xl:block" style={{ right: "3.2rem", top: "8.2rem", transform: "rotate(5deg)" }}>
        <div className="floating-drift rounded-3xl border border-slate-200 bg-white/95 p-2 shadow-[0_20px_40px_-24px_rgba(15,23,42,0.45)]" style={{ animationDelay: "0.5s" }}>
          <div className="rounded-2xl border border-slate-200 bg-white p-3">
            <p className="text-[10px] text-slate-500">Chat</p>
            <p className="mt-1 text-xs text-slate-800">&quot;Why did cost increase?&quot;</p>
          </div>
        </div>
      </div>
      <div className="floating hidden xl:block" style={{ right: "14.3rem", top: "14.5rem", transform: "rotate(-4deg)" }}>
        <div
          className="floating-drift rounded-3xl border border-emerald-100 bg-[#e7f7ef] px-3 py-2 shadow-[0_16px_34px_-18px_rgba(16,185,129,0.35)]"
          style={{ animationDelay: "1.8s" }}
        >
          <p className="text-[10px] text-emerald-700">98.4% data quality</p>
        </div>
      </div>
      <div className="floating hidden xl:block" style={{ right: "8.2rem", top: "18.8rem", transform: "rotate(3deg)" }}>
        <div className="floating-drift rounded-3xl border border-slate-200 bg-white/95 p-2 shadow-[0_20px_40px_-24px_rgba(15,23,42,0.45)]" style={{ animationDelay: "1.3s" }}>
          <div className="rounded-2xl border border-slate-200 bg-white p-3">
            <p className="text-[10px] text-slate-500">Mini graph</p>
            <svg viewBox="0 0 94 24" className="mt-1 h-4 w-20">
              <path d="M0,20 C13,16 20,16 33,12 C44,8 59,10 71,6 C81,4 89,3 94,2" fill="none" stroke="rgb(79 70 229)" strokeWidth="2.2" />
            </svg>
          </div>
        </div>
      </div>

      <div className="floating hidden xl:block" style={{ left: "2.5rem", top: "3.8rem" }}>
        <div className="floating-drift rounded-[26px] bg-[#ede7ff] p-2 shadow-[0_16px_34px_-18px_rgba(79,70,229,0.35)]" style={{ animationDelay: "2s" }}>
          <div className="h-16 w-16 rounded-[20px] bg-gradient-to-b from-white/80 to-violet-100/70 p-2">
            <div className="h-full w-full rounded-full bg-gradient-to-br from-amber-200 via-rose-200 to-violet-300" />
          </div>
        </div>
      </div>
      <div className="floating hidden xl:block" style={{ left: "2.8rem", top: "23.4rem", transform: "rotate(-7deg)" }}>
        <div className="floating-drift rounded-[26px] bg-[#f9e7ef] p-2 shadow-[0_16px_34px_-18px_rgba(219,39,119,0.3)]" style={{ animationDelay: "2.6s" }}>
          <div className="h-16 w-16 rounded-[20px] bg-gradient-to-b from-white/80 to-rose-100/80 p-2">
            <div className="h-full w-full rounded-full bg-gradient-to-br from-sky-200 via-violet-200 to-rose-300" />
          </div>
        </div>
      </div>
      <div className="floating hidden xl:block" style={{ right: "12rem", top: "4.4rem" }}>
        <div className="floating-drift rounded-[26px] bg-[#eaf3ff] p-2 shadow-[0_16px_34px_-18px_rgba(59,130,246,0.35)]" style={{ animationDelay: "2.3s" }}>
          <div className="h-16 w-16 rounded-[20px] bg-gradient-to-b from-white/80 to-sky-100/80 p-2">
            <div className="h-full w-full rounded-full bg-gradient-to-br from-violet-200 via-sky-200 to-fuchsia-200" />
          </div>
        </div>
      </div>
      <div className="floating hidden xl:block" style={{ right: "2.6rem", top: "21.2rem", transform: "rotate(8deg)" }}>
        <div className="floating-drift rounded-[26px] bg-[#fff6d8] p-2 shadow-[0_16px_34px_-18px_rgba(245,158,11,0.35)]" style={{ animationDelay: "2.1s" }}>
          <div className="h-16 w-16 rounded-[20px] bg-gradient-to-b from-white/80 to-amber-100/80 p-2">
            <div className="h-full w-full rounded-full bg-gradient-to-br from-amber-200 via-orange-200 to-rose-300" />
          </div>
        </div>
      </div>

      <svg className="pointer-events-none absolute left-[10rem] top-[10.8rem] hidden h-44 w-56 xl:block" viewBox="0 0 220 160">
        <path
          d="M10,10 C80,20 95,56 120,86 C140,108 170,128 208,146"
          fill="none"
          stroke="rgba(148,163,184,0.55)"
          strokeDasharray="5 7"
          strokeWidth="2"
        />
      </svg>
      <svg className="pointer-events-none absolute right-[6.5rem] top-[11.2rem] hidden h-52 w-60 xl:block" viewBox="0 0 240 170">
        <path
          d="M8,162 C52,140 78,122 98,96 C118,72 150,42 232,12"
          fill="none"
          stroke="rgba(148,163,184,0.55)"
          strokeDasharray="5 7"
          strokeWidth="2"
        />
      </svg>

      <div className="pointer-events-none absolute -left-10 top-20 h-40 w-40 rounded-full bg-[#f9e7ef] blur-3xl" />
      <div className="pointer-events-none absolute right-0 top-10 h-44 w-44 rounded-full bg-[#eaf3ff] blur-3xl" />
      <div className="pointer-events-none absolute left-1/2 top-[22rem] h-28 w-28 -translate-x-1/2 rounded-full bg-[#ede7ff] blur-3xl" />
    </>
  );
}

function WorkspaceVisual() {
  return (
    <div className="group fade-up relative rounded-[28px] bg-gradient-to-br from-violet-300 to-violet-400 p-5 shadow-[0_30px_65px_-35px_rgba(139,92,246,0.85)] transition-transform duration-300 hover:-translate-y-1">
      <div className="absolute -right-6 -top-6 h-20 w-20 rounded-full bg-violet-200/70 blur-2xl" />
      <div className="absolute -left-6 bottom-5 h-16 w-16 rounded-full bg-sky-200/70 blur-2xl" />
      <div className="rounded-2xl border border-violet-100 bg-white p-4">
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold text-slate-900">Workspace groups</p>
          <span className="rounded-full bg-violet-100 px-2 py-1 text-[11px] font-semibold text-violet-700">
            4 active
          </span>
        </div>
        <div className="mt-3 space-y-2">
          <div className="rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-700">
            India retail
          </div>
          <div className="rounded-lg bg-slate-900 px-3 py-2 text-sm text-white">
            Enterprise accounts
          </div>
          <div className="rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-700">
            APAC operations
          </div>
        </div>
        <div className="mt-4 grid grid-cols-[1fr_0.95fr] gap-2">
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-2">
            <p className="text-[11px] text-slate-500">Datasets linked</p>
            <p className="mt-1 text-sm font-semibold text-slate-900">12 files</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-2">
            <p className="text-[11px] text-slate-500">Owner team</p>
            <div className="mt-2 flex -space-x-2">
              <span className="h-6 w-6 rounded-full border border-white bg-gradient-to-br from-slate-300 to-slate-500" />
              <span className="h-6 w-6 rounded-full border border-white bg-gradient-to-br from-violet-300 to-violet-500" />
              <span className="h-6 w-6 rounded-full border border-white bg-gradient-to-br from-sky-300 to-blue-500" />
            </div>
          </div>
        </div>
        <div className="mt-3 rounded-lg border border-slate-200 bg-white p-2.5">
          <p className="text-[10px] text-slate-500">Cross-workspace insight</p>
          <p className="mt-1 text-xs text-slate-700">
            APAC margin recovered after channel mix rebalance in week 3.
          </p>
        </div>
      </div>
    </div>
  );
}

function DashboardFeatureVisual() {
  return (
    <WindowFrame title="Dashboard module">
      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-900/40">
        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-lg bg-[#f9e7ef] p-3">
            <p className="text-[11px] text-slate-500">Orders</p>
            <p className="text-sm font-semibold text-slate-900">14,280</p>
          </div>
          <div className="rounded-lg bg-[#eaf3ff] p-3">
            <p className="text-[11px] text-slate-500">Cost ratio</p>
            <p className="text-sm font-semibold text-slate-900">34%</p>
          </div>
        </div>
        <div className="mt-3 grid grid-cols-[1fr_0.82fr] gap-3">
          <div className="h-28 rounded-lg bg-white p-2 dark:bg-slate-800/80">
            <svg viewBox="0 0 300 90" className="h-full w-full">
              <path
                d="M0,72 C35,66 56,54 82,49 C107,44 122,55 150,41 C176,28 194,33 220,24 C245,16 265,15 300,9"
                fill="none"
                stroke="rgb(79 70 229)"
                strokeWidth="4"
              />
            </svg>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900/70">
            <p className="text-[11px] text-slate-500 dark:text-slate-400">Top line</p>
            <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">
              +14.2%
            </p>
            <p className="mt-2 text-[11px] text-slate-500 dark:text-slate-400">
              vs previous period
            </p>
          </div>
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <div className="rounded-lg border border-slate-200 bg-white p-2.5 dark:border-slate-700 dark:bg-slate-900/70">
            <p className="text-[10px] text-slate-500 dark:text-slate-400">Best segment</p>
            <p className="text-xs font-semibold text-slate-900 dark:text-white">Enterprise Plus</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-2.5 dark:border-slate-700 dark:bg-slate-900/70">
            <p className="text-[10px] text-slate-500 dark:text-slate-400">Anomaly flag</p>
            <p className="text-xs font-semibold text-slate-900 dark:text-white">West returns spike</p>
          </div>
        </div>
      </div>
    </WindowFrame>
  );
}

function ChatFeatureVisual() {
  return (
    <WindowFrame title="AI chat analyst">
      <div className="ml-auto max-w-[82%] rounded-2xl rounded-br-sm bg-slate-900 px-3 py-2 text-xs text-white">
        Why did revenue dip this month?
      </div>
      <div className="mt-3 max-w-[95%] rounded-2xl rounded-bl-sm border border-violet-100 bg-[#ede7ff] px-3 py-2 text-xs leading-5 text-slate-700">
        Main impact came from campaign mix and lower repeat orders in one region.
        AI suggests reducing discount depth by 4% and rebalancing paid channels.
      </div>
      <div className="mt-3 grid grid-cols-[1fr_0.8fr] gap-3">
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800/80">
          <p className="text-[11px] text-slate-500 dark:text-slate-400">
            Forecast trend preview
          </p>
          <svg viewBox="0 0 250 70" className="mt-2 h-16 w-full">
            <path
              d="M0,54 C20,45 42,47 64,38 C90,26 110,30 136,22 C157,16 177,18 201,13 C223,10 238,8 250,8"
              fill="none"
              stroke="rgb(99 102 241)"
              strokeWidth="3"
            />
          </svg>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900/70">
          <p className="text-[11px] text-slate-500 dark:text-slate-400">Confidence</p>
          <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">88%</p>
          <div className="mt-2 h-1.5 rounded-full bg-slate-100 dark:bg-slate-700">
            <div className="h-1.5 w-[88%] rounded-full bg-gradient-to-r from-violet-500 to-indigo-500" />
          </div>
          <p className="mt-2 text-[10px] text-slate-500 dark:text-slate-400">based on 6 data sources</p>
        </div>
      </div>
      <div className="mt-3 rounded-xl border border-slate-200 bg-white p-2.5 dark:border-slate-700 dark:bg-slate-900/70">
        <p className="text-[10px] text-slate-500 dark:text-slate-400">Suggested action</p>
        <p className="text-xs text-slate-700 dark:text-slate-200">
          Increase retention offer for top 40 at-risk accounts before next cycle.
        </p>
      </div>
    </WindowFrame>
  );
}

function Footer() {
  return (
    <footer className="border-t border-slate-200/80 py-12 dark:border-slate-700">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 text-sm text-slate-600 dark:text-slate-300 md:flex-row md:items-center md:justify-between">
        <p className="font-semibold text-slate-900 dark:text-white">{PRODUCT_NAME}</p>
        <div className="flex flex-wrap gap-5">
          <Link href="#solutions" className="hover:text-slate-900 dark:hover:text-white">
            Product
          </Link>
          <Link href="#features" className="hover:text-slate-900 dark:hover:text-white">
            Features
          </Link>
          <Link href="#pricing" className="hover:text-slate-900 dark:hover:text-white">
            Pricing
          </Link>
          <Link href="#cta" className="hover:text-slate-900 dark:hover:text-white">
            Contact
          </Link>
          <span>Privacy</span>
          <span>Terms</span>
        </div>
      </div>
    </footer>
  );
}

function FeatureGrid() {
  const items = [
    {
      title: "AI That Explains Your Business",
      body: "Get clear summaries of what changed, why it changed, and what to do next.",
      tone: "bg-[#ede7ff] border-violet-100",
    },
    {
      title: "See What Happens Next",
      body: "Forecast trends with confidence ranges built from your own historical files.",
      tone: "bg-[#eaf3ff] border-blue-100",
    },
    {
      title: "Ask Questions. Get Answers.",
      body: "Use natural language chat to explore revenue, costs, churn, and growth drivers.",
      tone: "bg-[#fff6d8] border-amber-100",
    },
    {
      title: "All Your Data in One Place",
      body: "Combine sales, finance, and operations sheets into one AI-ready decision layer.",
      tone: "bg-[#e7f7ef] border-emerald-100",
    },
  ];

  return (
    <div className="grid gap-5 md:grid-cols-2">
      {items.map((item, idx) => (
        <div
          key={item.title}
          className={`group fade-up rounded-3xl border p-7 transition-all duration-300 hover:-translate-y-1 hover:shadow-md ${item.tone} ${
            idx % 2 === 0 ? "md:translate-y-2" : ""
          }`}
          style={{ animationDelay: `${idx * 80}ms` }}
        >
          <div className="mb-3 h-8 w-8 rounded-lg bg-white/75 shadow-sm" />
          <h3 className="text-xl font-semibold tracking-tight text-slate-900">{item.title}</h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">{item.body}</p>
        </div>
      ))}
    </div>
  );
}

function PricingSection() {
  return (
    <section id="pricing" className="mx-auto w-full max-w-6xl px-6 py-28">
      <div className="text-center fade-up">
        <Tag>Pricing</Tag>
        <h2 className={`${serif.className} mt-4 text-4xl text-slate-900 dark:text-white md:text-5xl`}>
          Choose the plan that fits your team
        </h2>
        <p className="mx-auto mt-3 max-w-2xl text-[15px] leading-7 text-slate-600 dark:text-slate-300">
          Start free, scale when needed, and unlock a complete AI business
          analyst experience.
        </p>
      </div>
      <div className="mt-12 grid gap-6 md:grid-cols-3">
        {pricingTiers.map((tier) => (
          <div
            key={tier.name}
            className={`group relative rounded-3xl border p-7 shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-xl ${
              tier.featured
                ? "border-violet-300 bg-white ring-2 ring-violet-200 dark:border-violet-400 dark:bg-slate-900 dark:ring-violet-900/80"
                : "border-slate-200 bg-white/95 dark:border-slate-700 dark:bg-slate-900/80"
            }`}
          >
            {tier.featured && (
              <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-violet-600 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-white">
                Most popular
              </span>
            )}
            <p className="text-sm font-semibold text-slate-900 dark:text-white">{tier.name}</p>
            <div className="mt-3 flex items-end gap-1">
              <p className="text-4xl font-semibold tracking-tight text-slate-900 dark:text-white">
                {tier.price}
              </p>
              {tier.period && (
                <p className="pb-1 text-sm text-slate-500 dark:text-slate-400">{tier.period}</p>
              )}
            </div>
            <ul className="mt-5 space-y-2.5">
              {tier.features.map((feature) => (
                <li key={feature} className="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-300">
                  <span className="mt-0.5 text-violet-600 dark:text-violet-400">✓</span>
                  <span>{feature}</span>
                </li>
              ))}
            </ul>
            <LandingPricingCta
              tierName={tier.name}
              cta={tier.cta}
              highlighted={tier.featured}
            />
          </div>
        ))}
      </div>
    </section>
  );
}

export default function LandingPage() {
  return (
    <main className="min-h-screen bg-[#f6f4ef] text-slate-900 dark:bg-[#0c1220] dark:text-slate-100">
      <div className="relative overflow-hidden px-3 pb-8 pt-4 md:px-6">
        <HeroFloatingSet />
        <div className="relative z-10 mx-auto max-w-6xl rounded-[34px] border border-slate-200/80 bg-white/70 px-5 py-5 backdrop-blur-sm dark:border-slate-700 dark:bg-slate-900/45 md:px-8">
          <header className="flex items-center justify-between border-b border-slate-200/80 pb-5 dark:border-slate-700">
            <Link href="/" className="text-base font-semibold tracking-tight text-slate-900 dark:text-white">
              {PRODUCT_NAME}
            </Link>
            <nav className="hidden items-center gap-6 text-sm text-slate-600 dark:text-slate-300 md:flex">
              <Link href="#solutions" className="hover:text-slate-900 dark:hover:text-white">
                Solutions
              </Link>
              <Link href="#features" className="hover:text-slate-900 dark:hover:text-white">
                Features
              </Link>
              <Link href="#pricing" className="hover:text-slate-900 dark:hover:text-white">
                Pricing
              </Link>
              <Link href="#cta" className="hover:text-slate-900 dark:hover:text-white">
                Contact
              </Link>
              <ThemeMenuCompact />
              <div className="flex items-center gap-4">
                <LandingHeaderAuth />
              </div>
            </nav>
            <div className="flex items-center gap-2 md:hidden">
              <ThemeMenuCompact />
              <LandingHeaderAuth />
            </div>
          </header>

          <section className="relative pt-14 md:pt-16">
            <div className="mx-auto max-w-5xl text-center lg:max-w-4xl">
              <div className="fade-up flex justify-center px-2">
                <Tag className="max-w-xl text-balance normal-case text-[11px] font-semibold leading-snug tracking-[0.04em] text-slate-600 dark:text-slate-300 md:max-w-2xl md:px-4 md:py-2">
                  {POSITIONING_LINE}
                </Tag>
              </div>
              <h1 className={`${serif.className} fade-up mt-7 text-slate-900 dark:text-white`}>
                <span className="block text-5xl leading-[0.9] md:text-6xl">Turn</span>
                <span className="mt-1 block text-6xl leading-[0.88] md:text-7xl lg:ml-10">Business Data</span>
                <span className="mt-1 block text-5xl leading-[0.9] md:text-6xl lg:-ml-8">into</span>
                <span className="mt-1 block text-6xl leading-[0.88] md:text-7xl lg:ml-6">
                  <span className="rounded-md bg-[#fff6d8] px-2 py-0.5 text-slate-900 dark:bg-violet-600 dark:text-white dark:shadow-[0_0_28px_-6px_rgba(139,92,246,0.55)]">
                    Confident
                  </span>
                </span>
                <span className="mt-1 block text-6xl leading-[0.88] md:text-7xl lg:ml-16">Decisions</span>
              </h1>
              <p className="fade-up mx-auto mt-7 max-w-2xl text-[17px] leading-8 text-slate-600 dark:text-slate-300">
                <span className="font-semibold text-slate-800 dark:text-slate-100">{PRODUCT_TAGLINE}</span>{" "}
                Upload Excel and CSV, auto-build dashboards and AI summaries, compare periods,
                forecast trends, and ask questions in plain language—one workspace you use as your
                numbers evolve, not a one-off file drop.
              </p>
              <div className="fade-up mt-9 flex flex-wrap items-center justify-center gap-3">
                <LandingHeroPrimaryCta />
                <Link href="#solutions">
                  <Button variant="outline" size="lg" className="h-11 rounded-xl border-slate-300 bg-white px-7 text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800">
                    Book a Demo
                  </Button>
                </Link>
              </div>
              <p className="fade-up mx-auto mt-5 max-w-md text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                Free to start, no card on the free tier. Add workspaces as you grow—your data stays
                in your account.
              </p>
            </div>

            <div className="relative mx-auto mt-14 max-w-5xl">
              <HeroVisual />
              <div className="floating hidden lg:block" style={{ left: "-3.8rem", top: "4.2rem", transform: "rotate(-8deg)" }}>
                <div
                  className="floating-drift rounded-2xl border border-slate-200 bg-white px-3 py-2 shadow-[0_18px_38px_-20px_rgba(15,23,42,0.45)]"
                  style={{ animationDelay: "0.6s" }}
                >
                  <p className="text-[10px] text-slate-500">AI note</p>
                  <p className="text-xs text-slate-800">Orders surge in APAC</p>
                </div>
              </div>
              <div className="floating hidden lg:block" style={{ right: "-3.3rem", bottom: "1.8rem", transform: "rotate(7deg)" }}>
                <div
                  className="floating-drift rounded-2xl border border-slate-200 bg-white px-3 py-2 shadow-[0_18px_38px_-20px_rgba(15,23,42,0.45)]"
                  style={{ animationDelay: "1.4s" }}
                >
                  <p className="text-[10px] text-slate-500">Graph clip</p>
                  <svg viewBox="0 0 92 24" className="mt-1 h-4 w-20">
                    <path d="M0,20 C12,16 20,15 30,12 C43,9 49,12 61,8 C73,4 81,4 92,3" fill="none" stroke="rgb(79 70 229)" strokeWidth="2.2" />
                  </svg>
                </div>
              </div>
              <div className="hidden lg:block absolute -right-12 top-1/2 h-28 w-28 -translate-y-1/2 rounded-full border border-violet-200/60 bg-violet-100/60 blur-[1px]" />
              <div className="hidden lg:block absolute -left-8 bottom-10 h-20 w-20 rounded-2xl border border-sky-100 bg-[#eaf3ff] rotate-12 shadow-sm" />
            </div>
          </section>
        </div>
      </div>

      <section className="border-y border-slate-200/70 bg-white/60 py-7 dark:border-slate-700 dark:bg-slate-900/30">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-center gap-x-10 gap-y-3 px-6">
          {trustLogos.map((logo) => (
            <span key={logo} className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400 dark:text-slate-500">
              {logo}
            </span>
          ))}
        </div>
      </section>

      <section id="solutions" className="mx-auto max-w-6xl px-6 py-28">
        <div className="grid gap-12 lg:grid-cols-[1fr_1fr] lg:items-center">
          <SectionIntro
            tag="Workspace"
            title="Organize your clients and teams in workspaces"
            body="Separate files by team, client, region, or business unit while keeping every dashboard, summary, and forecast context-aware."
          />
          <div className="relative lg:translate-x-6 lg:translate-y-4">
            <div className="hidden lg:block absolute -left-8 -top-8 h-24 w-24 rounded-3xl bg-[#f9e7ef] rotate-[14deg] shadow-[0_18px_42px_-24px_rgba(219,39,119,0.35)]" />
            <div className="hidden lg:block absolute -right-8 bottom-4 h-20 w-20 rounded-full bg-[#eaf3ff] shadow-[0_18px_42px_-24px_rgba(59,130,246,0.35)]" />
            <WorkspaceVisual />
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 pb-14">
        <div className="relative text-center fade-up">
          <div className="hidden md:block absolute -left-2 top-2 h-8 w-8 rounded-full bg-violet-200/70" />
          <div className="hidden md:block absolute right-10 top-4 h-7 w-7 rounded-full bg-amber-200/70" />
          <Tag>Product Experience</Tag>
          <h2 className={`${serif.className} mt-4 text-4xl text-slate-900 dark:text-white md:text-5xl`}>
            Creative product experiences, built for decision speed
          </h2>
          <p className="mx-auto mt-3 max-w-2xl text-[15px] leading-7 text-slate-600 dark:text-slate-300">
            A blend of dashboards, AI analysis, and conversational insights in
            one modern workspace.
          </p>
        </div>
      </section>

      <section className="mx-auto max-w-6xl space-y-8 px-6 py-20">
        <div className="relative grid gap-6 rounded-[32px] border border-[#f1dfff] bg-[#f9e7ef]/75 p-7 md:ml-8 md:grid-cols-[1fr_1.2fr] md:p-9">
          <div className="hidden md:block absolute -left-10 top-10 h-16 w-16 rounded-2xl bg-white/80 rotate-12 shadow-sm" />
          <div className="hidden md:block absolute -right-8 -top-8 h-24 w-24 rounded-full bg-violet-200/70 blur-xl" />
          <div className="fade-up">
            <Tag>Dashboards</Tag>
            <h3 className={`${serif.className} mt-4 text-3xl text-slate-900 md:text-4xl`}>
              Instant Dashboards from Your Data
            </h3>
            <p className="mt-3 text-[15px] leading-7 text-slate-600">
              Auto-build KPIs, trends, period comparisons, and executive-ready
              summaries from uploaded files.
            </p>
          </div>
          <DashboardFeatureVisual />
        </div>

        <div className="relative grid gap-6 rounded-[32px] border border-[#f6e8b3] bg-[#fff6d8]/85 p-7 md:mr-8 md:grid-cols-[1.2fr_1fr] md:p-9">
          <div className="hidden md:block absolute -right-10 top-8 h-14 w-14 rounded-full bg-amber-200/80 shadow-sm" />
          <div className="hidden md:block absolute left-1/2 -bottom-8 h-20 w-20 -translate-x-1/2 rounded-full bg-violet-200/40 blur-2xl" />
          <div className="md:order-2 fade-up md:pl-2">
            <Tag>AI Chat + Insights</Tag>
            <h3 className={`${serif.className} mt-4 text-3xl text-slate-900 md:text-4xl`}>
              Ask Questions. Get Answers.
            </h3>
            <p className="mt-3 text-[15px] leading-7 text-slate-600">
              Ask why revenue changed, what costs increased, what drives growth,
              and which actions matter next.
            </p>
          </div>
          <div className="md:order-1 md:-translate-x-4">
            <ChatFeatureVisual />
          </div>
        </div>
      </section>

      <section id="features" className="bg-[#f7f5f2] py-28 dark:bg-slate-900/35">
        <div className="mx-auto max-w-6xl px-6">
          <div className="mb-10 text-center fade-up">
            <Tag>Core Capabilities</Tag>
            <h2 className={`${serif.className} mt-4 text-4xl text-slate-900 dark:text-white md:text-5xl`}>
              Everything your AI business analyst needs
            </h2>
          </div>
          <FeatureGrid />
        </div>
      </section>

      <PricingSection />

      <section id="cta" className="mx-auto max-w-6xl px-6 py-24">
        <div className="fade-up rounded-[34px] border border-slate-200 bg-gradient-to-r from-[#eaf3ff] via-[#ede7ff] to-[#f9e7ef] px-8 py-14 text-center shadow-sm dark:border-slate-700 dark:from-slate-900 dark:via-slate-800 dark:to-slate-900 md:px-14">
          <Tag>Final CTA</Tag>
          <h2 className={`${serif.className} mx-auto mt-4 max-w-2xl text-balance text-4xl text-slate-900 dark:text-white md:text-5xl`}>
            Start using AI for your business decisions
          </h2>
          <p className="mx-auto mt-4 max-w-2xl text-lg leading-8 text-slate-700 dark:text-slate-300">
            Turn spreadsheets into dashboards, insights, forecasts, and action
            plans in minutes.
          </p>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <LandingFooterPrimaryCta />
            <Link href="#solutions">
              <Button variant="outline" size="lg" className="h-12 px-8 font-semibold">
                See solutions
              </Button>
            </Link>
          </div>
        </div>
      </section>

      <Footer />

    </main>
  );
}
