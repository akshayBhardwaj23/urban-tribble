import type { IngestionProfile } from "@/lib/ingestion";
import { formatUserFacingApiError, sanitizeApiErrorMessage } from "@/lib/api-errors";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Stored executive digest (weekly / monthly); HTML snapshot reserved for future email. */
export type RecurringSummaryContent = {
  headline: string;
  key_changes: string[];
  biggest_risk: string;
  biggest_opportunity: string;
  recommended_actions: string[];
  meta?: {
    period_kind?: string;
    period_label?: string;
    what_changed_available?: boolean;
    generated_at?: string;
  };
};

/** Actionable workspace alert (thresholds, data scans, briefing). */
export type WorkspaceAlert = {
  id: string;
  title: string;
  detail: string;
  category: "risk" | "opportunity" | "data_issue" | "efficiency";
  priority: "high" | "medium" | "low";
  source: "signal" | "briefing" | "data_quality";
};

/** Prioritized operator move from briefing + signals (overview API). */
export type WorkspaceRecommendedAction = {
  id: string;
  action: string;
  priority: "high" | "medium" | "low";
  source: string;
};

/** Retention / rhythm copy for the overview (last activity, when to check again). */
export type WorkspaceUsageMeterDetail = {
  used: number;
  limit: number;
  remaining: number;
  pct: number;
  approaching: boolean;
  at_limit: boolean;
};

export type WorkspaceUsageNudge = {
  tone: string;
  message: string;
  href: string;
};

/** Plan + meters (Free = lifetime uploads/analyses; paid = per calendar month). */
export type WorkspaceUsage = {
  plan_id: string;
  plan_label: string;
  /** e.g. "this month" or "lifetime (Free)" */
  meter_period_label: string;
  period_start: string;
  period_end: string;
  limits: {
    analyses_cap: number | null;
    uploads_cap: number | null;
    history_periods: number;
    chat_messages_cap: number;
  };
  usage: {
    analyses_count: number;
    uploads_count: number;
    timeline_snapshots: number;
    chat_user_messages: number;
  };
  history: {
    periods_cap: number;
    snapshots_recorded: number;
    periods_highlighted: number;
    summary: string;
  };
  meters: {
    analyses: WorkspaceUsageMeterDetail | null;
    uploads: WorkspaceUsageMeterDetail | null;
    chat: WorkspaceUsageMeterDetail | null;
  };
  nudges: WorkspaceUsageNudge[];
};

export type PlanFeatures = {
  timeline: boolean;
  what_changed: boolean;
  alerts: boolean;
  weekly_summary: boolean;
  monthly_summary: boolean;
  full_briefing: boolean;
};

export type PlanLimitDetail = {
  code: "plan_limit";
  plan: string;
  limit: string;
  message: string;
};

export class ApiPlanLimitError extends Error {
  constructor(
    public readonly detail: PlanLimitDetail,
    message?: string
  ) {
    super(message ?? detail.message);
    this.name = "ApiPlanLimitError";
  }
}

export function isApiPlanLimitError(e: unknown): e is ApiPlanLimitError {
  return e instanceof ApiPlanLimitError;
}

/** Parse FastAPI 403 `plan_limit` from a `fetch` response body (non-`request()` calls). */
export function planLimitErrorFromJson(
  status: number,
  body: { detail?: unknown }
): ApiPlanLimitError | null {
  const detail = body?.detail;
  if (
    status === 403 &&
    detail &&
    typeof detail === "object" &&
    !Array.isArray(detail) &&
    (detail as PlanLimitDetail).code === "plan_limit"
  ) {
    const pl = detail as PlanLimitDetail;
    return new ApiPlanLimitError(pl, pl.message);
  }
  return null;
}

export type WorkspaceHabitHints = {
  last_activity_at: string | null;
  last_briefing_at: string | null;
  last_data_change_at: string | null;
  days_since_activity: number | null;
  days_since_briefing: number | null;
  days_since_data_change: number | null;
  next_check_suggestion: string;
  briefing_cta_context: string;
  activity_nudge: string | null;
  gentle_nudge: string | null;
};

/** Point-in-time workspace snapshot (import, briefing, append). */
export type WorkspaceTimelineEvent = {
  id: string;
  event_type: string;
  ref_id: string | null;
  dataset_id: string | null;
  display_label: string;
  metrics: {
    workspace_row_total: number;
    dataset_count: number;
    kpis: { label: string; value: number; dataset_name?: string }[];
    snapshot_quality?: string;
    focus_dataset?: string;
  };
  themes: {
    insight_headlines?: string[];
    priority_titles?: string[];
    executive_snippet?: string;
    buckets?: string[];
  } | null;
  created_at: string | null;
};

export type WorkspaceDigestStub = {
  id: string;
  kind: string;
  period_label: string;
  headline: string;
  created_at: string | null;
};

export type WorkspaceCompareResult = {
  from_snapshot_id: string | undefined;
  to_snapshot_id: string | undefined;
  from_label: string | undefined;
  to_label: string | undefined;
  workspace_row_delta: number;
  workspace_row_previous: number;
  workspace_row_current: number;
  kpi_changes: {
    label: string;
    dataset_name?: string;
    previous_value: number;
    current_value: number;
    delta_pct: number;
    direction: string;
  }[];
};

export type RecurringSummaryRecord = {
  id: string;
  workspace_id: string;
  kind: string;
  period_start: string;
  period_end: string;
  period_label: string;
  content: RecurringSummaryContent;
  email_ready: boolean;
  email_sent_at: string | null;
  email_scheduled: string | null;
  created_at: string | null;
  updated_at: string | null;
};

let _userEmail: string | null = null;

export function setApiUserEmail(email: string | null) {
  _userEmail = email;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    ...(options?.headers as Record<string, string>),
  };

  if (_userEmail) {
    headers["X-User-Email"] = _userEmail;
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
    });
  } catch (e) {
    throw new Error(formatUserFacingApiError(e));
  }

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = error.detail;
    if (
      res.status === 403 &&
      detail &&
      typeof detail === "object" &&
      !Array.isArray(detail) &&
      (detail as PlanLimitDetail).code === "plan_limit"
    ) {
      const pl = detail as PlanLimitDetail;
      throw new ApiPlanLimitError(pl, pl.message);
    }
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail
              .map((d: { msg?: string; loc?: unknown }) =>
                typeof d === "string" ? d : d?.msg ?? JSON.stringify(d)
              )
              .join("; ")
          : detail != null
            ? String(detail)
            : res.statusText;
    throw new Error(sanitizeApiErrorMessage(message || "Request failed"));
  }

  return res.json();
}

export const api = {
  health: () => request<{ status: string }>("/health"),

  getAuthMe: () =>
    request<{
      id: string;
      email: string;
      name: string | null;
      image: string | null;
      active_workspace_id: string | null;
      subscription_plan?: string;
      subscription_renews_at?: string | null;
      workspaces: { id: string; name: string; created_at: string }[];
    }>("/api/auth/me"),

  deleteAuthAccount: () =>
    request<{ ok: boolean; deleted: boolean }>("/api/auth/me", {
      method: "DELETE",
    }),

  deleteWorkspace: (workspaceId: string) =>
    request<{
      ok: boolean;
      deleted: boolean;
      active_workspace_id: string | null;
    }>(`/api/workspaces/${workspaceId}`, { method: "DELETE" }),

  uploadFile: (file: File, description: string) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("description", description);
    return request<{
      id: string;
      filename: string;
      file_type: string;
      status: string;
      dataset_id: string;
      row_count: number;
      column_count: number;
      cleaning_report: {
        steps: string[];
        original_shape: number[];
        cleaned_shape: number[];
      };
      ingestion: IngestionProfile;
      all_columns: string[];
    }>("/api/uploads", { method: "POST", body: formData });
  },

  patchDataset: (
    datasetId: string,
    body: {
      business_classification?: string;
      primary_date_column?: string | null;
      primary_amount_column?: string | null;
      segment_columns?: string[];
    }
  ) =>
    request<{
      id: string;
      business_classification: string | null;
      business_classification_label: string;
      schema_updated?: boolean;
    }>(`/api/datasets/${datasetId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  getUpload: (id: string) =>
    request<{
      id: string;
      filename: string;
      status: string;
      user_description: string | null;
      created_at: string;
    }>(`/api/uploads/${id}`),

  listDatasets: () =>
    request<
      {
        id: string;
        upload_id: string;
        name: string;
        row_count: number | null;
        column_count: number | null;
        status: string;
        user_description: string | null;
        business_classification: string | null;
        created_at: string;
        integration_id: string | null;
        dashboard_plan_locked: boolean;
        integration: {
          id: string;
          provider: string;
          name: string;
          status: string;
          refresh_interval_hours: number;
          last_sync_at: string | null;
          next_sync_at: string | null;
        } | null;
      }[]
    >("/api/datasets"),

  getDataset: (id: string) =>
    request<{
      id: string;
      upload_id: string;
      name: string;
      schema_json: {
        date_columns: string[];
        revenue_columns: string[];
        category_columns: string[];
        numeric_columns: string[];
        text_columns: string[];
      } | null;
      data_summary: Record<string, unknown> | null;
      cleaned_report: { steps: string[]; original_shape: number[]; cleaned_shape: number[] } | null;
      business_classification: string | null;
      created_at: string;
      integration_id: string | null;
      dashboard_plan_locked: boolean;
      integration: {
        id: string;
        provider: string;
        name: string;
        status: string;
        refresh_interval_hours: number;
        last_sync_at: string | null;
        next_sync_at: string | null;
        auto_analyze: boolean;
      } | null;
    }>(`/api/datasets/${id}`),

  getDatasetPreview: (id: string, n?: number) =>
    request<{
      columns: string[];
      rows: Record<string, unknown>[];
      total_rows: number;
      total_columns: number;
    }>(`/api/datasets/${id}/preview${n ? `?n=${n}` : ""}`),

  runAnalysis: (datasetId: string) =>
    request<{
      id: string;
      dataset_id: string;
      type: string;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      result_json: any;
      ai_summary: string | null;
      created_at: string;
    }>("/api/analysis/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dataset_id: datasetId }),
    }),

  getAnalysisByDataset: (datasetId: string) =>
    request<{
      id: string;
      dataset_id: string;
      type: string;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      result_json: any;
      ai_summary: string | null;
      created_at: string;
    } | null>(`/api/analysis/dataset/${datasetId}`),

  getDashboardData: (
    datasetId: string,
    range?: { start?: string; end?: string; lastNDays?: number }
  ) => {
    const q = new URLSearchParams();
    if (range?.lastNDays != null) {
      q.set("last_n_days", String(range.lastNDays));
    } else {
      if (range?.start) q.set("start_date", range.start);
      if (range?.end) q.set("end_date", range.end);
    }
    const qs = q.toString();
    return request<{
      dataset_id: string;
      dataset_brief: string | null;
      dashboard_plan_source?: string | null;
      kpis: {
        id: string;
        title: string;
        value: number;
        formatted: string;
        subtitle?: string | null;
        column?: string;
        aggregation?: string;
        details?: Record<string, unknown>;
      }[];
      filtered_row_count?: number;
      charts: {
        id: string;
        title: string;
        type: "line" | "bar" | "pie" | "area";
        data: Record<string, unknown>[];
        x_label?: string;
        y_label?: string;
      }[];
      daily_aggregates: {
        date: string;
        revenue: number;
        orders: number;
        aov: number;
      }[];
      timeframe?: {
        applied: boolean;
        start: string | null;
        end: string | null;
        date_column: string | null;
      };
      /** Min/max calendar dates in the primary date column (full file, for preset anchors). */
      date_bounds?: { min: string | null; max: string | null };
      period_comparison?: {
        available: boolean;
        description?: string;
        current?: { start: string; end: string } | null;
        previous?: { start: string; end: string } | null;
      };
      what_changed: {
        available: boolean;
        period_description: string;
        items: {
          label: string;
          direction: string;
          arrow: string;
          delta_pct: number | null;
          previous_value: number;
          current_value: number;
          explanation: string;
          higher_is_better?: boolean;
          is_favorable?: boolean;
          source_dataset?: string;
        }[];
        highlights: {
          label: string;
          direction: string;
          arrow: string;
          delta_pct: number | null;
          previous_value: number;
          current_value: number;
          explanation: string;
          higher_is_better?: boolean;
          is_favorable?: boolean;
          source_dataset?: string;
        }[];
        cross_metric_note?: string | null;
      };
    }>(`/api/dashboards/dataset/${datasetId}${qs ? `?${qs}` : ""}`);
  },

  chat: (datasetId: string, question: string) =>
    request<{ answer: string; chart_data?: Record<string, unknown> }>(
      "/api/chat",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dataset_id: datasetId, question }),
      }
    ),

  getChatHistory: (datasetId: string, opts?: { workspace?: boolean }) => {
    const q = opts?.workspace ? "?workspace=true" : "";
    return request<
      { id: string; role: string; content: string; created_at: string }[]
    >(`/api/chat/history/${datasetId}${q}`);
  },

  chatWorkspace: (question: string) =>
    request<{ answer: string; chart_data?: Record<string, unknown> }>(
      "/api/chat/workspace",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      }
    ),

  deleteDataset: (id: string) =>
    request<{ status: string; dataset_id: string }>(`/api/datasets/${id}`, {
      method: "DELETE",
    }),

  appendToDataset: (datasetId: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return request<{
      dataset_id: string;
      row_count: number;
      column_count: number;
      cleaning_report: { steps: string[]; original_shape: number[]; cleaned_shape: number[] };
    }>(`/api/datasets/${datasetId}/append`, {
      method: "POST",
      body: formData,
    });
  },

  getOverview: () =>
    request<{
      total_datasets: number;
      total_rows: number;
      kpis: { label: string; value: number; dataset_name: string }[];
      charts: {
        id: string;
        title: string;
        type: "line" | "bar" | "pie" | "area";
        data: Record<string, unknown>[];
        x_label?: string;
        y_label?: string;
        dataset_name?: string;
        period_comparison?: {
          available: boolean;
          description?: string;
          current?: { start: string; end: string } | null;
          previous?: { start: string; end: string } | null;
        };
      }[];
      datasets: {
        id: string;
        name: string;
        row_count: number | null;
        column_count: number | null;
        created_at: string;
        date_columns: string[];
        value_columns: string[];
      }[];
      what_changed: {
        available: boolean;
        period_description: string;
        items: {
          label: string;
          direction: string;
          arrow: string;
          delta_pct: number | null;
          previous_value: number;
          current_value: number;
          explanation: string;
          higher_is_better?: boolean;
          is_favorable?: boolean;
          source_dataset?: string;
        }[];
        highlights: {
          label: string;
          direction: string;
          arrow: string;
          delta_pct: number | null;
          previous_value: number;
          current_value: number;
          explanation: string;
          higher_is_better?: boolean;
          is_favorable?: boolean;
          source_dataset?: string;
        }[];
        cross_metric_note?: string | null;
      };
      alerts: WorkspaceAlert[];
      recommended_actions: WorkspaceRecommendedAction[];
      habit_hints: WorkspaceHabitHints;
      usage: WorkspaceUsage;
      plan_features?: PlanFeatures;
    }>("/api/dashboards/overview"),

  patchWorkspaceOutlookForecast: (
    workspaceId: string,
    body: {
      dataset_id?: string | null;
      date_column?: string | null;
      value_column?: string | null;
    }
  ) =>
    request<{
      ok: boolean;
      outlook_forecast_dataset_id: string | null;
      outlook_forecast_date_column: string | null;
      outlook_forecast_value_column: string | null;
    }>(`/api/workspaces/${workspaceId}/outlook-forecast`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  runOverviewAnalysis: () =>
    request<{
      id: string;
      type: string;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      result_json: any;
      ai_summary: string | null;
      created_at: string;
    }>("/api/analysis/overview/run", { method: "POST" }),

  getOverviewAnalysis: () =>
    request<{
      id: string;
      type: string;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      result_json: any;
      ai_summary: string | null;
      created_at: string;
    } | null>("/api/analysis/overview/latest"),

  runOverviewForecast: (periods?: number) =>
    request<{
      dataset_id: string;
      dataset_name: string;
      date_column: string;
      value_column: string;
      historical: { date: string; actual: number; predicted: number }[];
      forecast: { date: string; predicted: number; lower: number; upper: number }[];
      stats: {
        trend: string;
        slope_per_period: number;
        period_type: string;
        r_squared: number;
        std_error: number;
        forecast_periods: number;
      };
    }>("/api/analysis/overview/forecast", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ periods: periods ?? 90 }),
    }),

  runForecast: (
    datasetId: string,
    dateColumn?: string,
    valueColumn?: string,
    periods?: number
  ) =>
    request<{
      dataset_id: string;
      date_column: string;
      value_column: string;
      historical: { date: string; actual: number; predicted: number }[];
      forecast: { date: string; predicted: number; lower: number; upper: number }[];
      stats: {
        trend: string;
        slope_per_period: number;
        period_type: string;
        r_squared: number;
        std_error: number;
        forecast_periods: number;
      };
    }>("/api/analysis/forecast", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dataset_id: datasetId,
        date_column: dateColumn,
        value_column: valueColumn,
        periods: periods ?? 90,
      }),
    }),

  getSummariesLatest: (opts?: { ensure?: boolean }) => {
    const q = new URLSearchParams();
    if (opts?.ensure === false) q.set("ensure", "false");
    const qs = q.toString();
    return request<{
      weekly: RecurringSummaryRecord | null;
      monthly: RecurringSummaryRecord | null;
    }>(`/api/summaries/latest${qs ? `?${qs}` : ""}`);
  },

  getSummariesHistory: (kind: "weekly" | "monthly", limit = 12) =>
    request<{ kind: string; items: RecurringSummaryRecord[] }>(
      `/api/summaries/history?kind=${kind}&limit=${limit}`
    ),

  generateSummary: (body: { kind: "weekly" | "monthly"; force?: boolean }) =>
    request<RecurringSummaryRecord>("/api/summaries/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: body.kind, force: body.force ?? false }),
    }),

  getWorkspaceTimeline: (opts?: { since?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (opts?.since) q.set("since", opts.since);
    if (opts?.limit != null) q.set("limit", String(opts.limit));
    const qs = q.toString();
    return request<{
      events: WorkspaceTimelineEvent[];
      evolution: {
        recurring: {
          theme_key: string;
          theme_label: string;
          briefings_in_window: number;
          window_size: number;
          narrative: string;
        }[];
        improving: { theme_key: string; narrative: string }[];
      };
      digests: WorkspaceDigestStub[];
    }>(`/api/workspace/timeline${qs ? `?${qs}` : ""}`);
  },

  compareWorkspaceSnapshots: (fromId: string, toId: string) =>
    request<WorkspaceCompareResult>(
      `/api/workspace/timeline/compare?from=${encodeURIComponent(fromId)}&to=${encodeURIComponent(toId)}`
    ),

  razorpayCheckout: (tier: "starter" | "pro") =>
    request<{
      short_url: string;
      subscription_id: string;
      key_id: string;
    }>(
      "/api/billing/razorpay/checkout",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tier }),
      }
    ),

  /** After Standard Checkout success - verifies HMAC per Razorpay subscription docs. */
  razorpayVerifyCheckout: (body: {
    razorpay_payment_id: string;
    razorpay_subscription_id: string;
    razorpay_signature: string;
  }) =>
    request<{ verified: boolean; subscription_plan?: string }>(
      "/api/billing/razorpay/verify-checkout",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    ),

  getIntegrationCatalog: () =>
    request<{
      providers: IntegrationProvider[];
    }>("/api/integrations/catalog"),

  listIntegrations: () =>
    request<IntegrationRecord[]>("/api/integrations"),

  createIntegration: (body: CreateIntegrationBody) =>
    request<IntegrationSyncResult>("/api/integrations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  startIntegrationOauth: (body: StartIntegrationOauthBody) =>
    request<{
      authorize_url: string;
      provider: string;
    }>("/api/integrations/oauth/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  patchIntegration: (id: string, body: PatchIntegrationBody) =>
    request<IntegrationRecord>(`/api/integrations/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  deleteIntegration: (id: string) =>
    request<{ ok: boolean; id: string }>(`/api/integrations/${id}`, {
      method: "DELETE",
    }),

  testIntegration: (id: string) =>
    request<{
      ok: boolean;
      row_count: number;
      column_count: number;
      columns: string[];
    }>(`/api/integrations/${id}/test`, { method: "POST" }),

  refreshIntegration: (id: string) =>
    request<IntegrationSyncResult>(`/api/integrations/${id}/refresh`, {
      method: "POST",
    }),
};

export type IntegrationConnectionField = {
  key: string;
  label: string;
  type: "text" | "url" | "password" | "number" | "textarea";
  required?: boolean;
  placeholder?: string;
  help?: string;
  default?: number | string;
};

export type IntegrationConnectionMode = {
  id: string;
  label: string;
  fields: IntegrationConnectionField[];
  available?: boolean;
  recommended?: boolean;
  help?: string;
};

export type IntegrationProvider = {
  id: string;
  name: string;
  tier: number;
  category: string;
  description: string;
  connection_modes: IntegrationConnectionMode[];
};

export type IntegrationRecord = {
  id: string;
  workspace_id: string;
  provider: string;
  provider_name: string;
  name: string;
  connection_mode: string;
  dataset_id: string | null;
  refresh_interval_hours: number;
  auto_analyze: boolean;
  dashboard_plan_locked: boolean;
  status: string;
  last_sync_at: string | null;
  next_sync_at: string | null;
  last_sync_error: string | null;
  created_at: string;
  updated_at: string | null;
  has_credentials: boolean;
};

export type CreateIntegrationBody = {
  provider: string;
  name: string;
  connection_mode: string;
  config: Record<string, string | number>;
  refresh_interval_hours?: number;
  auto_analyze?: boolean;
  dashboard_plan_locked?: boolean;
  run_initial_sync?: boolean;
};

export type StartIntegrationOauthBody = {
  provider: string;
  name: string;
  refresh_interval_hours?: number;
  auto_analyze?: boolean;
  dashboard_plan_locked?: boolean;
};

export type PatchIntegrationBody = {
  name?: string;
  connection_mode?: string;
  config?: Record<string, string | number>;
  refresh_interval_hours?: number;
  auto_analyze?: boolean;
  dashboard_plan_locked?: boolean;
};

export type IntegrationSyncResult = {
  integration: IntegrationRecord;
  dataset_id?: string;
  row_count?: number;
  column_count?: number;
  analysis_id?: string | null;
  dashboard_plan_locked?: boolean;
};
