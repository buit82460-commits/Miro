"use client";
import { useMemo } from "react";
import Link from "next/link";
import { YoucareShell, StatCard, EmptyState } from "@/components/youcare/YoucareShell";
import { useRuntimeStatus } from "@/hooks/data/useRuntime";
export default function BrowserPageRoute() {
  const s = useRuntimeStatus(10000);
  const tabs = useMemo(() => s.data?.bridge?.tabs ?? [], [s.data]);
  return (
    <YoucareShell title="Trình duyệt" subtitle="Tab live duy nhất từ BE bridge — read-only, không tự mở tab." actions={<button className="yc-btn" onClick={() => s.refetch()}>Tải lại</button>}>
      <div className="yc-stats">
        <StatCard label="Tabs (BE)" value={s.isError ? "—" : s.isPending ? "…" : String(tabs.length)} sub="bridge.tabs" tone="blue" />
        <StatCard label="Wiring" value={s.data ? (s.data.wiring.ok ? "OK" : "CHƯA") : "—"} sub={s.data?.wiring.wiring ?? "—"} />
        <StatCard label="Lỗi bridge" value={s.data?.bridge.error ? "Có" : "Không"} sub={s.data?.bridge.error ?? "—"} />
        <StatCard label="BE" value={s.data?.be.status ?? "—"} sub="trạng thái BE" />
      </div>
      {s.isError ? <EmptyState text="Chưa nối được BE :8770. Kiểm tra BE rồi thử lại." /> : null}
      {!s.isError && s.isPending ? <EmptyState text="Đang tải tabs từ BE…" /> : null}
      <div className="yc-card">
        <h4>Tab đang mở ({tabs.length})</h4>
        {tabs.length === 0 && !s.isPending && !s.isError ? <p className="yc-sub">Chưa có tab live từ BE.</p> : null}
        <div style={{ display: "grid", gap: 8, marginTop: 10 }}>
          {tabs.map((t: any) => (
            <div key={`${t.browser}-${t.tab}`} style={{ border: "1px solid #eceaf4", borderRadius: 12, padding: "10px 14px", fontSize: 14, background: "#fafaff" }}>
              <b>tab {t.tab}</b> · {t.browser} · {t.title || t.url}
            </div>
          ))}
        </div>
        <p className="yc-sub">Mọi thao tác trình duyệt phải qua Browser Gateway (read_via_eye / write_via_adapter). FE không điều khiển tab trực tiếp.</p>
        <Link className="yc-btn" href="/tasks-live">Giao việc dùng tab</Link>
      </div>
    </YoucareShell>
  );
}
