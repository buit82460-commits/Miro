"use client";

import Link from "next/link";
import MiroNav from "@/components/miro-nav";
import { useRuntimeStatus } from "@/hooks/data/useRuntime";

export default function RuntimePage() {
  const { data, isLoading, isError } = useRuntimeStatus();

  return (
    <MiroNav>
      <h1 data-testid="runtime-title">Runtime</h1>
      <p>Launcher + BE + Bridge + Extension. BE so huu state, FE chi doc.</p>
      {isLoading ? <p>Dang tai runtime...</p> : null}
      {isError ? <p style={{ color: "#B52E2E" }}>Chua noi duoc BE (NEXT_PUBLIC_API_BASE).</p> : null}
      {data ? (
        <>
          <ul data-testid="runtime-status">
            <li data-testid="runtime-be">BE: {data.be.status}</li>
            <li data-testid="runtime-wiring">
              Wiring: {data.wiring.wiring} - {data.wiring.ok ? "OK" : `CHUA (${data.wiring.reason})`}
            </li>
            <li data-testid="runtime-tabs">
              Bridge tabs: {data.bridge.count}
              {data.bridge.error ? ` (loi: ${data.bridge.error})` : ""}
            </li>
            <li data-testid="runtime-tasks">Tasks trong BE: {data.tasks.count}</li>
          </ul>
          <h2>Tab dang quan ly</h2>
          <ul data-testid="runtime-tab-list">
            {(data.bridge.tabs ?? []).map((t) => (
              <li key={`${t.browser}-${t.tab}`} data-testid={`runtime-tab-${t.tab}`}>
                tab {t.tab} - {t.browser} - {t.title || t.url}
              </li>
            ))}
          </ul>
          <p>
            <Link data-testid="link-tasks-live" href="/tasks-live" style={{ fontWeight: 600 }}>
              Giao viec cho Miro
            </Link>
          </p>
        </>
      ) : null}
    </MiroNav>
  );
}
