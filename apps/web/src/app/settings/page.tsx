"use client";

import MiroNav from "@/components/miro-nav";
import { useConnections } from "@/hooks/data/useMiro";

export default function SettingsPage() {
  const { data, isLoading, isError } = useConnections();
  return (
    <MiroNav>
      <h1 data-testid="settings-title">Cài đặt & kết nối</h1>
      <p>Tài khoản các platform. Fixture hiện tại — nối runtime thật sau.</p>
      {isLoading ? <p>Đang tải kết nối…</p> : null}
      {isError ? <p style={{ color: "#B52E2E" }}>Chưa nối được BE.</p> : null}
      <ul data-testid="connections-list">
        {(data ?? []).map((c, i) => (
          <li key={i} data-testid={`connection-${String(c.platform)}`}>
            <b>{String(c.platform)}</b> · {String(c.account)} ·{" "}
            <span data-testid={`connection-status-${String(c.platform)}`}>{String(c.status)}</span>
          </li>
        ))}
      </ul>
    </MiroNav>
  );
}
