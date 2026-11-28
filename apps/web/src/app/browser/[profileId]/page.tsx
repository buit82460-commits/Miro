"use client";
import { useParams } from "next/navigation";
import { useMemo } from "react";
import { YoucareShell, EmptyState } from "@/components/youcare/YoucareShell";
import { useRuntimeStatus } from "@/hooks/data/useRuntime";
export default function BrowserProfilePage() {
  const p = useParams<{ profileId: string }>();
  const id = Array.isArray(p?.profileId) ? p.profileId[0] : p?.profileId;
  const s = useRuntimeStatus(10000);
  const tabs = useMemo(() => s.data?.bridge?.tabs ?? [], [s.data]);
  const mine = tabs.filter((t: any) => String(t.browser ?? "").includes(String(id ?? "")) || String(t.tab) === String(id));
  return (
    <YoucareShell title={`Trình duyệt ${id ?? "—"}`} subtitle="Tab thuộc profile — read-only từ bridge BE.">
      {s.isError ? <EmptyState text="Không nối BE :8770." /> : null}
      <div className="yc-card"><h4>Tabs ({mine.length})</h4>
      {mine.map((t: any) => <div key={`${t.browser}-${t.tab}`} style={{ border: "1px solid #eceaf4", borderRadius: 12, padding: "10px 14px", marginTop: 8, fontSize: 14 }}>tab {t.tab} · {t.title || t.url}</div>)}
      {mine.length === 0 && !s.isPending ? <p className="yc-sub">Không có tab nào của profile này trong bridge.</p> : null}</div>
    </YoucareShell>
  );
}
