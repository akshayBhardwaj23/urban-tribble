import type { IngestionProfile } from "@/lib/ingestion";
import {
  ApiAuthError,
  ApiTimeoutError,
  formatUserFacingApiError,
  sanitizeApiErrorMessage,
} from "@/lib/api-errors";
import { accessTokenExpiresAt } from "@/lib/access-token";
import { resolveApiBase } from "@/lib/api-base";

export { resolveApiBase };

const API_BASE = resolveApiBase();

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

export type ApiWorkspace = {
  id: string;
  name: string;
  is_active?: boolean;
  created_at: string;
  /** Saved Outlook chart source; omit or null = automatic (largest qualifying file). */
  outlook_forecast_dataset_id?: string | null;
  outlook_forecast_date_column?: string | null;
  outlook_forecast_value_column?: string | null;
};

export type ApiUserProfile = {
  id: string;
  email: string;
  name: string | null;
  image: string | null;
  active_workspace_id: string | null;
  needs_onboarding: boolean;
  subscription_plan?: string;
  subscription_renews_at?: string | null;
  workspaces: ApiWorkspace[];
};

let _accessToken: string | null = null;
let _accessTokenExpires: number | null = null;

/** @deprecated Prefer setApiAccessToken — email is no longer used for API auth. */
export function setApiUserEmail(_email: string | null) {
  // Kept as a no-op so older call sites compile during the migration.
}

export function setApiAccessToken(token: string | null) {
  if (!token) {
    _accessToken = null;
    _accessTokenExpires = null;
    return;
  }

  const expires = accessTokenExpiresAt(token);
  // Several call sites re-apply the token from a React session snapshot that
  // may predate a renewal we just performed. Never trade a live token for an
  // older one — but always accept a replacement for one that already lapsed.
  if (
    _accessToken &&
    _accessTokenExpires !== null &&
    _accessTokenExpires > Date.now() &&
    expires !== null &&
    expires < _accessTokenExpires
  ) {
    return;
  }

  _accessToken = token;
  _accessTokenExpires = expires;
}

export function getApiAccessToken(): string | null {
  return _accessToken;
}

/** Ask NextAuth for a freshly minted token; resolves null if none is available. */
type AccessTokenRenewer = () => Promise<string | null>;

let _renewAccessToken: AccessTokenRenewer | null = null;
let _onSessionExpired: (() => void) | null = null;

/**
 * Wired once by the app shell so any 401 can renew the session and retry,
 * and so an unrenewable session ends in a sign-in prompt rather than a
 * generic error screen. Kept as a registration hook to keep this module free
 * of a next-auth dependency.
 */
export function setApiSessionHandlers(handlers: {
  renew: AccessTokenRenewer;
  onExpired: () => void;
}) {
  _renewAccessToken = handlers.renew;
  _onSessionExpired = handlers.onExpired;
}

let _renewalInFlight: Promise<string | null> | null = null;

/** Renew the access token, collapsing concurrent 401s into one attempt. */
async function renewAccessToken(): Promise<string | null> {
  if (!_renewAccessToken) return null;
  if (!_renewalInFlight) {
    const renew = _renewAccessToken;
    _renewalInFlight = (async () => {
      try {
        return await renew();
      } catch {
        return null;
      }
    })().finally(() => {
      _renewalInFlight = null;
    });
  }
  return _renewalInFlight;
}

/** Client-side deadlines. Without these a hung backend leaves a spinner forever. */
const DEFAULT_TIMEOUT_MS = 30_000;
export const TIMEOUTS = {
  /** Parsing and profiling a workbook server-side. */
  upload: 180_000,
  /** LLM briefing generation. */
  analysis: 180_000,
  /** LLM question answering. */
  chat: 120_000,
} as const;

type RequestOptions = RequestInit & {
  /** Overrides DEFAULT_TIMEOUT_MS. Pass 0 to opt out entirely. */
  timeoutMs?: number;
  /** Verb phrase used in timeout copy, e.g. "read your file". */
  action?: string;
};

async function request<T>(path: string, options?: RequestOptions): Promise<T> {
  const { timeoutMs, action, ...init } = options ?? {};
  const deadline = timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const wasAuthenticated = Boolean(_accessToken);

  /** One attempt, reporting which token it used so a retry can tell them apart. */
  const send = async (): Promise<{ res: Response; token: string | null }> => {
    const token = _accessToken;
    const headers: Record<string, string> = {
      ...(init.headers as Record<string, string>),
    };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const controller =
      deadline > 0 && !init.signal ? new AbortController() : null;
    const timer = controller
      ? setTimeout(() => controller.abort(), deadline)
      : null;

    try {
      const res = await fetch(`${API_BASE}${path}`, {
        ...init,
        headers,
        signal: controller?.signal ?? init.signal,
      });
      return { res, token };
    } catch (e) {
      if (controller?.signal.aborted) {
        throw new ApiTimeoutError(action ?? "complete that request", deadline);
      }
      throw new Error(formatUserFacingApiError(e, action));
    } finally {
      if (timer) clearTimeout(timer);
    }
  };

  const first = await send();
  let res = first.res;

  // The token lapsed while this tab was open: renew it once and replay.
  if (res.status === 401 && wasAuthenticated) {
    // A parallel request may already have renewed while this one was in flight.
    const renewed =
      first.token !== _accessToken ? _accessToken : await renewAccessToken();
    if (renewed) {
      res = (await send()).res;
    }
    if (res.status === 401) {
      _onSessionExpired?.();
      throw new ApiAuthError();
    }
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

  deleteAuthAccount: (confirmation: string = "DELETE") =>
    request<{ ok: boolean; deleted: boolean }>("/api/auth/me", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmation }),
    }),

  syncUser: (body: { name: string | null; image: string | null }) =>
    request<ApiUserProfile>("/api/auth/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      timeoutMs: 20_000,
      action: "load your account",
    }),

  createWorkspace: (name: string) =>
    request<ApiWorkspace>("/api/workspaces", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),

  activateWorkspace: (workspaceId: string) =>
    request<{ active_workspace_id: string }>(
      `/api/workspaces/${workspaceId}/activate`,
      { method: "POST" }
    ),

  deleteWorkspace: (workspaceId: string) =>
    request<{
      ok: boolean;
      deleted: boolean;
      active_workspace_id: string | null;
    }>(`/api/workspaces/${workspaceId}`, { method: "DELETE" }),

  uploadFile: async (
    file: File,
    description: string,
    opts?: { onStage?: (stage: string | null | undefined) => void }
  ) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("description", description);
    type UploadResult = {
      id: string;
      filename: string;
      file_type: string;
      status: string;
      processing_stage?: string | null;
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
      mapping_spec?: unknown;
      sheets?: unknown[];
      /** Which tab of a workbook this dataset read; null for CSV. */
      sheet?: string | null;
      /** Tabs of the same workbook that do not have a dataset yet. */
      importable_sheets?: string[];
      poll_url?: string;
      error?: string | null;
    };

    const initial = await request<UploadResult & { dataset_id: string | null }>(
      "/api/uploads",
      {
        method: "POST",
        body: formData,
        timeoutMs: TIMEOUTS.upload,
        action: "read your file",
      }
    );
    opts?.onStage?.(initial.processing_stage ?? "queued");

    // Sync path already finished.
    if (initial.status === "completed" && initial.dataset_id) {
      return initial as UploadResult;
    }
    if (initial.status === "failed") {
      throw new Error(
        sanitizeApiErrorMessage(initial.error || "Failed to process file")
      );
    }

    // Async path: poll until the worker finishes.
    const uploadId = initial.id;
    const deadline = Date.now() + TIMEOUTS.upload;
    let delay = 600;
    while (Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, delay));
      delay = Math.min(delay + 200, 2000);
      const status = await request<UploadResult & { dataset_id: string | null }>(
        `/api/uploads/${uploadId}`,
        { timeoutMs: 30_000, action: "check upload progress" }
      );
      opts?.onStage?.(status.processing_stage);
      if (status.status === "completed" && status.dataset_id) {
        return status as UploadResult;
      }
      if (status.status === "failed") {
        throw new Error(
          sanitizeApiErrorMessage(status.error || "Failed to process file")
        );
      }
    }
    throw new ApiTimeoutError("finish processing your file", TIMEOUTS.upload);
  },

  patchDataset: (
    datasetId: string,
    body: {
      business_classification?: string;
      primary_date_column?: string | null;
      primary_amount_column?: string | null;
      segment_columns?: string[];
      dayfirst?: boolean | null;
      drop_duplicates?: boolean;
      sheet?: string | null;
      header_row?: number | null;
      column_roles?: Record<string, string>;
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

  /**
   * Import further tabs of an already-uploaded workbook, each as its own
   * dataset. Returns how many were created; tabs that already have a dataset
   * are skipped rather than duplicated.
   */
  importUploadSheets: (uploadId: string, sheetNames: string[]) =>
    request<{
      imported: number;
      uploads: { id: string; filename: string; sheet: string }[];
      skipped_reason: string | null;
    }>(`/api/uploads/${uploadId}/sheets`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sheet_names: sheetNames }),
      action: "import those sheets",
    }),

  getUpload: (id: string) =>
    request<{
      id: string;
      filename: string;
      status: string;
      processing_stage?: string | null;
      dataset_id?: string | null;
      user_description: string | null;
      created_at: string;
      error?: string | null;
      ingestion?: IngestionProfile | null;
      row_count?: number | null;
      column_count?: number | null;
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
        expense_columns?: string[];
        category_columns: string[];
        numeric_columns: string[];
        text_columns: string[];
        primary_timeline?: string | null;
        primary_amount?: string | null;
        all_columns?: string[];
      } | null;
      data_summary: Record<string, unknown> | null;
      cleaned_report: {
        steps: string[];
        original_shape: number[];
        cleaned_shape: number[];
        flags?: { kind: string; code: string; message: string }[];
        structured_steps?: {
          code?: string;
          kind?: string;
          message: string;
        }[];
      } | null;
      mapping_spec: {
        version?: number;
        source?: string;
        primary_timeline?: string | null;
        primary_amount?: string | null;
        dayfirst?: boolean | null;
        drop_duplicates?: boolean;
        sheet?: string | null;
        header_row?: number;
        columns?: {
          name: string;
          role: string;
          date_format?: string | null;
          original_name?: string | null;
          meaning?: string | null;
        }[];
        ingestion_profile?: {
          flags?: { kind: string; code: string; message: string }[];
          interpretations?: string[];
        } | null;
      } | null;
      sheets?: { name: string; score: number; rows?: number; cols?: number }[];
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
      timeoutMs: TIMEOUTS.analysis,
      action: "build your briefing",
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
        timeoutMs: TIMEOUTS.chat,
        action: "answer that question",
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
        timeoutMs: TIMEOUTS.chat,
        action: "answer that question",
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
      timeoutMs: TIMEOUTS.upload,
      action: "add this file to the source",
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
      enabled: boolean;
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

  getIntegrationOauthSession: (sessionId: string) =>
    request<IntegrationOauthSession>(`/api/integrations/oauth/session/${sessionId}`),

  completeMicrosoftOauth: (body: CompleteMicrosoftOauthBody) =>
    request<IntegrationSyncResult>("/api/integrations/oauth/complete/microsoft", {
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

  inspectGoogleTabs: (body: { session_id: string; item_ids: string[] }) =>
    request<{ files: GoogleFileTabs[] }>("/api/integrations/oauth/tabs/google", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  listIntegrationTabs: (id: string) =>
    request<{
      tabs: SheetTab[];
      current_tab: string | null;
      suggested_tab: string | null;
    }>(`/api/integrations/${id}/tabs`),

  updateIntegrationSheet: (id: string, sheetName: string) =>
    request<IntegrationSyncResult>(`/api/integrations/${id}/sheet`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sheet_name: sheetName }),
    }),

  completeGoogleOauth: (body: CompleteGoogleOauthBody) =>
    request<GoogleConnectResult>("/api/integrations/oauth/complete/google", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
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

export type CompleteMicrosoftOauthBody = {
  session_id: string;
  item_id: string;
};

/** Google connects several sheets from one sign-in, so this takes a list. */
export type CompleteGoogleOauthBody = {
  session_id: string;
  item_ids: string[];
  /**
   * Chosen tabs per file id. A workbook whose tabs hold separate datasets can
   * contribute several, each becoming its own source. Omitted files fall back
   * to the auto-pick.
   */
  sheet_names?: Record<string, string[]>;
};

export type SheetTab = {
  name: string;
  score: number;
  sampled_rows: number;
  cols: number;
};

/** What a workbook's tabs look like, and whether the user should be asked. */
export type GoogleFileTabs = {
  item_id: string;
  name: string;
  tabs: SheetTab[];
  needs_choice: boolean;
  suggested_tab: string | null;
};

/**
 * Google's connect returns as soon as the sources exist; the first sync of each
 * runs in the background, so every record comes back `pending` and the client
 * polls the list endpoint for it to move on.
 */
export type GoogleConnectResult = {
  connected: number;
  integrations: IntegrationRecord[];
  syncing: boolean;
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
  row_count?: number | null;
  column_count?: number | null;
  analysis_id?: string | null;
  /** Why no fresh briefing was produced, e.g. the plan's analysis cap. */
  analysis_skipped_reason?: string | null;
  dashboard_plan_locked?: boolean;
  /** True when the source was unchanged and nothing needed re-fetching. */
  skipped?: boolean;
  skipped_reason?: string | null;
};

export type IntegrationOauthSession = {
  session_id: string;
  provider: string;
  name: string;
  refresh_interval_hours: number;
  auto_analyze: boolean;
  dashboard_plan_locked: boolean;
  files: IntegrationOauthFile[];
};

export type IntegrationOauthFile = {
  id: string;
  name: string;
  web_url?: string | null;
  size?: number | null;
  last_modified?: string | null;
  /** Microsoft only. */
  drive_id?: string | null;
  /** Google only. */
  mime_type?: string | null;
  is_native_sheet?: boolean;
};
