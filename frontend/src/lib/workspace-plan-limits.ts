/** Mirrors backend `workspaces_max_for` in `subscription_usage.py`. */
const WORKSPACES_MAX: Record<string, number> = {
  free: 1,
  starter: 1,
  pro: 5,
  internal: 50,
};

export function maxWorkspacesForPlan(plan: string | undefined | null): number {
  const p = (plan ?? "free").toLowerCase();
  return WORKSPACES_MAX[p] ?? 1;
}
