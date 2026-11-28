"use client";
import { useState } from "react";
import { YoucareShell, EmptyState } from "@/components/youcare/YoucareShell";
export default function ResearchPageRoute() {
  const [q, setQ] = useState("");
  const [out, setOut] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async () => {
    if (!q.trim()) return;
    setBusy(true); setOut("");
    try {
      const r = await fetch("/api/research/search", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: q.trim(), limit: 10 }) });
      const j = await r.json().catch(() => null);
      setOut(r.ok ? JSON.stringify(j)?.slice(0, 2000) : `BE lỗi ${r.status}`);
    } catch (e: any) { setOut(`Không gọi được BE: ${e?.message}`); }
    finally { setBusy(false); }
  };
  return (
    <YoucareShell title="Nghiên cứu" subtitle="Tìm kiếm + phân tích video từ BE thật." actions={<button className="yc-btn primary" onClick={run} disabled={busy || !q.trim()}>{busy ? "…" : "Tìm kiếm"}</button>}>
      <div className="yc-card" style={{ display: "flex", gap: 8 }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nhập truy vấn…" style={{ flex: 1, border: "1px solid #eceaf4", borderRadius: 12, padding: "10px 14px", fontFamily: "inherit" }} />
      </div>
      {out ? <div className="yc-card"><pre style={{ fontSize: 12, whiteSpace: "pre-wrap" }}>{out}</pre></div> : <EmptyState text="Chưa có kết quả — nhập truy vấn rồi tìm. Không dùng kết quả mẫu." />}
    </YoucareShell>
  );
}
