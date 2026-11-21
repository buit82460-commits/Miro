"use client";

import Link from "next/link";
import MiroNav from "@/components/miro-nav";
import { useLibrary } from "@/hooks/data/useMiro";

export default function LibraryPage() {
  const { data, isLoading, isError } = useLibrary();
  return (
    <MiroNav>
      <h1 data-testid="library-title">Thư viện</h1>
      <p>Video trong kho — mở Editor để chỉnh rồi đưa đi xuất bản.</p>
      {isLoading ? <p>Đang tải thư viện…</p> : null}
      {isError ? <p style={{ color: "#B52E2E" }}>Chưa nối được BE.</p> : null}
      <div data-testid="library-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(240px,1fr))", gap: 12 }}>
        {(data ?? []).map((p) => {
          const id = String(p.id);
          return (
            <div key={id} data-testid={`library-item-${id}`} style={{ border: "1px solid #ddd", borderRadius: 10, padding: 12, background: "#fff" }}>
              <h3 style={{ margin: "0 0 4px" }}>{String(p.title)}</h3>
              <small>
                r{String(p.revision)} · {String(p.duration)}s · {String(p.canvas?.width)}x{String(p.canvas?.height)}
              </small>
              <br />
              <Link data-testid={`open-editor-${id}`} href={`/editor?project=${id}`} style={{ fontWeight: 600 }}>
                Mở trong Editor →
              </Link>
            </div>
          );
        })}
      </div>
    </MiroNav>
  );
}
