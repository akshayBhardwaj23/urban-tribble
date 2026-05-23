"use client";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { KpiDetailsSheet } from "@/components/dashboard/kpi-details-sheet";
import type { KpiDrillDownDetails } from "@/lib/kpi-drill-down";

export function DashboardKpiTile({
  title,
  value,
  subtitle,
  details,
}: {
  title: string;
  value: string;
  subtitle?: string;
  details?: KpiDrillDownDetails | null;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {title}
        </p>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-semibold tabular-nums">{value}</p>
        {subtitle ? (
          <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p>
        ) : null}
        {details ? (
          <div className="mt-3 border-t pt-2">
            <KpiDetailsSheet details={details} metricLabel={title} />
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
