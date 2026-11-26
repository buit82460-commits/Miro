"use client";

import Link from "next/link";
import { useState } from "react";
import MiroNav from "@/components/miro-nav";
import { useBeTasks, useRunMessage } from "@/hooks/data/useRuntime";

const SAMPLES = [
  { label: "Tìm kiếm mẫu", message: "tim kiem tiktok KANS 377 tong hop 5 video" },
  { label: "Kiểm tra tài khoản", message: "kiem tra tai khoan tiktok dang nhap" },
];

export default function TasksLivePage() {
  const { data: tasks } = useBeTasks();
  const run = useRunMessage();
  const [message, setMessage] = useState("");
  const [videoUrl, setVideoUrl] = useState("");
  const [out, setOut] = useState("");

  const send = (msg: string) => {
    setOut("");
    run.mutate(
      { message: msg, tabId: 0 },
      {
        onSuccess: (r) =>
          setOut(
            r.ok
              ? `OK - route=${r.route?.job_type} - evidence=${r.evidence ? "co" : "khong"}${
                  r.task_id ? ` - task ${r.task_id}` : ""
                }`
              : `Loi: ${r.error}`,
          ),
        onError: (e) => setOut(`Gui that bai: ${(e as Error).message}`),
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
    <MiroNav>
      <h1 data-testid="live-title">Giao viec</h1>
      <p>
        Nhiem vu capability da nghiem thu (actor/video/search TikTok) qua{" "}
        <code>POST /tasks/run-message</code>. BE so huu state; chuyen trang khong mat task.
      </p>
      <div style={{ display: "flex", gap: 8, maxWidth: 720, marginBottom: 8 }}>
        <input
          data-testid="live-input"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="VD: tim kiem tiktok KANS 377 5 video"
          style={{ flex: 1, border: "1px solid #ccc", borderRadius: 8, padding: "8px 12px" }}
        />
        <button data-testid="live-send" onClick={onSend} disabled={run.isPending || !message.trim()}>
          {run.isPending ? "Dang chay..." : "Giao viec"}
        </button>
      </div>

      <h2 style={{ marginTop: 16 }}>Phân tích video (Manual Control)</h2>
      <p>Dán URL video TikTok — Miro tự phân tích, không cần tab hay cú pháp kỹ thuật.</p>
      <div style={{ display: "flex", gap: 8, maxWidth: 720, marginBottom: 8 }}>
        <input
          data-testid="live-video-url"
          value={videoUrl}
          onChange={(e) => setVideoUrl(e.target.value)}
          placeholder="https://www.tiktok.com/@.../video/..."
          style={{ flex: 1, border: "1px solid #ccc", borderRadius: 8, padding: "8px 12px" }}
        />
        <button
          data-testid="live-analyze-url"
          onClick={onAnalyzeUrl}
          disabled={run.isPending || !videoUrl.trim()}
        >
          {run.isPending ? "Đang phân tích..." : "Phân tích video"}
        </button>
      </div>
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        {SAMPLES.map((s) => (
          <button key={s.label} data-testid={`live-sample-${s.label}`} onClick={() => send(s.message)} disabled={run.isPending}>
            {s.label}
          </button>
        ))}
      </div>
      {out ? <p data-testid="live-out">{out}</p> : null}

      <h2>Task moi nhat (BE)</h2>
      <ul data-testid="live-task-list" style={{ listStyle: "none", padding: 0, maxWidth: 720 }}>
        {(tasks ?? []).map((t) => (
          <li
            key={t.id}
            data-testid={`live-task-${t.id}`}
            style={{ border: "1px solid #ddd", borderRadius: 10, padding: 12, marginBottom: 8, background: "#fff" }}
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
    </MiroNav>
  );
}
