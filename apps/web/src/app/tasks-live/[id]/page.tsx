"use client";
import { useParams } from "next/navigation";
import { useState } from "react";
import { YoucareShell } from "@/components/youcare/YoucareShell";
import { RuntimeService } from "@/lib/services/runtime.service";
import { useBeApprove, useBeEvents, useBeRestart, useBeResume, useBeRevoke, useBeStop, useBeTask, useBeWaitStop } from "@/hooks/data/useRuntime";

function short(v: unknown): string {
  const s = typeof v === "string" ? v : JSON.stringify(v ?? "");
  return s.length > 500 ? s.slice(0, 500) + "…" : s;
}

function friendly(e: unknown): string {
  const { code, message, status } = RuntimeService.errMessage(e);
  if (status === 404) return "Task không tồn tại (404). Kiểm tra lại ID hoặc danh sách task.";
  if (status === 409) return `Xung đột (${code ?? "409"}): ${message} — reconcile read-only, không post lại.`;
  if (status === 422) return `Dữ liệu chưa hợp lệ (422): ${message}`;
  if (status === 503) return "Chưa nối được BE (503). Kiểm tra BE :8770 rồi thử lại.";
  return `Thất bại (${status ?? "?"}): ${code ? `${code}: ` : ""}${message}`;
}

export default function TaskDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Array.isArray(params?.id) ? params.id[0] : params?.id;
  const task = useBeTask(id, 2000);
  const events = useBeEvents(id, 1500);
  const stop = useBeStop();
  const waitStop = useBeWaitStop();
  const restart = useBeRestart();
  const resume = useBeResume();
  const approve = useBeApprove();
  const revoke = useBeRevoke();
  const [msg, setMsg] = useState("");
  const [approval, setApproval] = useState({ item: "0", scope: "edit", revision: "1" });

  const act = (
    label: string,
    fn: () => { mutate: (v: string, o: { onSuccess: () => void; onError: (e: unknown) => void }) => void },
  ) => {
    setMsg("");
    fn().mutate(id!, {
      onSuccess: () => setMsg(`${label} thành công cho ${id}.`),
      onError: (e) => setMsg(`${label} thất bại: ${friendly(e)}`),
    });
  };

  const pending = stop.isPending || waitStop.isPending || restart.isPending || resume.isPending;

  return (
    <YoucareShell title={`Task ${id ?? "—"}`} subtitle="Chi tiết tác vụ BE — stop / restart / resume / approve, sự kiện realtime.">
      <h1 data-testid="detail-title" style={{ fontSize: 20, fontWeight: 800, margin: 0 }}>Task {id}</h1>
      {task.isLoading ? <p>Đang tải task…</p> : null}
      {task.isError ? (
        <p style={{ color: "#B52E2E" }}>
          {friendly(task.error)}{" "}
          <button type="button" onClick={() => task.refetch()} style={{ textDecoration: "underline" }}>
            Thử lại
          </button>
        </p>
      ) : null}
      {task.data ? (
        <div className="yc-card">
          <p data-testid="detail-status" style={{ marginTop: 0 }}>
            Trạng thái: <b>{task.data.status}</b>
            {task.data.revision !== undefined ? ` · rev ${task.data.revision}` : ""}
            {task.data.error ? ` · ${task.data.error.code}: ${task.data.error.message}` : ""}
          </p>
          {task.data.evidence ? (
            <pre data-testid="detail-evidence" style={{ background: "#fafaff", border: "1px solid #eceaf4", padding: 12, borderRadius: 12, maxWidth: 860, overflow: "auto", fontSize: 12 }}>
              {short(task.data.evidence)}
            </pre>
          ) : (
            <p data-testid="detail-no-evidence" className="yc-sub">Chưa có evidence.</p>
          )}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "8px 0" }}>
            <button className="yc-btn" data-testid="detail-stop" disabled={pending} onClick={() => act("Dừng", () => stop)}>
              Dừng task
            </button>
            <button
              className="yc-btn"
              data-testid="detail-wait-stop"
              disabled={pending}
              onClick={() => {
                setMsg("");
                waitStop.mutate(
                  { id: id!, graceSeconds: 10 },
                  {
                    onSuccess: () => setMsg(`Đã gửi chờ dừng (watchdog 10s) cho ${id}.`),
                    onError: (e) => setMsg(`Chờ dừng thất bại: ${friendly(e)}`),
                  },
                );
              }}
            >
              Chờ dừng (10s)
            </button>
            <button className="yc-btn" data-testid="detail-restart" disabled={pending} onClick={() => act("Khởi động lại", () => restart)}>
              Khởi động lại
            </button>
            <button className="yc-btn" data-testid="detail-resume" disabled={pending} onClick={() => act("Tiếp tục", () => resume)}>
              Tiếp tục
            </button>
          </div>
          <details style={{ maxWidth: 860, margin: "8px 0" }}>
            <summary>Approval (RAM-only — mất sau restart BE, cần duyệt lại)</summary>
            <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap", alignItems: "center" }}>
              <label>
                item{" "}
                <input
                  data-testid="detail-approve-item"
                  value={approval.item}
                  onChange={(e) => setApproval((a) => ({ ...a, item: e.target.value }))}
                  style={{ width: 60, border: "1px solid #eceaf4", borderRadius: 8, padding: "6px 10px", fontFamily: "inherit" }}
                />
              </label>
              <label>
                scope{" "}
                <input
                  data-testid="detail-approve-scope"
                  value={approval.scope}
                  onChange={(e) => setApproval((a) => ({ ...a, scope: e.target.value }))}
                  style={{ width: 120, border: "1px solid #eceaf4", borderRadius: 8, padding: "6px 10px", fontFamily: "inherit" }}
                />
              </label>
              <label>
                revision{" "}
                <input
                  data-testid="detail-approve-rev"
                  value={approval.revision}
                  onChange={(e) => setApproval((a) => ({ ...a, revision: e.target.value }))}
                  style={{ width: 80, border: "1px solid #eceaf4", borderRadius: 8, padding: "6px 10px", fontFamily: "inherit" }}
                />
              </label>
              <button
                className="yc-btn primary"
                data-testid="detail-approve"
                disabled={approve.isPending}
                onClick={() => {
                  setMsg("");
                  approve.mutate(
                    { id: id!, item: Number(approval.item) || 0, scope: approval.scope, revision: Number(approval.revision) || 1 },
                    {
                      onSuccess: (r) => setMsg(`Đã duyệt scope=${r.scope ?? approval.scope} rev=${r.revision ?? approval.revision}. Lưu ý RAM-only — restart BE phải duyệt lại.`),
                      onError: (e) => setMsg(`Duyệt thất bại: ${friendly(e)}`),
                    },
                  );
                }}
              >
                Duyệt
              </button>
              <button
                className="yc-btn"
                data-testid="detail-revoke"
                disabled={revoke.isPending}
                onClick={() => {
                  setMsg("");
                  revoke.mutate(
                    { id: id!, item: Number(approval.item) || 0 },
                    {
                      onSuccess: () => setMsg("Đã thu hồi approval."),
                      onError: (e) => setMsg(`Thu hồi thất bại: ${friendly(e)}`),
                    },
                  );
                }}
              >
                Thu hồi
              </button>
            </div>
          </details>
          {msg ? <p data-testid="detail-msg">{msg}</p> : null}
        </div>
      ) : null}

      <div className="yc-card">
        <h4>Tiến độ / sự kiện</h4>
        {events.isLoading ? <p>Đang tải events…</p> : null}
        {events.isError ? (
          <p style={{ color: "#B52E2E" }}>
            {friendly(events.error)}{" "}
            <button type="button" onClick={() => events.refetch()} style={{ textDecoration: "underline" }}>
              Thử lại
            </button>
          </p>
        ) : null}
        {!events.isLoading && !events.isError && (events.data ?? []).length === 0 ? (
          <p data-testid="detail-events-empty" className="yc-sub">Chưa có sự kiện nào cho task này.</p>
        ) : null}
        <ul data-testid="detail-events" style={{ maxWidth: 860, paddingLeft: 18 }}>
          {(events.data ?? []).map((e) => (
            <li key={e.sequence} data-testid={`detail-event-${e.sequence}`}>
              #{e.sequence} · {e.type} · {e.timestamp} · {short(e.data)}
            </li>
          ))}
        </ul>
      </div>
    </YoucareShell>
  );
}
