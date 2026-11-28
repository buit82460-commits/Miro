"use client";
import { YoucareShell, StatCard, EmptyState } from "@/components/youcare/YoucareShell";
import { useDayPlan, useEnsureDayPlan, useDayPlanStatus } from "@/hooks/data/useRuntime";
export default function SchedulesPageRoute() {
  const plan = useDayPlan(5000);
  const ensure = useEnsureDayPlan();
  const st = useDayPlanStatus();
  const d: any = plan.data;
  const slots: any[] = Array.isArray(d?.slots) ? d.slots : [];
  return (
    <YoucareShell title="Lịch hẹn" subtitle="Day-plan từ BE — ensure / active / paused thật." actions={<><button className="yc-btn" onClick={() => ensure.mutate({ was_clean_shutdown: true })} disabled={ensure.isPending}>{ensure.isPending ? "…" : "Ensure day-plan"}</button><button className="yc-btn primary" onClick={() => st.mutate(d?.status === "paused" ? "active" : "paused")}>{d?.status === "paused" ? "Bật lại" : "Tạm dừng"}</button></>}>
      <div className="yc-stats">
        <StatCard label="Ngày" value={d?.date ?? "—"} sub={`status: ${d?.status ?? "—"}`} tone="blue" />
        <StatCard label="Slots" value={plan.isError ? "—" : plan.isPending ? "…" : String(slots.length)} sub="tổng suất" />
        <StatCard label="Pending" value={String(slots.filter((s) => s.state === "pending").length)} sub="chưa chạy" />
        <StatCard label="Unknown" value={String(slots.filter((s) => String(s.state ?? "").includes("unknown")).length)} sub="chờ reconcile" />
      </div>
      {plan.isError ? <EmptyState text="Không tải được day-plan (BE :8770). Bấm Ensure để tạo khi BE sẵn sàng." /> : null}
      {!plan.isError && plan.isPending ? <EmptyState text="Đang tải day-plan từ BE…" /> : null}
      <div className="yc-card">
        <h4>Suất trong ngày</h4>
        {slots.length === 0 && !plan.isPending ? <p className="yc-sub">Chưa có slot nào — bấm Ensure day-plan.</p> : null}
        <div style={{ display: "grid", gap: 8, marginTop: 10 }}>
          {slots.slice(0, 20).map((s: any, i: number) => (
            <div key={i} style={{ border: "1px solid #eceaf4", borderRadius: 12, padding: "10px 14px", fontSize: 14, background: "#fafaff" }}>
              <b>{s.intent_id ?? s.id ?? `slot-${i}`}</b> · {s.state ?? "—"} · {s.platform ?? "—"}
            </div>
          ))}
        </div>
      </div>
    </YoucareShell>
  );
}
