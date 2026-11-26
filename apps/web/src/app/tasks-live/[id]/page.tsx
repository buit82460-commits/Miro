"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import MiroNav from "@/components/miro-nav";
import { useBeEvents, useBeStop, useBeTask } from "@/hooks/data/useRuntime";

function short(v: unknown): string {
  const s = typeof v === "string" ? v : JSON.stringify(v ?? "");
  return s.length > 500 ? s.slice(0, 500) + "…" : s;
}

export default function TaskDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Array.isArray(params?.id) ? params.id[0] : params?.id;
  const task = useBeTask(id);
  const events = useBeEvents(id);
  const stop = useBeStop();
  const [msg, setMsg] = useState("");

  return (
    <MiroNav>
      <h1 data-testid="detail-title">Task {id}</h1>
      {task.isLoading ? <p>Đang tải task…</p> : null}
      {task.isError ? <p style={{ color: "#B52E2E" }}>Chưa nối được BE.</p> : null}
      {task.data ? (
        <>
          <p data-testid="detail-status">
            Trạng thái: <b>{task.data.status}</b>
            {task.data.error ? ` · ${task.data.error.code}: ${task.data.error.message}` : ""}
          </p>
          {task.data.evidence ? (
            <pre data-testid="detail-evidence" style={{ background: "#f6f6f6", padding: 12, borderRadius: 8, maxWidth: 860, overflow: "auto" }}>
              {short(task.data.evidence)}
            </pre>
          ) : (
            <p data-testid="detail-no-evidence">Chưa có evidence.</p>
          )}
          <button
            data-testid="detail-stop"
            onClick={() =>
              stop.mutate(id!, {
                onSuccess: () => setMsg(`Đã gửi dừng ${id}.`),
                onError: (e) => setMsg(`Dừng thất bại: ${(e as Error).message}`),
              })
            }
          >
            Dừng task
          </button>
          {msg ? <p data-testid="detail-msg">{msg}</p> : null}
        </>
      ) : null}

      <h2>Tiến độ / sự kiện</h2>
      <ul data-testid="detail-events" style={{ maxWidth: 860 }}>
        {(events.data ?? []).map((e) => (
          <li key={e.sequence} data-testid={`detail-event-${e.sequence}`}>
            #{e.sequence} · {e.type} · {e.timestamp} · {short(e.data)}
          </li>
        ))}
      </ul>
    </MiroNav>
  );
}
