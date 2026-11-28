"use client";
import { useParams } from "next/navigation";
import { YoucareShell, EmptyState } from "@/components/youcare/YoucareShell";
export default function WorkflowDetailPage() {
  const p = useParams<{ workflowId: string }>();
  const id = Array.isArray(p?.workflowId) ? p.workflowId[0] : p?.workflowId;
  return (
    <YoucareShell title={`Quy trình ${id ?? "—"}`} subtitle="Chi tiết workflow.">
      <EmptyState text="BE chưa có API workflow-detail — trang giữ trống trung thực." />
    </YoucareShell>
  );
}
