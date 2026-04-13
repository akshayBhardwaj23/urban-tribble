import type { PlanLimitDetail, WorkspaceUsage } from "@/lib/api";

/** Synthetic plan_limit payload for UI when overview usage shows analyses at cap (no new API call). */
export function analysesLimitDetailFromUsage(
  usage: WorkspaceUsage | undefined
): PlanLimitDetail | null {
  const m = usage?.meters.analyses;
  if (!usage || !m?.at_limit) return null;
  const msg =
    usage.nudges.find((n) => /analys/i.test(n.message))?.message ??
    `You've used all analyses allowed on your plan for ${usage.meter_period_label} (${m.used}/${m.limit}). Upgrade to run more briefings.`;
  return {
    code: "plan_limit",
    plan: usage.plan_id,
    limit: "analyses",
    message: msg,
  };
}
