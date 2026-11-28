"use client";
import { useParams } from "next/navigation";
import { YoucareShell, EmptyState } from "@/components/youcare/YoucareShell";
import { useDayPlan } from "@/hooks/data/useRuntime";
export default function ScheduleDetailPage() {
  const p = useParams<{ scheduleId: string }>();
  const id = Array.isArray(p?.scheduleId) ? p.scheduleId[0] : p?.scheduleId;
  const plan = useDayPlan(5000);
  const slots: any[] = Array.isArray((plan.data as any)?.slots) ? (plan.data as any).slots : [];
  const s = slots.find((x: any) => String(x.intent_id ?? x.id) === id);
  return (
    <YoucareShell title={`Lịch ${id ?? "—"}`} subtitle="Chi tiết suất day-plan từ BE.">
      {!s ? <EmptyState text="Không tìm thấy suất này trong day-plan BE." /> : <div className="yc-card"><pre style={{ fontSize: 12 }}>{JSON.stringify(s, null, 2)}</pre></div>}
    </YoucareShell>
  );
}
