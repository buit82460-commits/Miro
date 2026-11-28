// Helper poll HTTP cho mọi op dài (BE không có SSE/WebSocket — §09 contract).
// Dừng khi `done(result)` true, hết `attempts`, hoặc `signal` abort.
export type PollOptions<T> = {
  attempts?: number;
  intervalMs?: number;
  done?: (result: T) => boolean;
  signal?: AbortSignal;
};

export async function poll<T>(fn: () => Promise<T>, options: PollOptions<T> = {}): Promise<T> {
  const { attempts = 30, intervalMs = 2000, done, signal } = options;
  let last: T | undefined;
  for (let i = 0; i < attempts; i++) {
    if (signal?.aborted) throw new DOMException("Poll aborted", "AbortError");
    last = await fn();
    if (!done || done(last)) return last;
    if (i < attempts - 1) {
      await new Promise<void>((resolve, reject) => {
        const t = setTimeout(resolve, intervalMs);
        signal?.addEventListener("abort", () => {
          clearTimeout(t);
          reject(new DOMException("Poll aborted", "AbortError"));
        }, { once: true });
      });
    }
  }
  return last as T;
}
