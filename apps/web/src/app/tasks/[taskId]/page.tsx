"use client";
import { useParams } from "next/navigation";
import { YoucareShell, EmptyState } from "@/components/youcare/YoucareShell";
import { useBeTask, useBeEvents } from "@/hooks/data/useRuntime";
export default function TaskIdAliasPage() {
  const params = useParams<{ taskId: string }>();
  const id = Array.isArray(params?.taskId) ? params.taskId[0] : params?.taskId;
  const t = useBeTask(id, 2000);
  const e = useBeEvents(id, 1500);
  return (
    <YoucareShell title={`Task ${id ?? "—"}`} subtitle="Alias của /tasks-live/[id] — cùng BE state.">
      {t.isError ? <EmptyState text="Không tải được task (BE :8770)." /> : null}
      {t.data ? <div className="yc-card"><b>{t.data.id}</b> · {t.data.status} · {(e.data ?? []).length} events · <a className="yc-btn" href={`/tasks-live/${id}`}>Mở live</a></div> : null}
    </YoucareShell>
  );
}
