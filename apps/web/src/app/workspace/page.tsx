"use client";
import Link from "next/link";
import { YoucareShell } from "@/components/youcare/YoucareShell";
export default function AiWorkspacePageRoute() {
  return (
    <YoucareShell title="AI Workspace" subtitle="Giao việc cho Miro bằng ngôn ngữ tự nhiên — BE sở hữu state.">
      <div className="yc-card" style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <span className="yc-sub">Workspace hợp nhất vào Giám sát live (POST /tasks/run-message).</span>
        <Link className="yc-btn primary" href="/tasks-live">Mở Giám sát live</Link>
        <Link className="yc-btn" href="/tasks">Danh sách tác vụ</Link>
      </div>
    </YoucareShell>
  );
}
