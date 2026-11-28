"use client";
import { useEffect, useState } from "react";
import { useParams } from "@/lib/router-compat";
import { useMiroStore } from "../../stores/useMiroStore";
import { Button, Card, StatusTag } from "../../components/miro-ui/primitives";

interface StudioProject {
  video_id: string;
  revision?: number;
  segments?: { startSec?: number; endSec?: number; label?: string; [k: string]: unknown }[];
  [k: string]: unknown;
}

interface StudioMedia {
  video_id: string;
  output: string;
}

type LoadState = "idle" | "loading" | "error" | "loaded" | "missing";

export function MediaStudioPage() {
  const { assetId } = useParams();
  const setActiveContext = useMiroStore((s) => s.setActiveContext);

  const [videoId, setVideoId] = useState(typeof assetId === "string" ? assetId : "");
  const [project, setProject] = useState<StudioProject | null>(null);
  const [media, setMedia] = useState<StudioMedia | null>(null);
  const [state, setState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);

  const [tpRequestId, setTpRequestId] = useState("");
  const [tpTitle, setTpTitle] = useState("");
  const [tpSource, setTpSource] = useState("");
  const [tpMsg, setTpMsg] = useState<string | null>(null);

  useEffect(() => {
    setActiveContext({ resourceLabel: undefined });
  }, [setActiveContext]);

  const load = async () => {
    const id = videoId.trim();
    if (!id) return;
    setState("loading");
    setError(null);
    setProject(null);
    setMedia(null);
    try {
      const [pRes, mRes] = await Promise.all([
        fetch(`/api/studio/project/${encodeURIComponent(id)}`),
        fetch(`/api/studio/media/${encodeURIComponent(id)}`),
      ]);
      if (pRes.status === 503 || mRes.status === 503) {
        setState("error");
        setError("BE chưa nối được (503). Kiểm tra BE :8770 rồi thử lại.");
        return;
      }
      if (pRes.status === 404) {
        setState("missing");
        return;
      }
      if (!pRes.ok) {
        setState("error");
        setError(`BE trả lỗi HTTP ${pRes.status} khi lấy project.`);
        return;
      }
      const pData = (await pRes.json().catch(() => null)) as StudioProject | null;
      setProject(pData);
      if (mRes.ok) {
        setMedia((await mRes.json().catch(() => null)) as StudioMedia | null);
      }
      setState("loaded");
      setActiveContext({ resourceKind: "media", resourceId: id, resourceLabel: id });
    } catch {
      setState("error");
      setError("Không gọi được BFF /api/studio/*.");
    }
  };

  const createFromSource = async () => {
    if (!tpRequestId.trim() || !tpTitle.trim() || !tpSource.trim()) {
      setTpMsg("Nhập đủ request_id, tiêu đề và source_url.");
      return;
    }
    setTpMsg("Đang gửi...");
    try {
      const res = await fetch("/api/research/to-project", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          request_id: tpRequestId.trim(),
          title: tpTitle.trim(),
          source_url: tpSource.trim(),
        }),
      });
      const data = (await res.json().catch(() => null)) as { id?: string; detail?: { message?: string } } | null;
      if (res.status === 503) {
        setTpMsg("BE chưa cấu hình task_service (503 TASK_SERVICE_UNAVAILABLE) — chưa tạo được task.");
        return;
      }
      if (!res.ok || !data) {
        setTpMsg(`BE trả lỗi HTTP ${res.status}.`);
        return;
      }
      setTpMsg(`Đã tạo task BE: ${data.id ?? "(không rõ id)"}.`);
    } catch {
      setTpMsg("Không gọi được BFF /api/research/to-project.");
    }
  };

  return (
    <div className="h-full overflow-y-auto p-4 sm:p-6">
      <div className="mx-auto max-w-[1280px] space-y-6">
        <div className="space-y-1">
          <h1 className="text-h1 text-[var(--color-text-primary)]">Media Studio</h1>
          <p className="text-[14px] text-[var(--color-text-secondary)]">
            Chỉ hiển thị project thật từ Backend (GET /studio/project/{"{id}"}, /studio/media/{"{id}"}). Không dùng dữ liệu mẫu.
          </p>
        </div>

        <Card className="space-y-3">
          <div className="flex flex-wrap items-end gap-2">
            <div className="flex-1 min-w-[220px] space-y-1">
              <label className="text-[12px] font-medium text-[var(--color-text-secondary)]">
                Video ID (project thật trên BE)
              </label>
              <input
                type="text"
                value={videoId}
                onChange={(e) => setVideoId(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && void load()}
                placeholder="Nhập video_id đã có trên BE..."
                className="h-9 w-full rounded-[6px] bg-[var(--color-surface-2)] border border-[var(--color-border)] px-3 text-[13px] text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-focus-ring)]"
              />
            </div>
            <Button variant="primary" onClick={() => void load()} disabled={state === "loading" || !videoId.trim()}>
              <span>{state === "loading" ? "Đang tải..." : "Tải project từ BE"}</span>
            </Button>
          </div>
        </Card>

        {state === "idle" && (
          <Card className="p-8 text-center">
            <p className="text-[14px] text-[var(--color-text-secondary)]">
              Chưa có project nào. Nhập video_id ở trên để tải project thật từ Backend.
            </p>
          </Card>
        )}

        {state === "missing" && (
          <Card className="p-8 text-center space-y-3">
            <p className="text-[14px] text-[var(--color-text-secondary)]">
              BE không có project cho video_id này (404). Tạo task dựng từ nguồn bên dưới để bắt đầu pipeline thật.
            </p>
            <StatusTag tone="warning">BE-chưa-có-project</StatusTag>
          </Card>
        )}

        {state === "error" && error && (
          <Card className="p-4 border border-[var(--color-error)]/40 bg-[var(--color-error-bg)]/40">
            <p className="text-[13px] text-[var(--color-error)]">{error}</p>
          </Card>
        )}

        {state === "loaded" && project && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <StatusTag tone="success">project thật từ BE</StatusTag>
              <span className="font-mono-tech text-[11px] text-[var(--color-text-muted)]">
                video_id: {project.video_id}
                {project.revision !== undefined ? ` · revision: ${String(project.revision)}` : ""}
              </span>
            </div>
            <Card className="space-y-2">
              <h2 className="text-h4 text-[var(--color-text-primary)]">
                Phân cảnh ({project.segments?.length ?? 0})
              </h2>
              {(project.segments?.length ?? 0) === 0 ? (
                <p className="text-[13px] text-[var(--color-text-muted)]">
                  Project chưa có phân cảnh nào.
                </p>
              ) : (
                <ul className="space-y-1.5">
                  {project.segments?.map((sg, i) => (
                    <li
                      key={i}
                      className="rounded-[6px] bg-[var(--color-surface-2)] border border-[var(--color-border)] p-2.5 text-[12px] text-[var(--color-text-secondary)]"
                    >
                      {sg.label ? String(sg.label) : `Đoạn ${i + 1}`}
                      {sg.startSec !== undefined && (
                        <span className="font-mono-tech text-[11px] text-[var(--color-text-muted)]">
                          {" "}· {String(sg.startSec)}s → {String(sg.endSec ?? "?")}s
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            {media && (
              <Card className="space-y-1">
                <h2 className="text-h4 text-[var(--color-text-primary)]">Media output</h2>
                <p className="font-mono-tech text-[12px] text-[var(--color-text-secondary)] break-all">
                  {media.output}
                </p>
              </Card>
            )}
          </div>
        )}

        <Card className="space-y-3">
          <h2 className="text-h4 text-[var(--color-text-primary)]">
            Tạo task dựng từ nguồn (POST /research/to-project)
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <div className="space-y-1">
              <label className="text-[12px] font-medium text-[var(--color-text-secondary)]">request_id</label>
              <input
                type="text"
                value={tpRequestId}
                onChange={(e) => setTpRequestId(e.target.value)}
                placeholder="vd: req-001"
                className="h-9 w-full rounded-[6px] bg-[var(--color-surface-2)] border border-[var(--color-border)] px-3 text-[13px] text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-focus-ring)]"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[12px] font-medium text-[var(--color-text-secondary)]">Tiêu đề</label>
              <input
                type="text"
                value={tpTitle}
                onChange={(e) => setTpTitle(e.target.value)}
                placeholder="Tiêu đề video"
                className="h-9 w-full rounded-[6px] bg-[var(--color-surface-2)] border border-[var(--color-border)] px-3 text-[13px] text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-focus-ring)]"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[12px] font-medium text-[var(--color-text-secondary)]">source_url</label>
              <input
                type="text"
                value={tpSource}
                onChange={(e) => setTpSource(e.target.value)}
                placeholder="https://..."
                className="h-9 w-full rounded-[6px] bg-[var(--color-surface-2)] border border-[var(--color-border)] px-3 text-[13px] text-[var(--color-text-primary)] focus:outline-none focus:border-[var(--color-focus-ring)]"
              />
            </div>
          </div>
          <Button variant="secondary" onClick={() => void createFromSource()}>
            <span>Tạo task từ BE</span>
          </Button>
          {tpMsg && <p className="text-[13px] text-[var(--color-text-secondary)]">{tpMsg}</p>}
        </Card>
      </div>
    </div>
  );
}
