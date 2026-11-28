import axios, { type AxiosRequestConfig } from "axios";

// Axios instance duy nhất cho FE Miro. Luôn gọi tương đối /api/... để
// Next rewrite quyết định đích: fixture nội bộ (không env) hoặc proxy sang
// BE thật (khi có NEXT_PUBLIC_API_BASE). Không gắn baseURL tuyệt đối ở đây
// để request đi qua rewrite (giữ strip prefix /api → BE).
export const http = axios.create({
  baseURL: "",
  headers: { "Content-Type": "application/json" },
  timeout: 30_000,
});

export type ApiErrorKind =
  | "BAD_REQUEST" // 400 — sai tham số / guard (ACCOUNT_MISMATCH, CREDENTIAL_*)
  | "UNAUTHORIZED" // 401
  | "NOT_FOUND" // 404 — account/platform không tồn tại
  | "CONFLICT" // 409 — trùng id / STALE_EPOCH / REQUEST_ID_CONFLICT
  | "VALIDATION" // 422 — schema không hợp lệ
  | "SERVER" // 500 — lỗi BE (BIND_PLAN_FAILED...)
  | "UNAVAILABLE" // 503 — provider/engine chưa sẵn
  | "NETWORK" // không tới được BE (BE chưa chạy / rewrite sai)
  | "UNKNOWN";

export class MiroApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;
  readonly code?: string;

  constructor(kind: ApiErrorKind, message: string, status?: number, code?: string) {
    super(message);
    this.name = "MiroApiError";
    this.kind = kind;
    this.status = status;
    this.code = code;
  }
}

// Map status HTTP → kind + gợi ý hành động cho UI (fail-closed: không auto-retry post).
export function toApiError(status: number | undefined, detail: unknown, fallback: string): MiroApiError {
  const message =
    (typeof detail === "string" && detail) ||
    (typeof detail === "object" && detail !== null && "detail" in detail
      ? String((detail as { detail: unknown }).detail)
      : "") ||
    fallback;
  switch (status) {
    case 400:
      return new MiroApiError("BAD_REQUEST", message, status);
    case 401:
      return new MiroApiError("UNAUTHORIZED", message, status);
    case 404:
      return new MiroApiError("NOT_FOUND", message, status);
    case 409:
      return new MiroApiError("CONFLICT", message, status);
    case 422:
      return new MiroApiError("VALIDATION", message, status);
    case 503:
      return new MiroApiError("UNAVAILABLE", message, status);
    case 500:
      return new MiroApiError("SERVER", message, status);
    default:
      return new MiroApiError("UNKNOWN", message, status);
  }
}

type Envelope<T> = { success: boolean; result: T };

function unwrap<T>(data: unknown): T {
  if (typeof data === "object" && data !== null && "success" in data && "result" in data) {
    return (data as Envelope<T>).result;
  }
  return data as T;
}

export async function request<T>(path: string, config?: AxiosRequestConfig): Promise<T> {
  try {
    const res = await http.request({ url: path, ...config });
    return unwrap<T>(res.data);
  } catch (err) {
    if (axios.isAxiosError(err)) {
      if (!err.response) {
        throw new MiroApiError(
          "NETWORK",
          "Không tới được BE (kiểm tra BE :8770 / NEXT_PUBLIC_API_BASE).",
        );
      }
      const status = err.response.status;
      const body = err.response.data as unknown;
      const detail =
        typeof body === "object" && body !== null && "detail" in body
          ? (body as { detail: unknown }).detail
          : typeof body === "object" && body !== null && "error" in body
            ? (body as { error: unknown }).error
            : undefined;
      throw toApiError(status, detail, err.message);
    }
    throw err instanceof Error ? err : new MiroApiError("UNKNOWN", String(err));
  }
}

export const api = {
  get<T>(path: string, config?: AxiosRequestConfig) {
    return request<T>(path, { ...config, method: "GET" });
  },
  post<T>(path: string, body?: unknown, config?: AxiosRequestConfig) {
    return request<T>(path, { ...config, method: "POST", data: body });
  },
  patch<T>(path: string, body?: unknown, config?: AxiosRequestConfig) {
    return request<T>(path, { ...config, method: "PATCH", data: body });
  },
  put<T>(path: string, body?: unknown, config?: AxiosRequestConfig) {
    return request<T>(path, { ...config, method: "PUT", data: body });
  },
  delete<T>(path: string, config?: AxiosRequestConfig) {
    return request<T>(path, { ...config, method: "DELETE" });
  },
};
