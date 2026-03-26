const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || "Request failed");
  }

  return res.json();
}

export const api = {
  health: () => request<{ status: string }>("/health"),

  uploadFile: (file: File, description: string) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("description", description);
    return request<{
      id: string;
      filename: string;
      status: string;
      dataset_id: string;
      row_count: number;
      column_count: number;
      cleaning_report: { steps: string[]; original_shape: number[]; cleaned_shape: number[] };
    }>("/api/uploads", { method: "POST", body: formData });
  },

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
        created_at: string;
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
      created_at: string;
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

  getDashboardData: (datasetId: string) =>
    request<{
      dataset_id: string;
      charts: {
        id: string;
        title: string;
        type: "line" | "bar" | "pie" | "area";
        data: Record<string, unknown>[];
        x_label?: string;
        y_label?: string;
      }[];
    }>(`/api/dashboards/dataset/${datasetId}`),

  chat: (datasetId: string, question: string) =>
    request<{ answer: string; chart_data?: Record<string, unknown> }>(
      "/api/chat",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dataset_id: datasetId, question }),
      }
    ),

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
      }[];
      datasets: {
        id: string;
        name: string;
        row_count: number | null;
        column_count: number | null;
        created_at: string;
      }[];
    }>("/api/dashboards/overview"),

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
      body: JSON.stringify({ periods: periods || 12 }),
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
        periods: periods || 12,
      }),
    }),
};
