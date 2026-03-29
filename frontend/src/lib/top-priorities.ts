import {
  normalizeInsightsList,
  sortInsightsForDisplay,
} from "@/lib/analysis-normalize";

export type PriorityKind =
  | "risk"
  | "opportunity"
  | "inefficiency"
  | "anomaly"
  | "next_action";

export type PriorityLevel = "high" | "medium" | "low";

export interface TopPriorityItem {
  kind: PriorityKind;
  priority: PriorityLevel;
  title: string;
  explanation: string;
}

const INEFF_PAT =
  /cost|spend|waste|inefficien|overhead|margin|leak|duplicate|creep|burn|opex|cogs|utilization|throughput|bottleneck/i;

function truncate(s: string, max: number): string {
  const t = s.trim();
  if (t.length <= max) return t;
  const cut = t.slice(0, max - 1);
  const sp = cut.lastIndexOf(" ");
  return (sp > 40 ? cut.slice(0, sp) : cut).trim() + "…";
}

function firstSentence(s: string, maxLen: number): string {
  const t = s.trim();
  if (!t) return "";
  const end = t.search(/[.!?](\s|$)/);
  if (end > 0 && end <= maxLen) return t.slice(0, end + 1).trim();
  return truncate(t, maxLen);
}

function titleFromBody(s: string, max = 72): string {
  return truncate(firstSentence(s, max), max);
}

function normKind(v: unknown): PriorityKind | null {
  if (typeof v !== "string") return null;
  const k = v.trim().toLowerCase().replace(/\s+/g, "_");
  if (
    k === "risk" ||
    k === "opportunity" ||
    k === "inefficiency" ||
    k === "anomaly" ||
    k === "next_action" ||
    k === "nextaction"
  ) {
    if (k === "nextaction") return "next_action";
    return k;
  }
  if (k === "next" || k === "action" || k === "next_step" || k === "nextstep")
    return "next_action";
  return null;
}

function normPriority(v: unknown): PriorityLevel {
  if (v === "high" || v === "medium" || v === "low") return v;
  return "medium";
}

function parseOne(raw: unknown): TopPriorityItem | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const kind = normKind(o.kind ?? o.lens ?? o.focus);
  const title = typeof o.title === "string" ? o.title.trim() : "";
  const explanation =
    typeof o.explanation === "string"
      ? o.explanation.trim()
      : typeof o.detail === "string"
        ? o.detail.trim()
        : "";
  if (!kind || !title || !explanation) return null;
  return {
    kind,
    priority: normPriority(o.priority),
    title: truncate(title, 88),
    explanation: truncate(explanation, 240),
  };
}

/** Parse model-provided `top_priorities` array. */
export function parseTopPrioritiesFromApi(raw: unknown): TopPriorityItem[] {
  if (!Array.isArray(raw)) return [];
  return raw.map(parseOne).filter((x): x is TopPriorityItem => x != null);
}

function severityToPriority(
  s: "high" | "medium" | "low"
): PriorityLevel {
  return s;
}

type BriefAnomaly = { description: string; severity: "high" | "medium" | "low" };

export interface TopPrioritiesSource {
  executive_summary?: string;
  insights?: unknown[];
  anomalies?: BriefAnomaly[];
  recommendations?: string[];
  top_priorities?: unknown[];
}

function dedupeKey(item: TopPriorityItem): string {
  return `${item.kind}:${norm(item.title)}`;
}

function norm(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function mergeByKind(
  primary: TopPriorityItem[],
  filler: TopPriorityItem[]
): TopPriorityItem[] {
  const seenKind = new Set(primary.map((p) => p.kind));
  const seenText = new Set(primary.map(dedupeKey));
  const out = [...primary];
  for (const item of filler) {
    if (out.length >= 5) break;
    if (seenKind.has(item.kind)) continue;
    const k = dedupeKey(item);
    if (seenText.has(k)) continue;
    seenKind.add(item.kind);
    seenText.add(k);
    out.push(item);
  }
  return out.slice(0, 5);
}

function deriveFallback(src: TopPrioritiesSource): TopPriorityItem[] {
  const out: TopPriorityItem[] = [];
  const insights = sortInsightsForDisplay(
    normalizeInsightsList(src.insights ?? [])
  );
  const anomalies = Array.isArray(src.anomalies) ? src.anomalies : [];
  const recommendations = Array.isArray(src.recommendations)
    ? src.recommendations.filter((x): x is string => typeof x === "string")
    : [];
  const exec =
    typeof src.executive_summary === "string"
      ? src.executive_summary.trim()
      : "";

  const push = (item: TopPriorityItem) => {
    if (out.length >= 5) return;
    const key = dedupeKey(item);
    if (out.some((x) => dedupeKey(x) === key)) return;
    out.push(item);
  };

  const neg = insights.find((i) => i.type === "negative");
  if (neg) {
    push({
      kind: "risk",
      priority: "high",
      title: truncate(neg.headline || titleFromBody(neg.finding, 76), 88),
      explanation: firstSentence(neg.why_it_matters, 220) || truncate(neg.why_it_matters, 220),
    });
  }

  const pos = insights.find((i) => i.type === "positive");
  if (pos) {
    push({
      kind: "opportunity",
      priority: "high",
      title: truncate(pos.headline || titleFromBody(pos.finding, 76), 88),
      explanation:
        firstSentence(pos.why_it_matters, 220) || truncate(pos.why_it_matters, 220),
    });
  }

  const neutrals = insights.filter((i) => i.type === "neutral");
  const ineff =
    neutrals.find(
      (i) =>
        INEFF_PAT.test(i.finding) || INEFF_PAT.test(i.why_it_matters ?? "")
    ) ?? neutrals[0];
  if (ineff) {
    push({
      kind: "inefficiency",
      priority: "medium",
      title: truncate(ineff.headline || titleFromBody(ineff.finding, 76), 88),
      explanation:
        firstSentence(ineff.why_it_matters, 220) ||
        truncate(ineff.why_it_matters, 220),
    });
  }

  const topAnomaly = anomalies[0];
  if (topAnomaly?.description?.trim()) {
    push({
      kind: "anomaly",
      priority: severityToPriority(topAnomaly.severity),
      title: titleFromBody(topAnomaly.description, 64),
      explanation: firstSentence(topAnomaly.description, 220) || truncate(topAnomaly.description, 220),
    });
  }

  const rec = recommendations[0]?.trim();
  if (rec) {
    push({
      kind: "next_action",
      priority: "high",
      title: titleFromBody(rec, 56) || "Lead move",
      explanation: truncate(rec, 220),
    });
  } else {
    const withAction = insights.find((i) => i.recommended_action?.trim());
    const act = withAction?.recommended_action?.trim();
    if (act) {
      push({
        kind: "next_action",
        priority: "medium",
        title: titleFromBody(act, 56) || "Next move",
        explanation: truncate(act, 220),
      });
    }
  }

  if (out.length === 0 && exec) {
    push({
      kind: "next_action",
      priority: "high",
      title: "Open here",
      explanation: firstSentence(exec, 240) || truncate(exec, 240),
    });
  }

  return out.slice(0, 5);
}

/**
 * Prefer model `top_priorities` when it returns at least three rows; otherwise
 * merge with heuristics from insights, anomalies, and recommendations.
 */
export function buildTopPriorities(src: TopPrioritiesSource): TopPriorityItem[] {
  const parsed = parseTopPrioritiesFromApi(src.top_priorities);
  if (parsed.length >= 3) return parsed.slice(0, 5);
  const derived = deriveFallback(src);
  if (parsed.length === 0) return derived;
  return mergeByKind(parsed, derived);
}

export function lensLabel(kind: PriorityKind): string {
  switch (kind) {
    case "risk":
      return "Downside";
    case "opportunity":
      return "Upside";
    case "inefficiency":
      return "Spend or friction";
    case "anomaly":
      return "Data trust";
    case "next_action":
      return "Next step";
    default:
      return "Priority";
  }
}

export function lensAccentClass(kind: PriorityKind): string {
  switch (kind) {
    case "risk":
      return "bg-rose-500";
    case "opportunity":
      return "bg-emerald-500";
    case "inefficiency":
      return "bg-amber-500";
    case "anomaly":
      return "bg-violet-500";
    case "next_action":
      return "bg-slate-700 dark:bg-slate-300";
    default:
      return "bg-slate-400";
  }
}

export function priorityBadgeClass(p: PriorityLevel): string {
  switch (p) {
    case "high":
      return "border-rose-200/90 bg-rose-50/90 text-rose-800 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-200";
    case "medium":
      return "border-amber-200/90 bg-amber-50/80 text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/35 dark:text-amber-100";
    case "low":
      return "border-slate-200/90 bg-slate-50/90 text-slate-600 dark:border-slate-700 dark:bg-slate-900/50 dark:text-slate-300";
    default:
      return "";
  }
}
