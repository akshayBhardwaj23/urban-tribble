/**
 * Fallback copy when model output is thin or fields are missing.
 * Voice: calm operator briefing—plain English, honest limits, no empty praise.
 */

/** recommended_action missing */
export const INSIGHT_PAY_ATTENTION_FALLBACK =
  "No specific next step came back for this item—check it against source rows before you change targets or budget.";

/** why_it_matters missing (finding present) */
export const INSIGHT_WHY_MATTERS_FALLBACK =
  "The extract may be too thin to tie this to revenue, margin, or risk—add cost, channel, cohort, or segment fields and run the briefing again.";

/** confidence unknown */
export const INSIGHT_UNGRADED_CONFIDENCE =
  "Conviction was not graded—treat this line as directional until you tie it to underlying rows.";

/** source_reference missing */
export const INSIGHT_SOURCE_FALLBACK =
  "Only aggregate summary was available—slice by row or segment may change the read.";

/** Trace / merge base (rare) */
export const TRACE_SCOPE_FALLBACK_NOTE =
  "Scope is thin—confirm file, columns, and period before you lean on this line.";

/** Workspace overview — no analysis run yet */
export const WORKSPACE_NO_BRIEFING_YET =
  "Run a workspace briefing to roll your sources into what moved, what it may mean for margin or growth, and what to verify next.";

/** Dataset tab — no analysis yet */
export const DATASET_ANALYSIS_EMPTY_INVITE =
  "Run a briefing on this source for tradeoffs on revenue, cost, and risk—with a clear next check—instead of a generic tour of columns.";

/** At-a-glance tiles when analysis exists but slot is empty */
export const WORKSPACE_BRIEFING_EMPTY_TILES = {
  keyChange:
    "Nothing stood out as a single big shift this run—change may be incremental; still scan the series behind your plan.",
  risk:
    "No major downside surfaced here—that does not clear operating risk; stress-test the assumptions behind your largest bets.",
  upside:
    "No upside was highlighted—either a quiet period or thin signal; re-run after material new data.",
} as const;

export function workspaceRunBriefingInvite(totalDatasets: number): string {
  const pl = totalDatasets !== 1 ? "s" : "";
  return `Run a workspace briefing for one read across ${totalDatasets} source${pl}: what changed, what it may mean for margin or growth, and what to verify next.`;
}

export const WORKSPACE_OPERATOR_READ_BUSY = {
  whatMoved: "Pulling together what moved across your sources…",
  soWhat: "Ordering margin, concentration, and spend implications…",
  leadMove: "Choosing the move that clears the most uncertainty…",
} as const;

export const WORKSPACE_OPERATOR_READ_EMPTY = {
  soWhat:
    "Margin, concentration, and cost tradeoffs show up here after a briefing ties summaries to decisions—not before.",
  leadMove:
    "The briefing should name one move to own first; run it so this reflects a deliberate choice, not guesswork.",
} as const;
