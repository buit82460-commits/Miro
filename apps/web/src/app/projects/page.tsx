"use client";
import { useState } from "react";
import { YoucareShell, EmptyState, StatCard } from "@/components/youcare/YoucareShell";
import { useLibrary, useProject } from "@/hooks/data/useMiro";
export default function ProjectsPageRoute() {
  const lib = useLibrary();
  const [id, setId] = useState("");
  const detail = useProject(id || undefined);
  const items: any[] = Array.isArray(lib.data) ? lib.data as any[] : [];
  return (
    <YoucareShell title="Dự án" subtitle="Library + chi tiết project từ BE thật." actions={<button className="yc-btn" onClick={() => lib.refetch()}>Tải lại</button>}>
      <div className="yc-stats">
        <StatCard label="Projects (BE)" value={lib.isError ? "—" : lib.isPending ? "…" : String(items.length)} sub="library" tone="blue" />
        <StatCard label="Đã chọn" value={id ? id.slice(0, 12) + "…" : "—"} sub="chi tiết project" />
        <StatCard label="Revision" value={String((detail.data as any)?.revision ?? "—")} sub="expected_revision" />
        <StatCard label="BE" value={lib.isError ? "Down" : "OK"} sub=":8770" />
      </div>
      {lib.isError ? <EmptyState text="Không nối được BE :8770. Kiểm tra BE rồi tải lại." /> : null}
      <div className="yc-bottom">
        <div>
          <div className="yc-btitle">Danh sách</div>
          {!lib.isError && lib.isPending ? <EmptyState text="Đang tải từ BE…" /> : null}
          <div style={{ display: "grid", gap: 8 }}>
            {items.slice(0, 20).map((p: any, i: number) => (
              <button key={String(p.id ?? p.video_id ?? i)} onClick={() => setId(String(p.id ?? p.video_id ?? ""))} className="yc-row">
                <div><b style={{ fontSize: 13 }}>{String(p.id ?? p.video_id ?? p.title ?? `item-${i}`)}</b></div>
              </button>
            ))}
            {items.length === 0 && !lib.isPending && !lib.isError ? <EmptyState text="Chưa có project nào từ BE." /> : null}
          </div>
        </div>
        <div className="yc-detail">
          <small>Chi tiết</small>
          {!id ? <div style={{ marginTop: 12 }}>Chọn một project.</div> : detail.isPending ? <div style={{ marginTop: 12 }}>Đang tải…</div> : detail.isError ? <div style={{ marginTop: 12 }}>Không tải được project.</div> : (
            <pre style={{ marginTop: 12, fontSize: 12, whiteSpace: "pre-wrap" }}>{JSON.stringify(detail.data, null, 2)?.slice(0, 2000)}</pre>
          )}
        </div>
      </div>
    </YoucareShell>
  );
}
