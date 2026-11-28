"use client";
import { useParams } from "next/navigation";
import { YoucareShell, EmptyState } from "@/components/youcare/YoucareShell";
export default function ResearchDetailPage() {
  const p = useParams<{ researchId: string }>();
  const id = Array.isArray(p?.researchId) ? p.researchId[0] : p?.researchId;
  return (
    <YoucareShell title={`Nghiên cứu ${id ?? "—"}`} subtitle="Kết quả nghiên cứu từ BE.">
      <EmptyState text="BE chưa có API research-detail riêng — trang giữ trống trung thực." />
    </YoucareShell>
  );
}
