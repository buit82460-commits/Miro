"use client";
import Link from "next/link";
import { YoucareShell, StatCard } from "@/components/youcare/YoucareShell";
import { useRuntimeStatus } from "@/hooks/data/useRuntime";

export default function RuntimePage() {
  const { data, isLoading, isError } = useRuntimeStatus();

  return (
    <YoucareShell title="Runtime" subtitle="Launcher + BE + Bridge + Extension. BE sở hữu state, FE chỉ đọc.">
      <h1 data-testid="runtime-title" style={{ fontSize: 20, fontWeight: 800, margin: 0 }}>Runtime</h1>
      {isLoading ? <p>Đang tải runtime...</p> : null}
      {isError ? <p style={{ color: "#B52E2E" }}>Chưa nối được BE (kiểm tra BE :8770).</p> : null}
      {data ? (
        <>
          <div className="yc-stats">
            <StatCard label="BE" value={data.be.status} sub={<span data-testid="runtime-be">trạng thái BE</span>} />
            <StatCard label="Wiring" value={data.wiring.ok ? "OK" : "CHƯA"} sub={<span data-testid="runtime-wiring">{data.wiring.wiring} — {data.wiring.reason}</span>} />
            <StatCard label="Bridge tabs" value={String(data.bridge.count)} sub={<span data-testid="runtime-tabs">{data.bridge.error ? `lỗi: ${data.bridge.error}` : `${data.bridge.count} tab`}</span>} tone="blue" />
            <StatCard label="Tasks BE" value={String(data.tasks.count)} sub={<span data-testid="runtime-tasks">{data.tasks.count} task</span>} />
          </div>
          <ul data-testid="runtime-status" style={{ display: "none" }}>
            <li data-testid="runtime-be">{data.be.status}</li>
            <li data-testid="runtime-wiring">{data.wiring.wiring}</li>
            <li data-testid="runtime-tabs">{data.bridge.count}</li>
            <li data-testid="runtime-tasks">{data.tasks.count}</li>
          </ul>
          <div className="yc-card">
            <h4>Tab đang quản lý</h4>
            <ul data-testid="runtime-tab-list" style={{ listStyle: "none", padding: 0, display: "grid", gap: 8 }}>
              {(data.bridge.tabs ?? []).map((t) => (
                <li key={`${t.browser}-${t.tab}`} data-testid={`runtime-tab-${t.tab}`} style={{ border: "1px solid #eceaf4", borderRadius: 12, padding: "10px 14px", background: "#fafaff", fontSize: 14 }}>
                  tab {t.tab} - {t.browser} - {t.title || t.url}
                </li>
              ))}
              {(data.bridge.tabs ?? []).length === 0 ? <li className="yc-sub">Chưa có tab nào từ Bridge.</li> : null}
            </ul>
            <p>
              <Link data-testid="link-tasks-live" href="/tasks-live" className="yc-btn primary">
                Giao việc cho Miro
              </Link>
            </p>
          </div>
        </>
      ) : null}
    </YoucareShell>
  );
}
