import { api } from "@/lib/api/http";

// Service cho UI doc lap Slice 04: noi BE that qua rewrite /api -> BE
// (NEXT_PUBLIC_API_BASE). BE so huu state; FE chi doc + invalidate Query key.
// Khong luu credential/key tren FE.
const PREFIX = "/api";

export type BeTask = {
  id: string;
  request_id: string;
  fingerprint?: string;
  status: string;
  revision?: number;
  error?: { code: string; message: string } | null;
  evidence?: Record<string, unknown> | null;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
};

export type BeTaskSubmit = {
  request_id: string;
  message: string;
  videos: { title: string; project_id?: string; source?: string }[];
  use_ai?: boolean;
  handoff?: boolean;
  description?: string;
  tags?: string[];
  language?: "vi" | "en" | "zh";
};

export type BeEvent = {
  id: number;
  task_id: string;
  sequence: number;
  timestamp: string;
  type: string;
  data: Record<string, unknown>;
};

export type RuntimeStatus = {
  be: { status: string };
  wiring: { ok: boolean; wiring: string; reason: string };
  bridge: { tabs: { browser: string; tab: number; url: string; title: string }[]; count: number; error: string };
  tasks: { count: number };
};

export type RunMessageOut = {
  ok: boolean;
  error?: string;
  route?: { job_type: string; params?: Record<string, unknown>; matched?: string[] };
  evidence?: Record<string, unknown> | null;
  items?: Record<string, unknown>[];
  navigated_url?: string;
  task_id?: string;
  hint?: string;
};

export type ApprovalOut = {
  scope: string;
  revision: number;
  approved_by?: string;
  revoked?: boolean;
  [key: string]: unknown;
};

export type DayPlan = {
  date?: string;
  status?: string;
  slots?: { state?: string; [key: string]: unknown }[];
  [key: string]: unknown;
};

function errMessage(e: unknown): { code?: string; message: string; status?: number } {
  const ax = e as { response?: { status?: number; data?: unknown }; message?: string };
  const status = ax?.response?.status;
  const data = ax?.response?.data as
    | { detail?: { code?: string; message?: string } | string; error?: string }
    | null
    | undefined;
  let code: string | undefined;
  let message = ax?.message ?? "Request failed";
  if (typeof data?.detail === "string") message = data.detail;
  else if (data?.detail && typeof data.detail === "object") {
    code = data.detail.code;
    message = data.detail.message ?? message;
  } else if (typeof data?.error === "string") {
    code = data.error;
    message = data.error;
  }
  return { code, message, status };
}

export const RuntimeService = {
  errMessage,
  status(): Promise<RuntimeStatus> {
    return api.get<RuntimeStatus>(`${PREFIX}/tasks/runtime/status`);
  },
  recent(limit = 20): Promise<BeTask[]> {
    return api.get<BeTask[]>(`${PREFIX}/tasks/recent?limit=${limit}`);
  },
  listCompat(limit = 20): Promise<BeTask[]> {
    return api.get<BeTask[]>(`${PREFIX}/tasks?limit=${limit}`);
  },
  get(id: string): Promise<BeTask> {
    return api.get<BeTask>(`${PREFIX}/tasks/${encodeURIComponent(id)}`);
  },
  events(id: string): Promise<BeEvent[]> {
    return api.get<BeEvent[]>(`${PREFIX}/tasks/${encodeURIComponent(id)}/events`);
  },
  create(input: BeTaskSubmit): Promise<BeTask> {
    return api.post<BeTask>(`${PREFIX}/tasks`, input);
  },
  runMessage(message: string, tabId: number, liveOrigin = "", limit?: number): Promise<RunMessageOut> {
    return api.post<RunMessageOut>(`${PREFIX}/tasks/run-message`, {
      message,
      tab_id: tabId,
      live_origin: liveOrigin,
      ...(limit !== undefined ? { limit } : {}),
    });
  },
  stop(id: string): Promise<BeTask> {
    return api.post<BeTask>(`${PREFIX}/tasks/${encodeURIComponent(id)}/stop`);
  },
  workerStopped(id: string): Promise<BeTask> {
    return api.post<BeTask>(`${PREFIX}/tasks/${encodeURIComponent(id)}/worker-stopped`);
  },
  waitStop(id: string, graceSeconds?: number): Promise<BeTask> {
    const q = graceSeconds !== undefined ? `?grace_seconds=${encodeURIComponent(String(graceSeconds))}` : "";
    return api.post<BeTask>(`${PREFIX}/tasks/${encodeURIComponent(id)}/wait-stop${q}`);
  },
  restart(id: string): Promise<BeTask> {
    return api.post<BeTask>(`${PREFIX}/tasks/${encodeURIComponent(id)}/restart`);
  },
  resume(id: string): Promise<BeTask> {
    return api.post<BeTask>(`${PREFIX}/tasks/${encodeURIComponent(id)}/resume`);
  },
  approve(id: string, item = 0, scope = "edit", revision = 1): Promise<ApprovalOut> {
    return api.post<ApprovalOut>(
      `${PREFIX}/tasks/${encodeURIComponent(id)}/approve?item=${item}&scope=${encodeURIComponent(scope)}&revision=${revision}`,
    );
  },
  revoke(id: string, item = 0): Promise<{ revoked: boolean }> {
    return api.post<{ revoked: boolean }>(`${PREFIX}/tasks/${encodeURIComponent(id)}/revoke?item=${item}`);
  },
};

export const ScheduleService = {
  errMessage,
  dayPlan(): Promise<DayPlan> {
    return api.get<DayPlan>(`${PREFIX}/schedule/day-plan`);
  },
  ensure(input: {
    policy?: Record<string, unknown>;
    new_items?: Record<string, unknown>[];
    carryover?: Record<string, unknown>[];
    date_str?: string;
    was_clean_shutdown?: boolean;
  }): Promise<{ action: string; date?: string; slots: number; pending: number; status?: string }> {
    return api.post(`${PREFIX}/schedule/ensure`, {
      policy: input.policy ?? {},
      new_items: input.new_items ?? [],
      carryover: input.carryover ?? [],
      ...(input.date_str !== undefined ? { date_str: input.date_str } : {}),
      was_clean_shutdown: input.was_clean_shutdown ?? true,
    });
  },
  setStatus(status: "active" | "paused"): Promise<{ status: string; date?: string }> {
    return api.patch(`${PREFIX}/schedule/day-plan/status`, { status });
  },
};

export const HealthService = {
  check(): Promise<{ status: string; service?: string; be?: string }> {
    return api.get(`${PREFIX}/health`);
  },
};
