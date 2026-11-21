"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useApproveProject, useEditorCommand, useLibrary, useProject, useRender } from "@/hooks/data/useMiro";
import { subtitleSchema, type SubtitleInput } from "@/lib/schemas/miro.schema";

type Clip = { id: string; kind: string; start: number; duration: number; text?: string };
type Track = { id: string; kind: string; clips: Clip[] };

function EditorInner() {
  const sp = useSearchParams();
  const qp = sp.get("project") ?? "";
  const { data: library } = useLibrary();
  const projectId = qp || String((library?.[0] as Record<string, unknown> | undefined)?.id ?? "p1");
  const { data: project, isLoading, isError, refetch } = useProject(projectId);
  const command = useEditorCommand(projectId);
  const renderMut = useRender(projectId);
  const approveMut = useApproveProject(projectId);

  // ---- Local-only state: playhead + kéo-thả. Thả mới gửi 1 command có revision. ----
  const [playhead, setPlayhead] = useState(0);
  const [selClip, setSelClip] = useState<(Clip & { track_id: string }) | null>(null);
  const [sidebarHidden, setSidebarHidden] = useState(false);
  const [msg, setMsg] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const dragClip = useRef<(Clip & { track_id: string }) | null>(null);

  const p = project as unknown as {
    title?: string;
    revision?: number;
    duration?: number;
    canvas?: { width: number; height: number };
    tracks?: Track[];
    render?: { job_id: string; status: string; preview: boolean };
    approved?: boolean;
  } | undefined;
  const revision = p?.revision;
  const tracks = p?.tracks ?? [];

  const runCommand = (operation: Record<string, unknown>, okMsg: string) => {
    setMsg("");
    command.mutate(
      { operation, expected_revision: revision },
      {
        onSuccess: () => {
          setMsg(okMsg);
          refetch();
        },
        onError: (e) => setMsg(`Thất bại: ${(e as Error).message}`),
      },
    );
  };

  const subForm = useForm<SubtitleInput>({
    resolver: zodResolver(subtitleSchema),
    defaultValues: { start: 0, end: 2, text: "" },
  });

  const onDropToTimeline = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const clip = dragClip.current;
    if (!clip) return;
    // 1 lần thả = 1 command duy nhất, kèm revision hiện tại.
    runCommand({ type: "move_clip", clip_id: clip.id, start: Math.max(0, Math.round(playhead * 10) / 10) }, `Đã thả clip về ${playhead.toFixed(1)}s.`);
    dragClip.current = null;
  };

  return (
    <div style={{ display: "flex", minHeight: "100vh" }} data-testid="editor-root">
      {!sidebarHidden ? (
        <aside data-testid="editor-sidebar" style={{ width: 200, borderRight: "1px solid #ddd", padding: 16, background: "#fff" }}>
          <Link href="/" style={{ fontWeight: 800, fontSize: 18, textDecoration: "none" }}>
            Miro
          </Link>
          <nav style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 12 }}>
            <Link href="/">Công việc</Link>
            <Link href="/library">Thư viện</Link>
            <Link href="/publish">Xuất bản</Link>
            <Link href="/settings">Cài đặt</Link>
          </nav>
        </aside>
      ) : null}

      <div style={{ flex: 1, padding: 16 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12 }}>
          <h1 data-testid="editor-title" style={{ margin: 0 }}>
            Editor {p ? `— ${p.title} r${revision}` : ""}
          </h1>
          <button data-testid="toggle-sidebar" onClick={() => setSidebarHidden((v) => !v)}>
            {sidebarHidden ? "Hiện sidebar" : "Ẩn sidebar"}
          </button>
          <Link data-testid="back-tasks" href="/">
            ← Công việc
          </Link>
        </div>

        {isLoading ? <p>Đang tải project…</p> : null}
        {isError ? <p style={{ color: "#B52E2E" }}>Chưa nối được BE.</p> : null}
        {msg ? <p data-testid="editor-msg">{msg}</p> : null}

        {p ? (
          <>
            <div style={{ display: "flex", gap: 16 }}>
              {/* Preview */}
              <div data-testid="preview" style={{ flex: 1, background: "#111", color: "#fff", borderRadius: 12, padding: 24, minHeight: 220 }}>
                PREVIEW {p.canvas?.width}x{p.canvas?.height} · r{revision}
                <br />
                <span style={{ fontSize: 12 }}>
                  playhead {playhead.toFixed(1)}s / {Number(p.duration ?? 0).toFixed(1)}s
                </span>
                <br />
                <span data-testid="render-status" style={{ fontSize: 12 }}>
                  {p.render ? `job ${p.render.job_id} · ${p.render.status}` : "chưa render"}
                  {p.approved ? " · đã duyệt" : ""}
                </span>
              </div>

              {/* Thuộc tính */}
              <div data-testid="inspector" style={{ width: 300, border: "1px solid #ddd", borderRadius: 12, padding: 12, background: "#fff" }}>
                <h3 style={{ marginTop: 0 }}>Thuộc tính {selClip ? `— ${selClip.id}` : ""}</h3>
                {!selClip ? (
                  <p>Bấm một clip trên timeline để sửa phụ đề.</p>
                ) : (
                  <form
                    data-testid="subtitle-form"
                    onSubmit={subForm.handleSubmit((patch) =>
                      runCommand(
                        { type: "update_subtitle", clip_id: selClip.id, text: patch.text, start: patch.start, duration: Math.max(0.5, patch.end - patch.start) },
                        "Đã sửa phụ đề.",
                      ),
                    )}
                  >
                    <label>
                      Bắt đầu (s) <input data-testid="sub-start" type="number" step="any" {...subForm.register("start")} />
                    </label>
                    <br />
                    <label>
                      Kết thúc (s) <input data-testid="sub-end" type="number" step="any" {...subForm.register("end")} />
                    </label>
                    <br />
                    <label>
                      Nội dung{" "}
                      <textarea data-testid="sub-text" rows={2} {...subForm.register("text")} placeholder="Nội dung phụ đề" />
                    </label>
                    {subForm.formState.errors.text ? (
                      <p style={{ color: "#B52E2E" }}>{subForm.formState.errors.text.message}</p>
                    ) : null}
                    <br />
                    <button data-testid="sub-save" type="submit" disabled={command.isPending}>
                      {command.isPending ? "Đang lưu…" : "Lưu phụ đề"}
                    </button>
                  </form>
                )}
              </div>
            </div>

            <div style={{ display: "flex", gap: 8, margin: "12px 0" }}>
              <button data-testid="playhead-back" onClick={() => setPlayhead((v) => Math.max(0, v - 1))}>⏮</button>
              <span data-testid="playhead-value">{playhead.toFixed(2)}s</span>
              <button data-testid="playhead-fwd" onClick={() => setPlayhead((v) => v + 1)}>⏭</button>
              <label>
                Con trỏ (giây){" "}
                <input
                  data-testid="playhead-input"
                  type="number"
                  step="any"
                  value={playhead}
                  onChange={(e) => setPlayhead(Number(e.target.value))}
                />
              </label>
            </div>

            {/* Timeline */}
            <div
              data-testid="timeline"
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDropToTimeline}
              style={{ border: dragOver ? "2px dashed #16161a" : "1px solid #ddd", borderRadius: 12, padding: 12, background: "#fff" }}
            >
              <strong>Timeline</strong> <small>(kéo clip rồi thả — chỉ gửi 1 command khi thả)</small>
              {tracks.map((t) => (
                <div key={t.id} data-testid={`track-${t.id}`} style={{ marginTop: 8 }}>
                  <span style={{ fontWeight: 700 }}>{t.kind.toUpperCase()}</span>
                  <div style={{ display: "flex", gap: 8, marginTop: 4, flexWrap: "wrap" }}>
                    {(t.clips ?? []).map((c) => (
                      <span
                        key={c.id}
                        data-testid={`clip-${c.id}`}
                        draggable
                        onDragStart={() => {
                          dragClip.current = { ...c, track_id: t.id };
                        }}
                        onClick={() => {
                          setSelClip({ ...c, track_id: t.id });
                          setPlayhead(Number(c.start ?? 0));
                          subForm.reset({ start: Number(c.start ?? 0), end: Number(c.start ?? 0) + Number(c.duration ?? 2), text: c.text ?? "" });
                        }}
                        style={{
                          border: selClip?.id === c.id ? "2px solid #16161a" : "1px solid #999",
                          borderRadius: 8,
                          padding: "6px 10px",
                          cursor: "grab",
                          background: c.kind === "text" ? "#fff8d6" : "#eef4ff",
                        }}
                      >
                        {String(c.text ?? c.kind).slice(0, 24)} · {Number(c.start ?? 0).toFixed(1)}–
                        {Number((c.start ?? 0) + (c.duration ?? 0)).toFixed(1)}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button
                data-testid="render-preview"
                disabled={renderMut.isPending}
                onClick={() =>
                  renderMut.mutate(true, {
                    onSuccess: (np) => {
                      setMsg(`Đã gửi preview — job ${(np as unknown as { job: { id: string } }).job.id}.`);
                      refetch();
                    },
                    onError: (e) => setMsg(`Preview thất bại: ${(e as Error).message}`),
                  })
                }
              >
                ▶ Render preview
              </button>
              <button
                data-testid="render-final"
                disabled={renderMut.isPending}
                onClick={() =>
                  renderMut.mutate(false, {
                    onSuccess: (np) => {
                      setMsg(`Đã render bản cuối — job ${(np as unknown as { job: { id: string } }).job.id}.`);
                      refetch();
                    },
                    onError: (e) => setMsg(`Render thất bại: ${(e as Error).message}`),
                  })
                }
              >
                Xuất bản cuối ⬆
              </button>
              <button
                data-testid="approve-project"
                disabled={approveMut.isPending}
                onClick={() =>
                  approveMut.mutate(undefined, {
                    onSuccess: () => {
                      setMsg("Đã duyệt bản cuối.");
                      refetch();
                    },
                    onError: (e) => setMsg(`Duyệt thất bại: ${(e as Error).message}`),
                  })
                }
              >
                Duyệt bản cuối
              </button>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}

export default function EditorPage() {
  return (
    <Suspense>
      <EditorInner />
    </Suspense>
  );
}
