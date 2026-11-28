"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useApproveProject, useEditorCommand, useLibrary, useProject, useRender } from "@/hooks/data/useMiro";
import { subtitleSchema, type SubtitleInput } from "@/lib/schemas/miro.schema";
import { StudioService } from "@/lib/services/miro.service";

type Clip = { id: string; kind: string; start: number; duration: number; text?: string };
type Track = { id: string; kind: string; clips: Clip[] };

function EditorInner() {
  const sp = useSearchParams();
  const qp = sp.get("project") ?? "";
  const { data: library } = useLibrary();
  // Repair: fallback trỏ nhầm "p1" (fixture cũ threads-milestone) — khi không có
  // query param và library rỗng/BE down, projectId rỗng → useProject disabled →
  // UI hiện empty-state trung thực, KHÔNG tự load p1 mẫu gây hiểu nhầm.
  const projectId = qp || String((library?.[0] as Record<string, unknown> | undefined)?.id ?? "");
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
        {!projectId && !isLoading ? (
          <p data-testid="editor-empty">
            Chưa chọn project — mở qua ?project=&lt;id&gt; hoặc Thư viện (BE). Không tự mở project mẫu.
          </p>
        ) : null}
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
            <StudioDubPanel projectId={projectId} onDone={(m) => { setMsg(m); refetch(); }} />
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

type StudioSeg = { id: number; start: number; end: number; src_text?: string; tgt_text?: string };

// Panel mới "Studio Dub" dùng API thật (/studio/*). UI cũ phía trên giữ nguyên.
function StudioDubPanel({ projectId, onDone }: { projectId: string; onDone: (m: string) => void }) {
  const [source, setSource] = useState("");
  const [videoId, setVideoId] = useState(projectId);
  const [segs, setSegs] = useState<StudioSeg[]>([]);
  const [srtText, setSrtText] = useState("");
  const [planText, setPlanText] = useState("cắt 10s đầu");
  const [plan, setPlan] = useState<Record<string, unknown> | null>(null);
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);

  const reqId = () => `web-${Date.now().toString(36)}`;
  const summarize = (r: unknown) => {
    const o = r as Record<string, unknown>;
    const job = (o?.job ?? o?.render ?? null) as Record<string, unknown> | null;
    const rev = o?.revision ?? (o?.project as Record<string, unknown> | undefined)?.revision;
    const out = (o?.output ?? (o?.project as Record<string, unknown> | undefined)?.output) as string | undefined;
    return `job=${String(job?.id ?? job?.job_id ?? "—")} status=${String(job?.status ?? o?.status ?? "ok")}`
      + (rev !== undefined ? ` rev=${String(rev)}` : "")
      + (out ? ` out=${out}` : "");
  };
  const failMsg = (e: unknown) =>
    (e as { response?: { data?: { detail?: string; error?: string } } })?.response?.data?.detail
    ?? (e as { response?: { data?: { error?: string } } })?.response?.data?.error
    ?? (e as Error)?.message ?? "lỗi không rõ";

  const run = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(true);
    setInfo("");
    try {
      const r = await fn();
      const line = `${label}: ${summarize(r)}`;
      setInfo(line);
      onDone(line);
    } catch (e) {
      setInfo(`${label} thất bại: ${failMsg(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const reloadSubs = async (vid: string) => {
    const r = await StudioService.loadSubs(vid);
    setSegs((r.segments ?? []) as StudioSeg[]);
  };

  return (
    <section data-testid="studio-dub" style={{ marginTop: 16, border: "1px solid #ddd", borderRadius: 12, padding: 12, background: "#fff" }}>
      <h2 style={{ marginTop: 0 }}>Studio Dub <small>(API thật /studio)</small></h2>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <label>Video ID <input data-testid="studio-video-id" value={videoId} onChange={(e) => setVideoId(e.target.value)} style={{ width: 140 }} /></label>
        <label style={{ flex: 1, minWidth: 240 }}>Source (URL reel/TikTok/YT hoặc path local)
          <input data-testid="studio-source" value={source} onChange={(e) => setSource(e.target.value)} style={{ width: "100%" }} placeholder="https://... hoặc C:\videos\a.mp4" />
        </label>
        <button
          data-testid="studio-download"
          disabled={busy || !source.trim()}
          onClick={() => run("Tải + STT + Dịch", async () => {
            const dl = await StudioService.download(source.trim(), reqId());
            const vid = String((dl as Record<string, unknown>).video_id ?? videoId);
            setVideoId(vid);
            const tr = await StudioService.translate(vid, reqId());
            await reloadSubs(vid);
            return tr;
          })}
        >
          Tải + STT + Dịch
        </button>
      </div>

      <h3>Segments ({segs.length})</h3>
      {segs.length === 0 ? (
        <p><small>Chưa có segments — bấm “Tải + STT + Dịch” hoặc nhập Video ID rồi “Tải lại sub”.</small></p>
      ) : null}
      <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 260, overflow: "auto" }}>
        {segs.map((s) => (
          <div key={s.id} data-testid={`studio-seg-${s.id}`} style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <span style={{ width: 110, fontSize: 12 }}>{s.start.toFixed(1)}–{s.end.toFixed(1)}s</span>
            <input
              data-testid={`studio-seg-tgt-${s.id}`}
              value={s.tgt_text ?? ""}
              onChange={(e) => setSegs((prev) => prev.map((x) => (x.id === s.id ? { ...x, tgt_text: e.target.value } : x)))}
              style={{ flex: 1 }}
              aria-label={`Câu dịch ${s.id}`}
            />
            <span style={{ width: 200, fontSize: 12, color: "#666" }}>{(s.src_text ?? "").slice(0, 60)}</span>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
        <button data-testid="studio-subs-reload" disabled={busy || !videoId} onClick={() => run("Tải lại sub", () => reloadSubs(videoId).then(() => ({ status: "loaded" })))}>Tải lại sub</button>
        <button
          data-testid="studio-subs-save"
          disabled={busy || segs.length === 0}
          onClick={() => run("Lưu sub", () => StudioService.saveSubs(videoId, reqId(), segs.map((s) => ({ id: s.id, start: s.start, end: s.end, tgt_text: s.tgt_text ?? "" }))))}
        >
          Lưu sub đã sửa
        </button>
        <button data-testid="studio-render" disabled={busy || !videoId} onClick={() => run("TTS + Mix + Render", () => StudioService.render(videoId, reqId()))}>
          TTS + Mix + Render
        </button>
        <button data-testid="studio-render-final" disabled={busy || !videoId} onClick={() => run("Render cuối + burn sub", () => StudioService.renderFinal(videoId, reqId()))}>
          Render cuối + burn sub
        </button>
      </div>

      <h3>Import / Export SRT</h3>
      <textarea data-testid="studio-srt" rows={4} value={srtText} onChange={(e) => setSrtText(e.target.value)} placeholder="Dán nội dung SRT vào đây…" style={{ width: "100%" }} />
      <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
        <button data-testid="studio-srt-import" disabled={busy || !videoId || !srtText.trim()} onClick={() => run("Import SRT", () => StudioService.importCaptions(videoId, reqId(), srtText))}>
          Import SRT
        </button>
        <button
          data-testid="studio-srt-export"
          disabled={busy || !videoId}
          onClick={() => run("Export SRT", async () => {
            const r = await StudioService.exportCaptions(videoId);
            const txt = typeof r === "string" ? r : JSON.stringify(r);
            setSrtText(txt.slice(0, 4000));
            return r;
          })}
        >
          Export SRT
        </button>
      </div>

      <h3>Lệnh plan</h3>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <input data-testid="studio-plan-cmd" value={planText} onChange={(e) => setPlanText(e.target.value)} style={{ flex: 1, minWidth: 240 }} placeholder="cắt 10s đầu, thêm chữ ..." />
        <button data-testid="studio-plan" disabled={busy || !videoId || !planText.trim()} onClick={() => run("Plan", async () => {
          const r = await StudioService.plan(videoId, reqId(), planText.trim());
          const pl = (r as Record<string, unknown>).plan as Record<string, unknown> | undefined;
          if (pl) setPlan(pl);
          return r;
        })}>
          Gửi plan
        </button>
        <button data-testid="studio-editor-preview" disabled={busy || !videoId || !plan} onClick={() => run("Preview plan", () => StudioService.editorRender(videoId, reqId(), plan ?? {}, true))}>
          Preview
        </button>
        <button data-testid="studio-editor-final" disabled={busy || !videoId || !plan} onClick={() => run("Final plan", () => StudioService.editorRender(videoId, reqId(), plan ?? {}, false))}>
          Final
        </button>
        <button data-testid="studio-editor-restore" disabled={busy || !videoId} onClick={() => run("Khôi phục", () => StudioService.editorRestore(videoId, reqId()))}>
          Khôi phục
        </button>
      </div>

      <h3>Hiệu ứng / Overlay / Chuyển cảnh</h3>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button data-testid="studio-fx-glow" disabled={busy || !videoId} onClick={() => run("Glow", () => StudioService.overlay(videoId, reqId(), { type: "effect", name: "glow", params: { glow: 0.8 } }))}>
          Glow
        </button>
        <button data-testid="studio-fx-chroma" disabled={busy || !videoId} onClick={() => run("Chroma-key (xóa nền xanh)", () => StudioService.overlay(videoId, reqId(), { type: "effect", name: "chroma_key", params: { color: "0x00FF00", similarity: 0.15 } }))}>
          Xóa nền xanh
        </button>
        <button data-testid="studio-fx-slide" disabled={busy || !videoId} onClick={() => run("Slide mở đầu", () => StudioService.overlay(videoId, reqId(), { type: "transition", name: "slide_left", duration: 1.0 }))}>
          Slide mở đầu
        </button>
        <button data-testid="studio-fx-fade" disabled={busy || !videoId} onClick={() => run("Fade mở đầu", () => StudioService.overlay(videoId, reqId(), { type: "transition", name: "fade", duration: 0.8 }))}>
          Fade mở đầu
        </button>
      </div>

      <h3>Timeline / Audio FX / Nhịp / Tách nhạc / Tracking / Canvas / Export</h3>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button data-testid="studio-timeline-op" disabled={busy || !videoId} onClick={() => run("Timeline op (add_track)", () => StudioService.timelineOp(videoId, reqId(), { type: "add_track", kind: "video" }))}>
          Timeline: thêm track
        </button>
        <button data-testid="studio-timeline-undo" disabled={busy || !videoId} onClick={() => run("Undo", () => StudioService.timelineUndo(videoId, reqId()))}>
          Undo
        </button>
        <button data-testid="studio-timeline-redo" disabled={busy || !videoId} onClick={() => run("Redo", () => StudioService.timelineRedo(videoId, reqId()))}>
          Redo
        </button>
        <button data-testid="studio-audiofx" disabled={busy || !videoId} onClick={() => run("AudioFX bass", () => StudioService.audioFx(videoId, reqId(), "bass", { gain_db: 6 }))}>
          AudioFX: bass
        </button>
        <button data-testid="studio-beat" disabled={busy || !videoId} onClick={() => run("Phân tích nhịp", () => StudioService.beat(videoId, reqId()))}>
          Phân tích nhịp
        </button>
        <button data-testid="studio-separate" disabled={busy || !videoId} onClick={() => run("Tách nhạc", () => StudioService.separate(videoId, reqId()))}>
          Tách nhạc
        </button>
        <button data-testid="studio-track" disabled={busy || !videoId} onClick={() => run("Tracking ROI", () => StudioService.track(videoId, reqId(), { x: 0.4, y: 0.4, w: 0.2, h: 0.2 }))}>
          Tracking ROI
        </button>
        <button data-testid="studio-canvas" disabled={busy || !videoId} onClick={() => run("Canvas 9:16", () => StudioService.canvasSet(videoId, reqId(), "9:16"))}>
          Canvas 9:16
        </button>
        <button data-testid="studio-export-plan" disabled={busy || !videoId} onClick={() => run("Kế hoạch export", () => StudioService.exportPlan(videoId, reqId(), {}, true))}>
          Kế hoạch export
        </button>
        <button data-testid="studio-export-ladder" disabled={busy || !videoId} onClick={() => run("Ladder 480p-1080p", () => StudioService.exportLadder(videoId, reqId(), ["480p", "720p", "1080p"]))}>
          Ladder 480p–1080p
        </button>
        <button data-testid="studio-live-preview" disabled={busy || !videoId} onClick={() => run("Preview nhanh", () => StudioService.livePreview(videoId, reqId()))}>
          Preview nhanh
        </button>
      </div>

      {info ? <p data-testid="studio-info">{info}</p> : null}
      {busy ? <p>Đang chạy…</p> : null}
    </section>
  );
}
