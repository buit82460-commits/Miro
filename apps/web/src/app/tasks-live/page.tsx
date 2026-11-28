"use client";

import Link from "next/link";
import { useState } from "react";
import { YoucareShell } from "@/components/youcare/YoucareShell";
import { RuntimeService } from "@/lib/services/runtime.service";
import { useBeTasks, useRunMessage } from "@/hooks/data/useRuntime";

const SAMPLES = [
  { label: "Tìm kiếm mẫu", message: "tim kiem tiktok tong hop 5 video" },
  { label: "Kiểm tra tài khoản", message: "kiem tra tai khoan tiktok dang nhap" },
];

export default function TasksLivePage() {
  const {
    data: tasks,
    isLoading,
    isError,
    error: tasksError,
    refetch,
  } = useBeTasks(20, 2000);
  const run = useRunMessage();
  const [message, setMessage] = useState("");
  const [tabId, setTabId] = useState("0");
  const [limit, setLimit] = useState("5");
  const [videoUrl, setVideoUrl] = useState("");
  const [out, setOut] = useState("");
  const [lastRoute, setLastRoute] = useState("");

  const send = (msg: string) => {
    setOut("");
    setLastRoute("");
    const tid = Number.parseInt(tabId, 10);
    const lim = Number.parseInt(limit, 10);
    run.mutate(
      {
        message: msg,
        tabId: Number.isFinite(tid) ? tid : 0,
        limit: Number.isFinite(lim) ? lim : undefined,
      },
      {
        onSuccess: (r) => {
          setLastRoute(r.route?.job_type ?? "");
          if (r.ok) {
            setOut(
              `OK - route=${r.route?.job_type ?? "?"} - evidence=${r.evidence ? "co" : "khong"}${
                r.task_id ? ` - task ${r.task_id}` : ""
              }`,
            );
          } else if (r.error === "TAB_UNKNOWN") {
            setOut(
              `TAB_UNKNOWN: tab chưa được extension quan sát sau reload. Task ${r.task_id ?? "?"} đã chốt NEEDS_ATTENTION — kiểm tra tab/Bridge rồi giao việc lại, KHÔNG bấm gửi lặp.`,
            );
          } else if (r.error === "NO_ROUTE_MATCH") {
            setOut(`Không khớp route — task ${r.task_id ?? "?"} đã tạo để khỏi mất dấu vết (route=${r.route?.job_type ?? "?"}).`);
          } else {
            setOut(`Lỗi: ${r.error ?? "unknown"}${r.task_id ? ` - task ${r.task_id} (reconcile read-only)` : ""}`);
          }
        },
        onError: (e) => {
          const { code, message: m, status } = RuntimeService.errMessage(e);
          if (status === 503) {
            setOut(`Chưa nối được BE (503). Kiểm tra BE :8770 rồi thử lại. Chi tiết: ${code ?? m}`);
          } else {
            setOut(`Gửi thất bại (${status ?? "?"}): ${code ? `${code}: ` : ""}${m}`);
          }
        },
      },
    );
  };

  const onSend = () => {
    if (message.trim()) send(message.trim());
  };

  const onAnalyzeUrl = () => {
    const u = videoUrl.trim();
    if (!u) return;
    send(`phan tich video tiktok ${u}`);
  };

  return (
    <YoucareShell
      title="Giám sát live"
      subtitle="Nhiệm vụ capability qua POST /tasks/run-message. BE sở hữu state; chuyển trang không mất task."
      actions={<Link className="yc-btn primary" href="/tasks">Mở tác vụ</Link>}
    >
      <h1 data-testid="live-title" style={{ fontSize: 20, fontWeight: 800, margin: 0 }}>Giao việc</h1>
      <div className="yc-card" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <input
          data-testid="live-input"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="VD: tim kiem tiktok 5 video"
          className="yc-input"
          style={{ flex: 1, minWidth: 220, border: "1px solid #eceaf4", borderRadius: 12, padding: "10px 14px", fontFamily: "inherit", fontSize: 14 }}
        />
        <input
          data-testid="live-tab"
          value={tabId}
          onChange={(e) => setTabId(e.target.value)}
          placeholder="tab_id"
          inputMode="numeric"
          title="tab_id (int, bắt buộc — 0 = autonomous)"
          style={{ width: 90, border: "1px solid #eceaf4", borderRadius: 12, padding: "10px 12px", fontFamily: "inherit", fontSize: 14 }}
        />
        <input
          data-testid="live-limit"
          value={limit}
          onChange={(e) => setLimit(e.target.value)}
          placeholder="limit"
          inputMode="numeric"
          title="limit (tùy chọn)"
          style={{ width: 80, border: "1px solid #eceaf4", borderRadius: 12, padding: "10px 12px", fontFamily: "inherit", fontSize: 14 }}
        />
        <button className="yc-btn primary" data-testid="live-send" onClick={onSend} disabled={run.isPending || !message.trim()}>
          {run.isPending ? "Đang chạy..." : "Giao việc"}
        </button>
      </div>
      {run.isPending ? <p data-testid="live-loading">Đang gửi tới BE…</p> : null}

      <div className="yc-card">
        <h4>Phân tích video (Manual Control)</h4>
        <p className="yc-sub">Dán URL video TikTok — Miro tự phân tích, không cần tab hay cú pháp kỹ thuật.</p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            data-testid="live-video-url"
            value={videoUrl}
            onChange={(e) => setVideoUrl(e.target.value)}
            placeholder="https://www.tiktok.com/@.../video/..."
            style={{ flex: 1, minWidth: 220, border: "1px solid #eceaf4", borderRadius: 12, padding: "10px 14px", fontFamily: "inherit", fontSize: 14 }}
          />
          <button
            className="yc-btn"
            data-testid="live-analyze-url"
            onClick={onAnalyzeUrl}
            disabled={run.isPending || !videoUrl.trim()}
          >
            {run.isPending ? "Đang phân tích..." : "Phân tích video"}
          </button>
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
          {SAMPLES.map((s) => (
            <button className="yc-btn" key={s.label} data-testid={`live-sample-${s.label}`} onClick={() => send(s.message)} disabled={run.isPending}>
              {s.label}
            </button>
          ))}
        </div>
        {out ? <p data-testid="live-out">{out}</p> : null}
        {lastRoute ? <p data-testid="live-route">route: {lastRoute}</p> : null}
      </div>

      <div className="yc-card">
        <h4>Task mới nhất (BE)</h4>
        {isLoading ? <p data-testid="live-tasks-loading">Đang tải task…</p> : null}
        {isError ? (
          <p data-testid="live-tasks-error" style={{ color: "#B52E2E" }}>
            {(() => {
              const { status } = RuntimeService.errMessage(tasksError);
              return status === undefined
                ? "Chưa nối được BE (http://127.0.0.1:8770 unreachable). Kiểm tra BE rồi "
                : `BE lỗi (${status}). Kiểm tra BE rồi `;
            })()}
            <button type="button" onClick={() => refetch()} style={{ textDecoration: "underline" }}>
              thử lại
            </button>
            .
          </p>
        ) : null}
        {!isLoading && !isError && (tasks ?? []).length === 0 ? (
          <p data-testid="live-tasks-empty">
            Chưa có task nào. Giao việc đầu tiên ở form trên.
          </p>
        ) : null}
        <ul data-testid="live-task-list" style={{ listStyle: "none", padding: 0, margin: "12px 0 0", display: "grid", gap: 8 }}>
          {(tasks ?? []).map((t) => (
            <li
              key={t.id}
              data-testid={`live-task-${t.id}`}
              style={{ border: "1px solid #eceaf4", borderRadius: 12, padding: 12, background: "#fafaff" }}
            >
              <Link data-testid={`live-open-${t.id}`} href={`/tasks-live/${t.id}`} style={{ fontWeight: 700 }}>
                {t.id}
              </Link>{" "}
              <small data-testid={`live-status-${t.id}`}>
                - {t.status}
                {t.error ? ` - ${t.error.code}` : ""}
                {t.evidence ? " - co evidence" : ""}
              </small>
            </li>
          ))}
        </ul>
      </div>
    </YoucareShell>
  );
}
