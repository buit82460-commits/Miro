"use client";
import { YoucareShell, EmptyState } from "@/components/youcare/YoucareShell";
export default function SettingsPageRoute() {
  return (
    <YoucareShell title="Cài đặt" subtitle="Cài đặt FE cục bộ — credential chỉ lưu ref, không plaintext.">
      <div className="yc-card">
        <h4>Liên kết nhanh</h4>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
          <a className="yc-btn" href="/settings/connections">Kết nối tài khoản</a>
          <a className="yc-btn" href="/settings/platforms">Nền tảng</a>
        </div>
      </div>
      <EmptyState text="Cài đặt giao diện/ngôn ngữ lưu cục bộ trên trình duyệt. Mọi secret BE từ chối plaintext (CREDENTIAL_PLAINTEXT_DENIED)." />
    </YoucareShell>
  );
}
