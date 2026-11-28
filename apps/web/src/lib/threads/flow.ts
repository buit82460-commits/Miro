// FE-B · Threads live-flow client (ghép BE thật qua rewrite /api/* → BE).
//
// Khi NEXT_PUBLIC_API_BASE trỏ sang BE, Next rewrite /api/threads/* → BE /threads/*
// (strip prefix /api). Response BE là JSON thô (không envelope) — `api` client
// tự unwrap envelope fixture lẫn JSON thô. Khi không có env (fixture nội bộ),
// các EP này 404 → caller coi như BE unreachable, fail-closed (502 + message).
// KHÔNG bao giờ tự suy posted.
import { api } from "@/lib/api/http";

export type ThreadsIntent = {
  text: string;
  owner: string;
  shortcode: string;
  tag?: string;
  media_sha256?: string;
  media_path?: string;
};

export type ThreadsApproval = {
  scope: string;
  revision: number;
  fingerprint: string;
  approved_by?: string;
  approved_at?: number;
};

export type ThreadsPrepareResult = {
  asset: { id?: string; path?: string; sha256?: string } & Record<string, unknown>;
  render: { render_id: string; status?: string; replayed?: boolean } & Record<string, unknown>;
  replayed?: boolean;
};

export type ThreadsPublishResult = {
  publication_id?: string;
  attempt_id?: string;
  status?: string;
  replayed?: boolean;
  worker?: {
    results?: Array<{
      shortcode?: string;
      dry_run?: boolean;
      posted?: boolean;
      receipt?: string;
      error?: string;
      cause?: string;
      hint?: string;
    }>;
  };
  posted_fake?: string[];
} & Record<string, unknown>;

export type ThreadsReconcileResult = {
  reconciled?: boolean;
  shortcode?: string;
  already?: string;
  hint?: string;
  url?: string;
  post_id?: string | null;
  status?: string;
} & Record<string, unknown>;

export type ThreadsHistoryResult = {
  publication_id: string;
  render_id: string;
  assets: Array<{ asset_id: string; path: string; exists: boolean; sha256: string }>;
  renders: unknown[];
  posts: unknown[];
  queue: Array<{ publication_id?: string; attempt_id?: string; status?: string } & Record<string, unknown>>;
  journals: Array<{ file: string; shortcode?: string; status?: string; url?: string | null; post_id?: string | null }>;
} & Record<string, unknown>;

export async function prepareThreads(input: {
  asset_path: string;
  project_id: string;
  request_id: string;
  expected_revision: number;
  content_hash: string;
  spec?: Record<string, unknown>;
  tags?: string[];
}): Promise<ThreadsPrepareResult> {
  return api.post<ThreadsPrepareResult>("/api/threads/prepare", input);
}

export async function approveThreads(
  intent: ThreadsIntent,
  revision: number,
): Promise<ThreadsApproval> {
  return api.post<ThreadsApproval>("/api/threads/approve", { ...intent, revision });
}

export async function publishThreads(input: {
  publication_id: string;
  attempt_id: string;
  render_id: string;
  channel?: string;
  approval?: ThreadsApproval;
  revision?: number;
  allow_post: boolean;
} & ThreadsIntent): Promise<ThreadsPublishResult> {
  return api.post<ThreadsPublishResult>("/api/threads/publish", {
    channel: "threads",
    ...input,
  });
}

export async function reconcileThreads(intent: ThreadsIntent): Promise<ThreadsReconcileResult> {
  return api.post<ThreadsReconcileResult>("/api/threads/reconcile", intent);
}

export async function fetchThreadsHistory(
  publication_id: string,
  render_id: string,
): Promise<ThreadsHistoryResult> {
  const q = `publication_id=${encodeURIComponent(publication_id)}&render_id=${encodeURIComponent(render_id)}`;
  return api.get<ThreadsHistoryResult>(`/api/threads/history?${q}`);
}

export async function createRender(input: {
  request_id: string;
  project_id: string;
  expected_revision: number;
  content_hash: string;
  spec?: Record<string, unknown>;
}): Promise<{ render_id: string; status: string; replayed?: boolean }> {
  return api.post("/api/renders", input);
}

export async function createPublication(input: {
  publication_id: string;
  attempt_id: string;
  render_id: string;
  channel: string;
}): Promise<{ publication_id: string; attempt_id: string; status: string; replayed: boolean }> {
  return api.post("/api/publications", input);
}

export async function ensureDayPlan(input: {
  policy?: Record<string, unknown>;
  new_items?: unknown[];
  carryover?: unknown[];
  date_str?: string | null;
  was_clean_shutdown?: boolean;
} = {}): Promise<{ action: string; date?: string; slots?: number; pending?: number; status?: string }> {
  return api.post("/api/schedule/ensure", {
    policy: {},
    new_items: [],
    carryover: [],
    date_str: null,
    was_clean_shutdown: true,
    ...input,
  });
}

export async function fetchDayPlan(): Promise<{
  date?: string;
  status?: string;
  slots?: Array<{ intent_id?: string; state?: string } & Record<string, unknown>>;
}> {
  return api.get("/api/schedule/day-plan");
}

export async function patchDayPlanStatus(status: "active" | "paused"): Promise<{ status: string; date?: string }> {
  const { request } = await import("@/lib/api/http");
  return request<{ status: string; date?: string }>("/api/schedule/day-plan/status", {
    method: "PATCH",
    data: { status },
  });
}

// ---- Fail-closed error mapping (BE → message + action cho UI) ----
export type ThreadsFail = {
  code: string;
  message: string;
  action: string;
  retryPost: boolean;
};

const FAIL_ACTIONS: Record<string, string> = {
  APPROVAL_REQUIRED: "Duyệt intent trước (nút Duyệt), rồi đăng lại.",
  STALE_REVISION: "Revision đã đổi — duyệt lại để gắn revision mới.",
  FINGERPRINT_CONFLICT: "Nội dung đổi sau khi duyệt — duyệt lại, không đăng bản cũ.",
  SCOPE_DENIED: "Approval sai scope — duyệt lại đúng luồng threads_post.",
  SECRET_REJECTED: "Nội dung chứa mẫu secret — sửa text rồi làm lại từ Prepare.",
  MEDIA_UNVERIFIED: "Media chưa verify bytes — kiểm tra file media rồi thử lại.",
  CDP_UNAVAILABLE: "Không có managed tab — mở Chrome Profile 20 rồi reconcile lại.",
  ACTOR_MISMATCH: "Tab hiện tại không đúng account — verify actor rồi thử lại.",
  DUPLICATE_TAGS: "Tag #dub trùng trong batch — sửa tag rồi chuẩn bị lại.",
  REQUEST_ID_CONFLICT: "request_id đã dùng với nội dung khác — đổi request_id.",
  FAILED_BEFORE_POST: "Lỗi trước khi bấm đăng — chưa đăng gì, sửa rồi đăng lại.",
  APPROVAL_STALE_AFTER_RESTART: "BE vừa restart (approval RAM bị mất) — duyệt lại toàn bộ.",
};

export function mapThreadsError(e: unknown): ThreadsFail {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const err = e as any;
  const status: number | undefined = err?.response?.status;
  const data = err?.response?.data;
  const rawDetail: string =
    (typeof data === "string" ? data : (data?.detail ?? data?.error ?? "")) ||
    err?.message ||
    "Lỗi không rõ";
  const detail = String(rawDetail);
  const m = detail.match(/^([A-Z][A-Z0-9_]+)\s*:\s*(.*)$/s);
  const code = (m?.[1] ?? (status === 403 ? "APPROVAL_REQUIRED" : status === 409 ? "REQUEST_ID_CONFLICT" : status === 422 ? "SECRET_REJECTED" : "UNKNOWN_ERROR")).trim();
  const message = (m?.[2] ?? detail).trim() || detail;
  // UNKNOWN: reconcile-readonly, KHÔNG nút thử-lại-post.
  const isUnknown =
    code.includes("UNKNOWN") || code === "UNCONFIRMED_NO_REPLAY" || /chưa xác minh/i.test(detail);
  return {
    code,
    message,
    action: isUnknown
      ? "Trạng thái chưa xác minh — chỉ Reconcile (read-only), không đăng lại."
      : (FAIL_ACTIONS[code] ?? "Xem chi tiết BE, sửa rồi thử lại từ bước phù hợp."),
    retryPost: !isUnknown,
  };
}
