"use client";
import { useParams } from "next/navigation";
import { YoucareShell, EmptyState } from "@/components/youcare/YoucareShell";
export default function PublicationDetailPage() {
  const p = useParams<{ publicationId: string }>();
  const id = Array.isArray(p?.publicationId) ? p.publicationId[0] : p?.publicationId;
  return (
    <YoucareShell title={`Bài ${id ?? "—"}`} subtitle="Đối soát qua Reconcile read-only, không suy đoán trạng thái.">
      <EmptyState text="Chi tiết publication đọc qua journal BE — dùng Reconcile ở trang Xuất bản để đối soát bài này." />
    </YoucareShell>
  );
}
