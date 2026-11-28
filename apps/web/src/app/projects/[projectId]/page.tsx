"use client";
import { useParams } from "next/navigation";
import { YoucareShell, EmptyState } from "@/components/youcare/YoucareShell";
import { useProject } from "@/hooks/data/useMiro";
export default function ProjectDetailPage() {
  const p = useParams<{ projectId: string }>();
  const id = Array.isArray(p?.projectId) ? p.projectId[0] : p?.projectId;
  const d = useProject(id);
  return (
    <YoucareShell title={`Dự án ${id ?? "—"}`} subtitle="Chi tiết project từ BE.">
      {d.isPending ? <EmptyState text="Đang tải từ BE…" /> : null}
      {d.isError ? <EmptyState text="Không tải được project (BE :8770)." /> : null}
      {d.data ? <div className="yc-card"><pre style={{ fontSize: 12, whiteSpace: "pre-wrap" }}>{JSON.stringify(d.data, null, 2)?.slice(0, 3000)}</pre></div> : null}
    </YoucareShell>
  );
}
