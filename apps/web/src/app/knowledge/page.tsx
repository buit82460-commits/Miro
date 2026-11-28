"use client";
import { YoucareShell, EmptyState } from "@/components/youcare/YoucareShell";
export default function KnowledgePageRoute() {
  return (
    <YoucareShell title="Tri thức" subtitle="Kho tri thức — BE chưa có endpoint riêng, hiển thị trung thực.">
      <EmptyState text="BE chưa có API knowledge riêng. Trang này giữ trống trung thực — không tạo tài liệu mẫu." />
    </YoucareShell>
  );
}
