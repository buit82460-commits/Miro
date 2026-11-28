"use client";
import { YoucareShell, EmptyState } from "@/components/youcare/YoucareShell";
export default function WorkflowsPageRoute() {
  return (
    <YoucareShell title="Quy trình" subtitle="Danh sách workflow — BE chưa có endpoint riêng, hiển thị trung thực.">
      <EmptyState text="BE chưa có API workflows riêng. Trang này giữ trống trung thực — không tạo workflow mẫu." />
    </YoucareShell>
  );
}
