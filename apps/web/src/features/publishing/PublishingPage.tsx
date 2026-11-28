"use client";
import { useCallback, useEffect, useState } from "react";
import {
  approveThreads,
  createPublication,
  createRender,
  fetchDayPlan,
  fetchThreadsHistory,
  mapThreadsError,
  prepareThreads,
  publishThreads,
  reconcileThreads,
  type ThreadsApproval,
  type ThreadsHistoryResult,
} from "@/lib/threads/flow";

// Publishing — BE-first, không mock/fixture.
// Luồng: prepare → approve → publish dry-run → reconcile → history.
// Post thật chỉ sau approval tươi (allow_post=true); UNKNOWN → chỉ Reconcile (read-only).
export function PublishingPage() {
  const [assetPath, setAssetPath] = useState("");
  const [projectId, setProjectId] = useState("");
  const [requestId, setRequestId] = useState(`req-${Date.now()}`);
  const [revision, setRevision] = useState(0);
  const [contentHash, setContentHash] = useState("");
  const [text, setText] = useState("");
  const [owner, setOwner] = useState("");
  const [shortcode, setShortcode] = useState("");
  const [approval, setApproval] = useState<ThreadsApproval | null>(null);
  const [publicationId, setPublicationId] = useState(`pub-${Date.now()}`);
  const [attemptId, setAttemptId] = useState(`att-${Date.now()}`);
  const [renderId, setRenderId] = useState("");
  const [msg, setMsg] = useState("");
  const [msgKind, setMsgKind] = useState<"info" | "error">("info");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<ThreadsHistoryResult | null>(null);
  const [dayPlan, setDayPlan] = useState<{ date?: string; status?: string } | null>(null);

  const say = (m: string, kind: "info" | "error" = "info") => {
    setMsg(m);
    setMsgKind(kind);
  };

  const loadDayPlan = useCallback(async () => {
    try {
      setDayPlan(await fetchDayPlan());
    } catch {
      setDayPlan(null);
    }
  }, []);

  useEffect(() => {
    loadDayPlan();
  }, [loadDayPlan]);

  const run = async (fn: () => Promise<string>) => {
    setBusy(true);
    setMsg("");
    try {
      say(await fn());
    } catch (e) {
      const f = mapThreadsError(e);
      say(`${f.code}: ${f.message} Hành động: ${f.action}`, "error");
    } finally {
      setBusy(false);
    }
  };

  const need = (v: string, name: string) => {
    if (!v.trim()) throw new Error(`422: Thiếu ${name}`);
    return v;
  };

  return (
    <div className="h-full overflow-y-auto p-4 sm:p-6">
      <div className="mx-auto max-w-[1080px] space-y-5">
        <div>
          <h1 className="text-h1 text-[var(--color-text-primary)]">Xuất bản (BE thật)</h1>
          <p className="text-[13px] text-[var(--color-text-secondary)]">
            Prepare → Approve → Publish dry-run → Reconcile → History. BE down → lỗi 502,
            không dữ liệu mẫu. Post thật chỉ sau approval tươi. UNKNOWN → chỉ Reconcile (read-only).
            {dayPlan ? ` Day-plan: ${dayPlan.date ?? "?"} (${dayPlan.status ?? "?"})` : " Day-plan: chưa tải được."}
          </p>
        </div>

        {msg ? (
          <p data-testid="publishing-msg" className={msgKind === "error" ? "text-[var(--color-error)]" : "text-[var(--color-success)]"}>
            {msg}
          </p>
        ) : null}

        <section className="rounded-[8px] border border-[var(--color-border)] bg-[var(--color-surface-1)] p-4 space-y-3">
          <h2 className="text-h4">1 · Prepare + Render + Publication</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            <input aria-label="asset_path" placeholder="asset_path" value={assetPath} onChange={(e) => setAssetPath(e.target.value)} className="h-9 rounded-[6px] border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2.5 text-[13px]" />
            <input aria-label="project_id" placeholder="project_id" value={projectId} onChange={(e) => setProjectId(e.target.value)} className="h-9 rounded-[6px] border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2.5 text-[13px]" />
            <input aria-label="request_id" placeholder="request_id" value={requestId} onChange={(e) => setRequestId(e.target.value)} className="h-9 rounded-[6px] border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2.5 text-[13px]" />
            <input aria-label="content_hash" placeholder="content_hash" value={contentHash} onChange={(e) => setContentHash(e.target.value)} className="h-9 rounded-[6px] border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2.5 text-[13px]" />
            <input aria-label="expected_revision" type="number" placeholder="expected_revision" value={revision} onChange={(e) => setRevision(Number(e.target.value))} className="h-9 rounded-[6px] border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2.5 text-[13px]" />
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" disabled={busy} onClick={() => run(async () => {
              const r = await prepareThreads({ asset_path: need(assetPath, "asset_path"), project_id: need(projectId, "project_id"), request_id: need(requestId, "request_id"), expected_revision: revision, content_hash: need(contentHash, "content_hash") });
              if (r.render?.render_id) setRenderId(r.render.render_id);
              return `Prepare OK — render ${r.render?.render_id ?? "?"}${r.replayed ? " (replayed)" : ""}.`;
            })} className="h-9 rounded-[6px] bg-[var(--color-accent)] px-3 text-[13px]">Prepare</button>
            <button type="button" disabled={busy} onClick={() => run(async () => {
              const r = await createRender({ request_id: need(requestId, "request_id"), project_id: need(projectId, "project_id"), expected_revision: revision, content_hash: need(contentHash, "content_hash") });
              setRenderId(r.render_id);
              return `Render OK — ${r.render_id} (${r.status})${r.replayed ? " (replayed)" : ""}.`;
            })} className="h-9 rounded-[6px] border border-[var(--color-border)] px-3 text-[13px]">Tạo render</button>
            <button type="button" disabled={busy} onClick={() => run(async () => {
              const r = await createPublication({ publication_id: need(publicationId, "publication_id"), attempt_id: need(attemptId, "attempt_id"), render_id: need(renderId, "render_id"), channel: "threads" });
              return `Publication OK — ${r.publication_id}/${r.attempt_id} (${r.status})${r.replayed ? " (replayed)" : ""}.`;
            })} className="h-9 rounded-[6px] border border-[var(--color-border)] px-3 text-[13px]">Tạo publication</button>
          </div>
        </section>

        <section className="rounded-[8px] border border-[var(--color-border)] bg-[var(--color-surface-1)] p-4 space-y-3">
          <h2 className="text-h4">2 · Approve intent (scope=threads_post)</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
            <input aria-label="text" placeholder="text" value={text} onChange={(e) => setText(e.target.value)} className="h-9 rounded-[6px] border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2.5 text-[13px]" />
            <input aria-label="owner" placeholder="owner" value={owner} onChange={(e) => setOwner(e.target.value)} className="h-9 rounded-[6px] border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2.5 text-[13px]" />
            <input aria-label="shortcode" placeholder="shortcode" value={shortcode} onChange={(e) => setShortcode(e.target.value)} className="h-9 rounded-[6px] border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2.5 text-[13px]" />
          </div>
          <button type="button" disabled={busy} onClick={() => run(async () => {
            const a = await approveThreads({ text: need(text, "text"), owner: need(owner, "owner"), shortcode: need(shortcode, "shortcode") }, revision);
            setApproval(a);
            return `Approve OK — scope=${a.scope} revision=${a.revision}. Post thật đã mở (approval tươi).`;
          })} className="h-9 rounded-[6px] bg-[var(--color-accent)] px-3 text-[13px]">Duyệt intent</button>
        </section>

        <section className="rounded-[8px] border border-[var(--color-border)] bg-[var(--color-surface-1)] p-4 space-y-3">
          <h2 className="text-h4">3 · Publish (dry-run mặc định) + Reconcile + History</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
            <input aria-label="publication_id" placeholder="publication_id" value={publicationId} onChange={(e) => setPublicationId(e.target.value)} className="h-9 rounded-[6px] border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2.5 text-[13px]" />
            <input aria-label="attempt_id" placeholder="attempt_id" value={attemptId} onChange={(e) => setAttemptId(e.target.value)} className="h-9 rounded-[6px] border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2.5 text-[13px]" />
            <input aria-label="render_id" placeholder="render_id" value={renderId} onChange={(e) => setRenderId(e.target.value)} className="h-9 rounded-[6px] border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2.5 text-[13px]" />
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" disabled={busy} onClick={() => run(async () => {
              const p = await publishThreads({ publication_id: need(publicationId, "publication_id"), attempt_id: need(attemptId, "attempt_id"), render_id: need(renderId, "render_id"), text, owner: need(owner, "owner"), shortcode: need(shortcode, "shortcode"), allow_post: false });
              return `Dry-run OK — ${p.status ?? "xong"} (chưa đăng thật). Dùng Reconcile để đối soát.`;
            })} className="h-9 rounded-[6px] bg-[var(--color-accent)] px-3 text-[13px]">Publish dry-run</button>
            <button type="button" disabled={busy || !approval} title={approval ? "Approval tươi — cho phép post thật" : "Cần duyệt intent trước"} onClick={() => run(async () => {
              if (!approval) throw new Error("422: Cần approval tươi trước khi đăng thật");
              const p = await publishThreads({ publication_id: need(publicationId, "publication_id"), attempt_id: need(attemptId, "attempt_id"), render_id: need(renderId, "render_id"), text, owner: need(owner, "owner"), shortcode: need(shortcode, "shortcode"), approval, allow_post: true });
              return `Post thật: ${p.status ?? "xong"} — đối soát qua History/Reconcile.`;
            })} className="h-9 rounded-[6px] border border-[var(--color-border)] px-3 text-[13px]">Đăng thật (cần approval tươi)</button>
            <button type="button" disabled={busy} onClick={() => run(async () => {
              const r = await reconcileThreads({ text, owner: need(owner, "owner"), shortcode: need(shortcode, "shortcode") });
              return `Reconcile OK — ${r.status ?? "xong"} (read-only, không đăng lại).`;
            })} className="h-9 rounded-[6px] border border-[var(--color-border)] px-3 text-[13px]">Reconcile (read-only)</button>
            <button type="button" disabled={busy} onClick={() => run(async () => {
              const h = await fetchThreadsHistory(need(publicationId, "publication_id"), need(renderId, "render_id"));
              setHistory(h);
              return `History OK — ${h.journals?.length ?? 0} journal.`;
            })} className="h-9 rounded-[6px] border border-[var(--color-border)] px-3 text-[13px]">Xem history</button>
          </div>
          {history ? (
            <div className="text-[12px] font-mono-tech space-y-1">
              {(history.journals ?? []).map((j, i) => (
                <p key={i}>{j.file} · {j.shortcode ?? ""} · {j.status ?? ""} · {j.post_id ?? "no-post-id"}</p>
              ))}
              {(history.journals ?? []).length === 0 ? <p>Chưa có journal nào.</p> : null}
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}
