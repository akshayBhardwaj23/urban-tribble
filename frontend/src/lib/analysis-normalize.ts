/** Normalize AI analysis insights (legacy title/description or structured finding fields). */

import { INSIGHT_WHY_MATTERS_FALLBACK } from "@/lib/analysis-fallback-copy";
import type { InsightTraceSlice } from "@/lib/traceability";

export type InsightPolarity = "positive" | "negative" | "neutral";

export type ConfidenceBand = "high" | "medium" | "low" | "unknown";

export interface NormalizedInsight {
  /** Operator-brief title (4–9 words); from API or derived from finding */
  headline: string;
  finding: string;
  why_it_matters: string;
  likely_cause: string | null;
  recommended_action: string | null;
  /** Raw model line, if any */
  confidence: string | null;
  /** Parsed band for UI; `unknown` when not stated */
  confidence_level: ConfidenceBand;
  /** Text after High/Medium/Low prefix, or full line if unparseable */
  confidence_rationale: string | null;
  /** Data-quality notes (missing fields, duplicates, attribution, etc.) */
  caveats: string[];
  source_reference: string | null;
  type: InsightPolarity;
  /** Optional model/UI provenance for verification dialogs */
  trace: InsightTraceSlice | null;
}

function str(v: unknown): string {
  return typeof v === "string" ? v.trim() : "";
}

function polarity(v: unknown): InsightPolarity {
  if (v === "positive" || v === "negative" || v === "neutral") return v;
  return "neutral";
}

function strList(v: unknown): string[] | undefined {
  if (!Array.isArray(v)) return undefined;
  const xs = v.filter(
    (x): x is string => typeof x === "string" && x.trim().length > 0
  );
  return xs.length ? xs : undefined;
}

function uniqueCaveats(items: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of items) {
    const t = raw.trim();
    if (t.length < 2) continue;
    const key = t.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(t);
  }
  return out;
}

const WEAK_HEADLINE_RE =
  /^(data|dataset|the data|this data|analysis|insight|observation|summary|trend|business observation|marketing insight|revenue analysis|customer spending)/i;

/** First sentence or trimmed segment for fallback headline (no API headline). */
function firstSentenceOrTrim(s: string, maxLen: number): string {
  const t = s.trim();
  const end = t.search(/[.!?](?=\s|$)/);
  if (end >= 14 && end < maxLen + 24) {
    return t.slice(0, end + 1).trim();
  }
  if (t.length <= maxLen) return t;
  const cut = t.slice(0, maxLen - 1);
  const sp = cut.lastIndexOf(" ");
  return `${sp > 35 ? cut.slice(0, sp) : cut}…`;
}

function deriveInsightHeadline(
  finding: string,
  type: InsightPolarity,
  hasCaveats: boolean
): string {
  const stripped = finding
    .replace(/^(the |this |this pass |this briefing |the api |the extract )/i, "")
    .trim();
  let candidate = firstSentenceOrTrim(stripped, 88);
  candidate = candidate.replace(/\.$/, "").trim();
  if (candidate.length < 12 || WEAK_HEADLINE_RE.test(candidate)) {
    if (type === "negative" && hasCaveats) return "Data quality limiting conviction";
    if (type === "negative") return "Commercial downside flagged";
    if (type === "positive") return "Upside worth validating";
    return "Operating signal to review";
  }
  if (!/^[A-Z]/.test(candidate)) {
    candidate = candidate.charAt(0).toUpperCase() + candidate.slice(1);
  }
  return candidate;
}

/** Text under headline when it does not duplicate the full finding. */
export function insightContextLine(headline: string, finding: string): string | null {
  const f = finding.trim();
  const h = headline.replace(/…\s*$/, "").trim();
  if (!f) return null;
  if (f === headline) return null;
  const fl = f.toLowerCase();
  const hl = h.toLowerCase();
  if (fl.startsWith(hl)) {
    const rest = f.slice(h.length).replace(/^[.\s—:,-]+/, "").trim();
    return rest.length >= 12 ? rest : null;
  }
  return f;
}

/** Parse High/Medium/Low from explicit field or leading words of `confidence`. */
export function parseConfidenceBand(
  confidenceRaw: string | null,
  explicit: unknown
): ConfidenceBand {
  if (explicit === "high" || explicit === "medium" || explicit === "low") {
    return explicit;
  }
  if (typeof explicit === "string") {
    const e = explicit.trim().toLowerCase();
    if (e === "high" || e === "medium" || e === "low") return e;
  }
  if (!confidenceRaw) return "unknown";
  const t = confidenceRaw.trim();
  const m = t.match(/^(high|medium|low)\b/i);
  if (m) return m[1].toLowerCase() as ConfidenceBand;
  return "unknown";
}

/** Strip leading band label from confidence string for rationale display. */
export function splitConfidenceRationale(
  confidenceRaw: string | null,
  level: ConfidenceBand
): string | null {
  if (!confidenceRaw?.trim()) return null;
  if (level === "unknown") return confidenceRaw.trim();
  let t = confidenceRaw.trim();
  t = t
    .replace(
      new RegExp(`^${level}\\b\\s*[—\\-\\:\\.]?\\s*`, "i"),
      ""
    )
    .trim();
  return t.length ? t : null;
}

export function parseInsightTraceSlice(raw: unknown): InsightTraceSlice | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const fileName = str(o.file_name || o.fileName);
  const sheetName = str(o.sheet_name || o.sheetName) || undefined;
  const dateRange = str(o.date_range || o.dateRange) || undefined;
  const rowCount =
    typeof o.row_count === "number"
      ? o.row_count
      : typeof o.rowCount === "number"
        ? o.rowCount
        : undefined;
  const columnsUsed =
    strList(o.columns_used) ?? strList(o.columnsUsed) ?? strList(o.columns);
  const caveatsRaw = strList(o.caveats) ?? strList(o.data_quality_notes);
  const caveats = caveatsRaw?.map((c) => c.trim()).filter(Boolean);

  if (
    !fileName &&
    !sheetName &&
    !dateRange &&
    rowCount === undefined &&
    !columnsUsed?.length &&
    !caveats?.length
  ) {
    return null;
  }

  return {
    fileName: fileName || undefined,
    sheetName,
    dateRange,
    rowCount,
    columnsUsed,
    caveats,
  };
}

/**
 * Maps API insight objects into a fixed analyst template. Supports legacy
 * `{ title, description, type }` and structured `{ finding, why_it_matters, ... }`.
 */
export function normalizeInsight(raw: unknown): NormalizedInsight | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;

  const finding = str(o.finding) || str(o.title);
  const why = str(o.why_it_matters) || str(o.description);
  if (!finding && !why) return null;

  const finalFinding =
    finding || (why.length > 100 ? `${why.slice(0, 97)}…` : why);
  const finalWhy = why || INSIGHT_WHY_MATTERS_FALLBACK;

  const rawHeadline = str(
    o.headline || o.card_title || o.operator_title || o.brief_title
  );
  const likely = str(o.likely_cause) || null;
  const action = str(o.recommended_action) || null;
  const confidence = str(o.confidence) || null;
  const sourceRef = str(o.source_reference) || null;
  const trace = parseInsightTraceSlice(o.trace);

  const confidence_level = parseConfidenceBand(
    confidence,
    o.confidence_level ?? o.confidence_band
  );
  const confidence_rationale = splitConfidenceRationale(
    confidence,
    confidence_level
  );

  const caveatParts: string[] = [
    ...(strList(o.caveats) ?? []),
    ...(strList(o.data_quality_caveats) ?? []),
    ...(strList(o.reliability_notes) ?? []),
  ];
  const singleNote = str(o.data_quality_note || o.attribution_note);
  if (singleNote) caveatParts.push(singleNote);
  if (trace?.caveats?.length) caveatParts.push(...trace.caveats);
  const caveats = uniqueCaveats(caveatParts);

  const headline =
    rawHeadline ||
    deriveInsightHeadline(finalFinding, polarity(o.type), caveats.length > 0);

  return {
    headline,
    finding: finalFinding,
    why_it_matters: finalWhy,
    likely_cause: likely,
    recommended_action: action,
    confidence,
    confidence_level,
    confidence_rationale,
    caveats,
    source_reference: sourceRef,
    type: polarity(o.type),
    trace,
  };
}

export function normalizeInsightsList(raw: unknown): NormalizedInsight[] {
  if (!Array.isArray(raw)) return [];
  return raw.map(normalizeInsight).filter((x): x is NormalizedInsight => x != null);
}

/** Sort: risks first, then context, then upside. */
export function sortInsightsForDisplay(
  insights: NormalizedInsight[]
): NormalizedInsight[] {
  const rank = (t: InsightPolarity) =>
    t === "negative" ? 0 : t === "neutral" ? 1 : 2;
  return [...insights].sort((a, b) => rank(a.type) - rank(b.type));
}
