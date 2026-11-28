"use client";

import Link from "next/link";
import { YoucareShell } from "@/components/youcare/YoucareShell";
import { useLibrary } from "@/hooks/data/useMiro";

export default function LibraryPage() {
  const { data, isLoading, isError } = useLibrary();
  return (
    <YoucareShell title="Thư viện" subtitle="Video trong kho — BE chưa có route /library production.">
      <h1 data-testid="library-title" style={{ display: "none" }}>Thư viện</h1>
      {isLoading ? <p>Đang tải thư viện…</p> : null}
      {isError ? (
        <p style={{ color: "#B52E2E" }}>
          Thư viện chưa khả dụng trên BE production (404/405 là đúng — không dùng fixture giả).
        </p>
      ) : null}
      <div data-testid="library-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(240px,1fr))", gap: 12 }}>
        {(data ?? []).map((p) => {
          const id = String(p.id);
          return (
            <div key={id} data-testid={`library-item-${id}`} style={{ border: "1px solid #ddd", borderRadius: 10, padding: 12, background: "#fff" }}>
              <h3 style={{ margin: "0 0 4px" }}>{String(p.title)}</h3>
              <small>
                r{String(p.revision)} · {String(p.duration)}s ·{" "}
                {String((p.canvas as { width?: unknown; height?: unknown } | undefined)?.width)}x
                {String((p.canvas as { width?: unknown; height?: unknown } | undefined)?.height)}
              </small>
              <br />
              <Link data-testid={`open-editor-${id}`} href={`/editor?project=${id}`} style={{ fontWeight: 600 }}>
                Mở trong Editor →
              </Link>
            </div>
          );
        })}
      </div>
    </YoucareShell>
  );
}
