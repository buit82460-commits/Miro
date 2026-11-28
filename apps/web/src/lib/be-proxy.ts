// BFF → BE passthrough cho nhóm Tasks/Runtime/Schedule.
// BE sở hữu state (http://127.0.0.1:8770); BFF chỉ forward status + body,
// không bịa state. BE down → 503 fail-closed, UI tự hiển thị message + action.
const BE_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8770").replace(/\/+$/, "");

export function beBase() {
  return BE_BASE;
}

export type BeFetchResult =
  | { ok: true; status: number; body: unknown }
  | { ok: false; unreachable: true };

export async function beFetch(path: string, init?: RequestInit): Promise<BeFetchResult> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 15_000);
  try {
    const res = await fetch(`${BE_BASE}${path}`, {
      ...init,
      signal: ctrl.signal,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
    const body = await res.json().catch(() => null);
    return { ok: true, status: res.status, body };
  } catch {
    return { ok: false, unreachable: true };
  } finally {
    clearTimeout(timer);
  }
}

export function beForward(status: number, body: unknown) {
  return Response.json(body, { status });
}

export function beUnavailable(detail = "BE_UNREACHABLE") {
  return Response.json(
    { detail: { code: 503, message: `Chưa nối được BE (${BE_BASE}). Kiểm tra BE :8770 rồi thử lại.` }, error: detail },
    { status: 503 },
  );
}

// Chuẩn hoá query BE: chỉ forward key cho phép, tránh injection param lạ.
export function pickParams(url: URL, keys: string[]) {
  const out = new URLSearchParams();
  for (const k of keys) {
    const v = url.searchParams.get(k);
    if (v !== null) out.set(k, v);
  }
  const s = out.toString();
  return s ? `?${s}` : "";
}
