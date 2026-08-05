"use client";

import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

export type ColumnRole =
  | "timeline"
  | "amount_inflow"
  | "amount_outflow"
  | "quantity"
  | "identifier"
  | "dimension"
  | "text"
  | "ignore";

export interface MappingColumn {
  name: string;
  role: string;
  date_format?: string | null;
  original_name?: string | null;
  meaning?: string | null;
}

export interface MappingSpec {
  version?: number;
  source?: string;
  primary_timeline?: string | null;
  primary_amount?: string | null;
  dayfirst?: boolean | null;
  drop_duplicates?: boolean;
  sheet?: string | null;
  header_row?: number;
  columns?: MappingColumn[];
  ingestion_profile?: {
    flags?: { kind: string; code: string; message: string }[];
    interpretations?: string[];
  } | null;
}

const ROLE_OPTIONS: { id: ColumnRole; label: string }[] = [
  { id: "timeline", label: "Timeline" },
  { id: "amount_inflow", label: "Amount (in)" },
  { id: "amount_outflow", label: "Amount (out)" },
  { id: "quantity", label: "Quantity" },
  { id: "identifier", label: "ID" },
  { id: "dimension", label: "Breakdown" },
  { id: "text", label: "Text" },
  { id: "ignore", label: "Ignore" },
];

function roleLabel(role: string) {
  return ROLE_OPTIONS.find((r) => r.id === role)?.label ?? role;
}

interface HowWeReadPanelProps {
  datasetId: string;
  mappingSpec: MappingSpec | null;
  allColumns: string[];
  sheets?: { name: string; score: number }[];
}

export function HowWeReadPanel({
  datasetId,
  mappingSpec,
  allColumns,
  sheets = [],
}: HowWeReadPanelProps) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [timeline, setTimeline] = useState(mappingSpec?.primary_timeline ?? "");
  const [amount, setAmount] = useState(mappingSpec?.primary_amount ?? "");
  const [dayfirst, setDayfirst] = useState<boolean | null>(
    mappingSpec?.dayfirst ?? null
  );
  const [dropDupes, setDropDupes] = useState(
    Boolean(mappingSpec?.drop_duplicates)
  );
  const [sheet, setSheet] = useState(mappingSpec?.sheet ?? "");
  const [roles, setRoles] = useState<Record<string, string>>(() => {
    const out: Record<string, string> = {};
    for (const c of mappingSpec?.columns || []) {
      out[c.name] = c.role;
    }
    return out;
  });

  const flags = mappingSpec?.ingestion_profile?.flags || [];
  const interpretations = mappingSpec?.ingestion_profile?.interpretations || [];
  const ambiguousDates = flags.some(
    (f) =>
      String(f.code || "").includes("ambiguous_date") ||
      String(f.message || f.label || "")
        .toLowerCase()
        .includes("ambiguous")
  );
  const needsPrimaryConfirm = !timeline || !amount;
  const columns: MappingColumn[] = useMemo(
    () =>
      mappingSpec?.columns ||
      allColumns.map((name) => ({ name, role: "text" as const })),
    [mappingSpec, allColumns]
  );

  const saveMutation = useMutation({
    mutationFn: () =>
      api.patchDataset(datasetId, {
        primary_date_column: timeline || null,
        primary_amount_column: amount || null,
        dayfirst: dayfirst,
        drop_duplicates: dropDupes,
        sheet: sheet || null,
        column_roles: roles,
      }),
    onSuccess: () => {
      toast.success("Mapping updated — charts will use the new roles");
      setEditing(false);
      void queryClient.invalidateQueries({ queryKey: ["dataset", datasetId] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard", datasetId] });
      void queryClient.invalidateQueries({ queryKey: ["overview"] });
    },
    onError: (err: Error) => {
      toast.error(err.message || "Could not update mapping");
    },
  });

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
        <div>
          <CardTitle className="text-base">How we read this file</CardTitle>
          <p className="text-xs text-muted-foreground mt-1">
            Roles come from evidence-based profiling
            {mappingSpec?.source ? ` (${mappingSpec.source})` : ""}. You can
            change them anytime — the cleaned data is re-derived from your
            original file.
          </p>
        </div>
        {!editing ? (
          <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
            Edit mapping
          </Button>
        ) : (
          <div className="flex gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setEditing(false)}
              disabled={saveMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending || needsPrimaryConfirm}
              title={
                needsPrimaryConfirm
                  ? "Choose a primary timeline and amount before saving"
                  : undefined
              }
            >
              {saveMutation.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {ambiguousDates && (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm">
            Some dates are ambiguous (day and month could be swapped). Confirm whether
            this file uses DD/MM or MM/DD before trusting charts.
            {!editing ? (
              <button
                type="button"
                className="ml-2 underline underline-offset-2"
                onClick={() => setEditing(true)}
              >
                Set date order
              </button>
            ) : null}
          </div>
        )}
        {needsPrimaryConfirm && (
          <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
            Confirm the primary timeline and amount columns so dashboards and briefings
            use the right fields.
            {!editing ? (
              <button
                type="button"
                className="ml-2 text-foreground underline underline-offset-2"
                onClick={() => setEditing(true)}
              >
                Confirm now
              </button>
            ) : null}
          </div>
        )}
        {interpretations.length > 0 && (
          <ul className="text-sm text-muted-foreground space-y-1">
            {interpretations.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        )}

        {flags.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Quality notes
            </p>
            {flags.map((f, i) => (
              <div
                key={`${f.code}-${i}`}
                className={`text-sm rounded-md border px-3 py-2 ${
                  f.kind === "warning"
                    ? "border-amber-500/40 bg-amber-500/5 text-amber-900 dark:text-amber-100"
                    : "border-border bg-muted/40 text-muted-foreground"
                }`}
              >
                {f.message}
              </div>
            ))}
          </div>
        )}

        {editing ? (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="text-sm space-y-1">
                <span className="text-muted-foreground">Timeline column</span>
                <select
                  className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
                  value={timeline}
                  onChange={(e) => setTimeline(e.target.value)}
                >
                  <option value="">Not set</option>
                  {allColumns.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-sm space-y-1">
                <span className="text-muted-foreground">Primary amount</span>
                <select
                  className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                >
                  <option value="">Not set</option>
                  {allColumns.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="flex flex-wrap gap-4 text-sm">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={dayfirst === true}
                  onChange={(e) => setDayfirst(e.target.checked ? true : false)}
                />
                Prefer DD/MM dates when ambiguous
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={dropDupes}
                  onChange={(e) => setDropDupes(e.target.checked)}
                />
                Remove duplicate rows
              </label>
            </div>

            {sheets.length > 1 && (
              <label className="text-sm space-y-1 block">
                <span className="text-muted-foreground">Worksheet</span>
                <select
                  className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
                  value={sheet}
                  onChange={(e) => setSheet(e.target.value)}
                >
                  <option value="">Auto (best table)</option>
                  {sheets.map((s) => (
                    <option key={s.name} value={s.name}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </label>
            )}

            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Column roles
              </p>
              <div className="max-h-64 overflow-y-auto space-y-2">
                {columns.map((c) => (
                  <div
                    key={c.name}
                    className="flex items-center justify-between gap-2 text-sm"
                  >
                    <span className="font-mono text-xs truncate" title={c.name}>
                      {c.original_name || c.name}
                    </span>
                    <select
                      className="rounded-md border bg-background px-2 py-1 text-xs"
                      value={roles[c.name] || c.role}
                      onChange={(e) =>
                        setRoles((prev) => ({
                          ...prev,
                          [c.name]: e.target.value,
                        }))
                      }
                    >
                      {ROLE_OPTIONS.map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.label}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {columns.map((c) => (
              <Badge
                key={c.name}
                variant="outline"
                className="font-mono text-xs"
              >
                {c.name}{" "}
                <span className="ml-1 text-muted-foreground">
                  {roleLabel(c.role)}
                </span>
              </Badge>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
