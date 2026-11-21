"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import MiroNav from "@/components/miro-nav";
import { useReviewTask, useSendChat, useStopTask, useTasks } from "@/hooks/data/useMiro";
import { chatSendSchema, type ChatSendInput } from "@/lib/schemas/miro.schema";

export default function TasksPage() {
  const { data: tasks, isLoading, isError } = useTasks();
  const sendChat = useSendChat();
  const reviewTask = useReviewTask();
  const stopTask = useStopTask();
  const [msg, setMsg] = useState("");

  const form = useForm<ChatSendInput>({
    resolver: zodResolver(chatSendSchema),
    defaultValues: { message: "" },
  });

  const onSend = (input: ChatSendInput) => {
    setMsg("");
    sendChat.mutate(input, {
      onSuccess: () => {
        form.reset();
        setMsg("Đã gửi chat — task mới đang chạy.");
      },
      onError: (e) => setMsg(`Gửi thất bại: ${(e as Error).message}`),
    });
  };

  return (
    <MiroNav>
      <h1 data-testid="tasks-title">Công việc</h1>
      <p>Chat / task / duyệt / dừng. BE sở hữu state qua Query key `tasks`.</p>

      <form
        data-testid="chat-form"
        onSubmit={form.handleSubmit(onSend)}
        style={{ display: "flex", gap: 8, maxWidth: 640, marginBottom: 8 }}
      >
        <input
          data-testid="chat-input"
          {...form.register("message")}
          placeholder="Giao việc cho AI…"
          style={{ flex: 1, border: "1px solid #ccc", borderRadius: 8, padding: "8px 12px" }}
        />
        <button data-testid="chat-send" type="submit" disabled={sendChat.isPending}>
          {sendChat.isPending ? "Đang gửi…" : "Gửi"}
        </button>
      </form>
      {form.formState.errors.message ? (
        <p style={{ color: "#B52E2E" }}>{form.formState.errors.message.message}</p>
      ) : null}
      {msg ? <p data-testid="chat-msg">{msg}</p> : null}

      {isLoading ? <p>Đang tải task…</p> : null}
      {isError ? <p style={{ color: "#B52E2E" }}>Chưa nối được BE.</p> : null}

      <ul data-testid="task-list" style={{ listStyle: "none", padding: 0, maxWidth: 720 }}>
        {(tasks ?? []).map((t) => (
          <li
            key={t.id}
            data-testid={`task-${t.id}`}
            style={{ border: "1px solid #ddd", borderRadius: 10, padding: 12, marginBottom: 8, background: "#fff" }}
          >
            <b>{t.title}</b> <small data-testid={`task-status-${t.id}`}>· {t.status} · r{t.revision}</small>
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <button
                data-testid={`approve-${t.id}`}
                onClick={() =>
                  reviewTask.mutate(
                    { id: t.id, decision: "approve" },
                    { onSuccess: () => setMsg(`Đã duyệt ${t.id}.`), onError: (e) => setMsg(`Duyệt thất bại: ${(e as Error).message}`) },
                  )
                }
              >
                Duyệt
              </button>
              <button
                data-testid={`reject-${t.id}`}
                onClick={() =>
                  reviewTask.mutate(
                    { id: t.id, decision: "reject" },
                    { onSuccess: () => setMsg(`Đã trả ${t.id} về hàng chờ.`), onError: (e) => setMsg(`Thất bại: ${(e as Error).message}`) },
                  )
                }
              >
                Từ chối
              </button>
              <button
                data-testid={`stop-${t.id}`}
                onClick={() =>
                  stopTask.mutate(t.id, {
                    onSuccess: () => setMsg(`Đã dừng ${t.id}.`),
                    onError: (e) => setMsg(`Dừng thất bại: ${(e as Error).message}`),
                  })
                }
              >
                Dừng
              </button>
            </div>
          </li>
        ))}
      </ul>
    </MiroNav>
  );
}
