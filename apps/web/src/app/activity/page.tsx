"use client";
import { useMemo } from "react";
import { YoucareShell, StatCard, EmptyState } from "@/components/youcare/YoucareShell";
import { useBeTasks } from "@/hooks/data/useRuntime";
export default function ActivityPageRoute() {
  const q = useBeTasks(50, 5000);
  const list: any[] = useMemo(() => (Array.isArray(q.data) ? q.data as any[] : []), [q.data]);
  return (
    <YoucareShell title="Hoạt động" subtitle="Nhật ký từ events task BE — không bịa log.">
      <div className="yc-stats">
        <StatCard label="Tasks theo dõi" value={q.isError ? "—" : q.isPending ? "…" : String(list.length)} sub="recent 50" tone="blue" />
        <StatCard label="Có lỗi" value={String(list.filter((t) => t.error).length)} sub="error != null" />
        <StatCard label="Có evidence" value={String(list.filter((t) => t.evidence).length)} sub="đã đối soát" />
        <StatCard label="BE" value={q.isError ? "Down" : "OK"} sub=":8770" />
      </div>
      {q.isError ? <EmptyState text="Không tải được activity — BE :8770 chưa nối." /> : null}
      <div className="yc-card">
        <h4>Dòng thời gian</h4>
        <div style={{ display: "grid", gap: 8, marginTop: 10 }}>
          {list.slice(0, 20).map((t) => (
            <div key={t.id} style={{ border: "1px solid #eceaf4", borderRadius: 12, padding: "10px 14px", fontSize: 14, background: "#fafaff" }}>
              <b>{String(t.id).slice(0, 18)}…</b> · {t.status} · {t.updated_at ?? t.created_at ?? "—"}
            </div>
          ))}
          {list.length === 0 && !q.isPending && !q.isError ? <p className="yc-sub">Chưa có hoạt động nào.</p> : null}
        </div>
      </div>
    </YoucareShell>
  );
}
