"use client";
import { useParams } from "next/navigation";
import { useState } from "react";
import { YoucareShell, EmptyState } from "@/components/youcare/YoucareShell";
export default function MediaAssetPage() {
  const p = useParams<{ assetId: string }>();
  const id = Array.isArray(p?.assetId) ? p.assetId[0] : p?.assetId;
  const [vid, setVid] = useState(typeof id === "string" ? id : "");
  const [out, setOut] = useState("");
  const load = async () => {
    if (!vid.trim()) return;
    try {
      const r = await fetch(`/api/studio/project/${encodeURIComponent(vid.trim())}`);
      const j = await r.json().catch(() => null);
      setOut(r.ok ? String(JSON.stringify(j))?.slice(0, 1500) : `BE lỗi ${r.status}`);
    } catch (e: any) { setOut(`Không gọi được BE: ${e?.message}`); }
  };
  return (
    <YoucareShell title={`Media ${id ?? "—"}`} subtitle="Studio project từ BE.">
      <div className="yc-card" style={{ display: "flex", gap: 8 }}>
        <input value={vid} onChange={(e) => setVid(e.target.value)} placeholder="video_id" style={{ flex: 1, border: "1px solid #eceaf4", borderRadius: 12, padding: "10px 14px", fontFamily: "inherit" }} />
        <button className="yc-btn primary" onClick={load}>Tải</button>
      </div>
      {out ? <div className="yc-card"><pre style={{ fontSize: 12, whiteSpace: "pre-wrap" }}>{out}</pre></div> : <EmptyState text="Nhập video_id rồi tải từ BE." />}
    </YoucareShell>
  );
}
