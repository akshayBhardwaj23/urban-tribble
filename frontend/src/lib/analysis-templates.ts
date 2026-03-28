/**
 * Template-first import: each template defines files to bring and the analysis framing users get.
 */

export interface AnalysisTemplate {
  id: string;
  title: string;
  /** Short line on the landing picker */
  summary: string;
  /** What the product focuses on after ingest (shown after template is chosen) */
  analysisDelivered: string;
  /** Scannable bullet labels — typical files or exports to bring */
  recommendedInputs: readonly string[];
  suggestedFiles: string;
  bestFor?: string;
  contextPlaceholder: string;
}

/** Manual path — no predefined outcome */
export const CUSTOM_ANALYSIS_TEMPLATE: AnalysisTemplate = {
  id: "custom",
  title: "Manual upload",
  summary: "Bring files when you already know what you’re loading.",
  analysisDelivered:
    "Standard pipeline: we detect structure, classify each dataset, map dates and amounts, and you confirm before dashboards and workspace analysis run.",
  recommendedInputs: [
    "Structured tables (rows = records, columns = fields)",
    "Exports from sales, finance, marketing, or ops",
    "Several related files in one import when useful",
  ],
  suggestedFiles: "Any structured spreadsheet — sales, finance, marketing, or ops exports (Excel, CSV, TSV).",
  bestFor: "Teams with ready files or one-off imports.",
  contextPlaceholder:
    'e.g. "Q3 regional sales", "Vendor spend by department", "Weekly funnel export"',
};

export const ANALYSIS_TEMPLATES: AnalysisTemplate[] = [
  {
    id: "monthly_business_review",
    title: "Monthly business review",
    summary: "Leadership-ready view of how the month moved versus prior periods.",
    analysisDelivered:
      "Executive-style read: key metrics vs last period, what shifted, and a short list of risks and opportunities—aligned to a monthly operating rhythm.",
    recommendedInputs: [
      "Revenue report",
      "Expense sheet",
      "Customer or account summary",
    ],
    suggestedFiles:
      "KPI or scorecard exports, revenue and cost summaries, pipeline or forecast snapshots. One file or several that cover the same period.",
    bestFor: "CEOs, COOs, and finance partners running a monthly cadence.",
    contextPlaceholder:
      'e.g. "September MBR — revenue, opex, pipeline vs plan"',
  },
  {
    id: "profit_leak_audit",
    title: "Profit leak audit",
    summary: "Surface margin and spend patterns that quietly erode profit.",
    analysisDelivered:
      "Focus on margin drains: unusual cost or discount patterns, heavy vendors or categories, and concentration so you can prioritize fixes with numbers behind them.",
    recommendedInputs: [
      "P&L or margin extract",
      "Vendor spend detail",
      "COGS, discounts, or promo export",
    ],
    suggestedFiles:
      "P&L or margin extracts, COGS by product or channel, vendor spend, discounts or promotions, expense detail by category.",
    bestFor: "Finance, FP&A, and commercial leaders protecting profitability.",
    contextPlaceholder:
      'e.g. "Q2 margin walk — discounts and COGS by SKU"',
  },
  {
    id: "sales_performance",
    title: "Sales performance analysis",
    summary: "Rep, region, and product performance in one coherent picture.",
    analysisDelivered:
      "Performance against time and segments: who and what is driving revenue, lagging areas, and trend signals you can use in reviews and planning.",
    recommendedInputs: [
      "Opportunity, order, or revenue export",
      "Rep, region, or territory breakdown",
      "Product, SKU, or segment split",
    ],
    suggestedFiles:
      "Opportunity or order exports, revenue by rep or territory, product or segment splits, quota or target columns if you have them.",
    bestFor: "Sales leadership and revenue operations.",
    contextPlaceholder:
      'e.g. "H1 bookings by AE and region"',
  },
  {
    id: "campaign_efficiency",
    title: "Campaign efficiency review",
    summary: "Compare spend, reach, and outcomes across campaigns and channels.",
    analysisDelivered:
      "Efficiency lens: cost per outcome, channel and campaign comparison, and where budget is working—so marketing can reallocate with clarity.",
    recommendedInputs: [
      "Ad spend export",
      "Attributed revenue or conversion report",
      "Campaign-level metrics (CPA, ROAS, etc.)",
    ],
    suggestedFiles:
      "Ad platform or export spreadsheets: spend, impressions, clicks, conversions by campaign, ad set, or channel.",
    bestFor: "Marketing and growth teams.",
    contextPlaceholder:
      'e.g. "Q4 paid social + search — CPA by campaign"',
  },
  {
    id: "customer_value",
    title: "Customer value breakdown",
    summary: "See concentration, segments, and value across your customer base.",
    analysisDelivered:
      "Value and mix: top accounts, segment-level revenue or retention signals, and where concentration sits—useful for CS, sales, and strategy.",
    recommendedInputs: [
      "CRM or account export",
      "Revenue, ARR, or subscription billing",
      "Segment, tier, industry, or health fields",
    ],
    suggestedFiles:
      "CRM or billing exports: accounts, revenue or ARR, tiers, industry or region, activity or health fields if available.",
    bestFor: "Customer success, sales strategy, and lifecycle marketing.",
    contextPlaceholder:
      'e.g. "Enterprise vs SMB — ARR and NRR inputs"',
  },
];

export const ALL_TEMPLATE_OPTIONS: AnalysisTemplate[] = [
  ...ANALYSIS_TEMPLATES,
  CUSTOM_ANALYSIS_TEMPLATE,
];

export function getTemplateById(id: string): AnalysisTemplate {
  return (
    ALL_TEMPLATE_OPTIONS.find((t) => t.id === id) ?? CUSTOM_ANALYSIS_TEMPLATE
  );
}

export function isGuidedTemplate(t: AnalysisTemplate): boolean {
  return t.id !== "custom";
}
