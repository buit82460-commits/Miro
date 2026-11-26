"use client";

import Link from "next/link";
import { useState } from "react";
import MiroNav from "@/components/miro-nav";
import { useBeTasks, useRunMessage } from "@/hooks/data/useRuntime";

export default function TasksLivePage() {
  const { data: tasks } = useBeTasks();
  const run = useRunMessage();
  const [message, setMessage] = useState("");
  const [tabId, setTabId] = useState("0");
  const [out, setOut] = useState("");

  const onSend = () => {
    setOut("");
    run.mutate(
      { message, tabId: Number(tabId) || 0 },
      {
        onSuccess: (r) =>
          setOut(
            r.ok
              ? `OK - route=${r.route?.job_type} - evidence=${r.evidence ? "rea-eye" : "khong"}`
              : `Loi: ${r.error}`,
          ),
        onError: (e) => setOut(`Gui that bai: ${(e as Error).message}`),
      },
    );
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
        <input
          data-testid="live-tab"
          value={tabId}
          onChange={(e) => setTabId(e.target.value)}
          placeholder="tab_id (0 = tu tim)"
          style={{ width: 140, border: "1px solid #ccc", borderRadius: 8, padding: "8px 12px" }}
        />
        <button data-testid="live-send" onClick={onSend} disabled={run.isPending || !message.trim()}>
          {run.isPending ? "Dang chay..." : "Giao viec"}
        </button>
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
            </small>
          </li>
        ))}
      </ul>
    </MiroNav>
  );
}
