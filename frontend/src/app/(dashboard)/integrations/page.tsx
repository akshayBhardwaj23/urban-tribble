"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type IntegrationProvider } from "@/lib/api";
import { INTEGRATIONS_COMING_SOON } from "@/lib/integrations-flags";

const TIER_LABELS: Record<number, string> = {
  1: "Tier 1 — Must-have",
  2: "Tier 2 — Growth",
  3: "Tier 3 — Enterprise",
};

export default function IntegrationsPage() {
  const catalogQuery = useQuery({
    queryKey: ["integration-catalog"],
    queryFn: () => api.getIntegrationCatalog(),
  });

  const providersByTier = useMemo(() => {
    const providers = catalogQuery.data?.providers ?? [];
    const tiers: Record<number, IntegrationProvider[]> = { 1: [], 2: [], 3: [] };
    for (const p of providers) {
      tiers[p.tier]?.push(p);
    }
    return tiers;
  }, [catalogQuery.data]);

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">Integrations</h1>
            {INTEGRATIONS_COMING_SOON ? (
              <Badge variant="secondary">Coming soon</Badge>
            ) : null}
          </div>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Live connections to Sheets, Excel / OneDrive, CRMs, ads, and more are on the way.
            For now, import CSV or Excel files — dashboards and chat work from those sources.
          </p>
        </div>
        <Link
          href="/upload"
          className="inline-flex h-9 shrink-0 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          Import a file
        </Link>
      </div>

      <Card className="border-dashed">
        <CardContent className="space-y-2 py-6">
          <p className="text-sm font-medium">What you can do today</p>
          <p className="text-sm text-muted-foreground">
            Upload spreadsheets from Import, then use Sources, Overview, and Chat. When
            integrations ship, you will connect once and refresh on a schedule without
            re-uploading.
          </p>
        </CardContent>
      </Card>

      {([1, 2, 3] as const).map((tier) => (
        <section key={tier} className="space-y-3">
          <h2 className="text-lg font-medium">{TIER_LABELS[tier]}</h2>
          {catalogQuery.isLoading ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-28" />
              ))}
            </div>
          ) : catalogQuery.isError ? (
            <p className="text-sm text-muted-foreground">
              Provider list unavailable right now. Check back when integrations launch.
            </p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {(providersByTier[tier] ?? []).map((provider) => (
                <Card key={provider.id} className="flex flex-col opacity-90">
                  <CardHeader className="pb-2">
                    <div className="flex items-start justify-between gap-2">
                      <CardTitle className="text-base">{provider.name}</CardTitle>
                      <Badge variant="outline" className="shrink-0 text-[10px]">
                        {provider.category}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="flex flex-1 flex-col gap-3 pt-0">
                    <p className="flex-1 text-sm text-muted-foreground">
                      {provider.description}
                    </p>
                    <button
                      type="button"
                      disabled
                      className="inline-flex h-8 w-fit items-center justify-center rounded-md border px-3 text-sm text-muted-foreground opacity-70"
                    >
                      Coming soon
                    </button>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </section>
      ))}
    </div>
  );
}
