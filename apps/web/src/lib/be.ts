// BFF → BE proxy dùng chung. BE sở hữu state; BFF chỉ forward status/body.
// Khi BE không reachable: caller tự fallback fixture (projects) hoặc báo lỗi rõ.
export const BE_BASE = (process.env.MIRO_BE_BASE ?? "http://localhost:8770").replace(/\/+$/, "");

type ProxyOpts = {
  method?: string;
  body?: unknown;
  timeoutMs?: number;
};

export async function proxyBe(bePath: string, opts: ProxyOpts = {}): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts.timeoutMs ?? 30_000);
  try {
    const init: RequestInit = {
      method: opts.method ?? "GET",
      headers: { "Content-Type": "application/json" },
      signal: ctrl.signal,
    };
    if (opts.body !== undefined) init.body = JSON.stringify(opts.body);
    const res = await fetch(`${BE_BASE}${bePath}`, init);
    const text = await res.text();
    return new Response(text, {
      status: res.status,
      headers: { "Content-Type": res.headers.get("content-type") ?? "application/json" },
    });
  } finally {
    clearTimeout(timer);
  }
}

// Thử BE trước; BE reachable (kể cả 4xx/5xx) → trả response BE nguyên trạng.
// Chỉ khi lỗi mạng/timeout mới trả null để caller fallback fixture.
export async function tryBe(bePath: string, opts: ProxyOpts = {}): Promise<Response | null> {
  try {
    return await proxyBe(bePath, opts);
  } catch {
    return null;
  }
}
