import { api } from "@/lib/api/http";

// Service cho UI doc lap Slice 04: noi BE that qua rewrite /api -> BE
// (NEXT_PUBLIC_API_BASE). BE so huu state; FE chi doc + invalidate Query key.
// Khong luu credential/key tren FE.
const PREFIX = "/api";

export type BeTask = {
  id: string;
  request_id: string;
  status: string;
  error?: { code: string; message: string } | null;
  evidence?: Record<string, unknown> | null;
  created_at?: string;
  updated_at?: string;
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
};

export const RuntimeService = {
  status(): Promise<RuntimeStatus> {
    return api.get<RuntimeStatus>(`${PREFIX}/tasks/runtime/status`);
  },
  recent(limit = 20): Promise<BeTask[]> {
    return api.get<BeTask[]>(`${PREFIX}/tasks/recent?limit=${limit}`);
  },
  get(id: string): Promise<BeTask> {
    return api.get<BeTask>(`${PREFIX}/tasks/${id}`);
  },
  events(id: string): Promise<BeEvent[]> {
    return api.get<BeEvent[]>(`${PREFIX}/tasks/${id}/events`);
  },
  runMessage(message: string, tabId: number, liveOrigin = ""): Promise<RunMessageOut> {
    return api.post<RunMessageOut>(`${PREFIX}/tasks/run-message`, {
      message,
      tab_id: tabId,
      live_origin: liveOrigin,
    });
  },
  stop(id: string): Promise<BeTask> {
    return api.post<BeTask>(`${PREFIX}/tasks/${id}/stop`);
  },
};
