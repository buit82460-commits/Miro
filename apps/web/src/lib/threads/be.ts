// FE-B · helper gọi BE thật từ BFF (server-side).
// BE local-only, default http://127.0.0.1:8770 (contract §10).
// Không bao giờ tự suy posted: BE unreachable → { reachable: false } để
// caller báo lỗi BE_UNREACHABLE, không bịa dữ liệu, không chế receipt "posted".
const BE_BASE = (process.env.MIRO_BE_BASE ?? "http://127.0.0.1:8770").replace(/\/+$/, "");

export type BeCallOk<T> = { reachable: true; status: number; data: T };
export type BeCallMiss = { reachable: false; status: 0; data: null; error: string };
export type BeCall<T> = BeCallOk<T> | BeCallMiss;

export async function beFetch<T>(path: string, init?: RequestInit, timeoutMs = 10_000): Promise<BeCall<T>> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${BE_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      signal: ctrl.signal,
    });
    const data = (await res.json().catch(() => null)) as T;
    return { reachable: true, status: res.status, data };
  } catch (e) {
    return { reachable: false, status: 0, data: null, error: (e as Error).message || "unreachable" };
  } finally {
    clearTimeout(timer);
  }
}

export function beDetail(status: number, data: unknown): string {
  if (data && typeof data === "object" && "detail" in data) {
    const d = (data as { detail: unknown }).detail;
    return typeof d === "string" ? d : JSON.stringify(d);
  }
  return `BE trả HTTP ${status}`;
}
