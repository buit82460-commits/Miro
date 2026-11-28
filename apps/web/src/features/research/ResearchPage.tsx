"use client";
import { useState } from "react";
import { useMiroStore } from "../../stores/useMiroStore";
import { Button, Card, StatusTag } from "../../components/miro-ui/primitives";

type EvidenceLevel = "metadata_only" | "frames_analyzed";

interface ResearchResult {
  kind: string;
  summary: string;
  items: Record<string, unknown>[];
  sources: string[];
  fetched_at: string;
  evidence: EvidenceLevel;
}

function renderValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") return String(v);
  try {
    return JSON.stringify(v);
  } catch {
    return "—";
  }
}

export function ResearchPage() {
  const setActiveContext = useMiroStore((s) => s.setActiveContext);

  const [query, setQuery] = useState("");
  const [videoUrl, setVideoUrl] = useState("");
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [loading, setLoading] = useState<"idle" | "search" | "video">("idle");
  const [error, setError] = useState<string | null>(null);

  const runSearch = async () => {
    if (!query.trim()) return;
    setLoading("search");
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/research/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query.trim(), limit: 10 }),
      });
      const data = (await res.json().catch(() => null)) as ResearchResult | null;
      if (!res.ok || !data) {
        setError(res.status === 503 ? "BE chưa nối được (503). Kiểm tra BE :8770 rồi thử lại." : `BE trả lỗi HTTP ${res.status}.`);
        return;
      }
      setResult(data);
      setActiveContext({
        resourceKind: "research",
        resourceLabel: `Tìm kiếm: ${query.trim()}`,
      });
    } catch {
      setError("Không gọi được BFF /api/research/search.");
    } finally {
      setLoading("idle");
    }
  };

  const runVideo = async () => {
    if (!videoUrl.trim()) return;
    setLoading("video");
    setError(null);
    setResult(null);
    try {
      const res = await fetch("/api/research/video", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: videoUrl.trim(), include_frames: false }),
      });
      const data = (await res.json().catch(() => null)) as ResearchResult | null;
      if (!res.ok || !data) {
        setError(res.status === 503 ? "BE chưa nối được (503). Kiểm tra BE :8770 rồi thử lại." : `BE trả lỗi HTTP ${res.status}.`);
        return;
      }
      setResult(data);
      setActiveContext({
        resourceKind: "research",
        resourceLabel: `Video: ${videoUrl.trim()}`,
      });
    } catch {
      setError("Không gọi được BFF /api/research/video.");
    } finally {
      setLoading("idle");
    }
  };

  return (
    <div className="h-full overflow-y-auto p-4 sm:p-6">
      <div className="mx-auto max-w-[1280px] space-y-6">
        <div className="space-y-1">
          <h1 className="text-h1 text-[var(--color-text-primary)]">Nghiên cứu</h1>
          <p className="text-[14px] text-[var(--color-text-secondary)]">
            Kết quả lấy trực tiếp từ Backend qua BFF /api/research/*. Không dùng dữ liệu mẫu.
          </p>
        </div>

        <Card className="space-y-3">
          <div className="flex flex-wrap items-end gap-2">
            <div className="flex-1 min-w-[220px] space-y-1">
              <label className="text-[12px] font-medium text-[var(--color-text-secondary)]">
                Tìm kiếm (POST /research/search)
              </label>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && void runSearch()}
                placeholder="Nhập từ khóa nghiên cứu..."
                className="h-9 w-full rounded-[6px] bg-[var(--color-surface-2)] border border-[var(--color-border)] px-3 text-[13px] text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-focus-ring)]"
              />
            </div>
            <Button variant="primary" onClick={() => void runSearch()} disabled={loading !== "idle" || !query.trim()}>
              <span>{loading === "search" ? "Đang tìm..." : "Tìm kiếm"}</span>
            </Button>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <div className="flex-1 min-w-[220px] space-y-1">
              <label className="text-[12px] font-medium text-[var(--color-text-secondary)]">
                Phân tích video (POST /research/video)
              </label>
              <input
                type="text"
                value={videoUrl}
                onChange={(e) => setVideoUrl(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && void runVideo()}
                placeholder="Dán URL video..."
                className="h-9 w-full rounded-[6px] bg-[var(--color-surface-2)] border border-[var(--color-border)] px-3 text-[13px] text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-focus-ring)]"
              />
            </div>
            <Button variant="secondary" onClick={() => void runVideo()} disabled={loading !== "idle" || !videoUrl.trim()}>
              <span>{loading === "video" ? "Đang phân tích..." : "Phân tích video"}</span>
            </Button>
          </div>
        </Card>

        {loading !== "idle" && (
          <Card className="p-6 text-center text-[13px] text-[var(--color-text-secondary)]">
            Đang gọi Backend...
          </Card>
        )}

        {error && (
          <Card className="p-4 border border-[var(--color-error)]/40 bg-[var(--color-error-bg)]/40">
            <p className="text-[13px] text-[var(--color-error)]">{error}</p>
          </Card>
        )}

        {!result && loading === "idle" && !error && (
          <Card className="p-8 text-center space-y-2">
            <p className="text-[14px] text-[var(--color-text-secondary)]">
              Chưa có kết quả nghiên cứu. Nhập từ khóa hoặc URL video ở trên để tra cứu từ Backend.
            </p>
          </Card>
        )}

        {result && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <StatusTag tone={result.evidence === "frames_analyzed" ? "success" : "warning"}>
                {result.evidence === "frames_analyzed" ? "frames_analyzed — đã phân tích khung hình" : "metadata_only — chỉ metadata (BE mặc định NullProvider)"}
              </StatusTag>
              <span className="font-mono-tech text-[11px] text-[var(--color-text-muted)]">
                kind: {result.kind} · fetched: {result.fetched_at}
              </span>
            </div>

            {result.summary && (
              <Card className="space-y-1">
                <h2 className="text-h4 text-[var(--color-text-primary)]">Tóm tắt</h2>
                <p className="text-[14px] text-[var(--color-text-secondary)]">{result.summary}</p>
              </Card>
            )}

            <Card className="space-y-2">
              <h2 className="text-h4 text-[var(--color-text-primary)]">
                Nguồn ({result.sources.length})
              </h2>
              {result.sources.length === 0 ? (
                <p className="text-[13px] text-[var(--color-text-muted)]">
                  BE không trả nguồn nào (metadata-only).
                </p>
              ) : (
                <ul className="space-y-1">
                  {result.sources.map((s, i) => (
                    <li key={i} className="font-mono-tech text-[12px] text-[var(--color-text-secondary)] break-all">
                      {s}
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card className="space-y-2">
              <h2 className="text-h4 text-[var(--color-text-primary)]">
                Bản ghi ({result.items.length})
              </h2>
              {result.items.length === 0 ? (
                <p className="text-[13px] text-[var(--color-text-muted)]">
                  BE trả danh sách rỗng. Thử từ khóa khác.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse text-left min-w-[560px]">
                    <thead className="bg-[var(--color-surface-2)] border-b border-[var(--color-border)]">
                      <tr className="h-[32px] text-[12px] font-medium text-[var(--color-text-secondary)]">
                        {Object.keys(result.items[0] ?? {}).slice(0, 6).map((k) => (
                          <th key={k} className="px-3">{k}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[var(--color-border-subtle)]">
                      {result.items.map((item, i) => (
                        <tr key={i} className="hover:bg-[var(--color-hover)]/60">
                          {Object.entries(item).slice(0, 6).map(([k, v]) => (
                            <td key={k} className="px-3 py-2 text-[12px] text-[var(--color-text-secondary)] max-w-[260px] truncate">
                              {renderValue(v)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
