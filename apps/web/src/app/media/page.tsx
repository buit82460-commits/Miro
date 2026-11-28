"use client";
import { useState } from "react";
import { YoucareShell, EmptyState } from "@/components/youcare/YoucareShell";
export default function MediaPageRoute() {
  const [videoId, setVideoId] = useState("");
  const [out, setOut] = useState("");
  const [busy, setBusy] = useState(false);
  const load = async () => {
    if (!videoId.trim()) return;
    setBusy(true); setOut("");
    try {
      const r = await fetch(`/api/studio/project/${encodeURIComponent(videoId.trim())}`);
      const j = await r.json().catch(() => null);
      setOut(r.ok ? JSON.stringify(j)?.slice(0, 1500) : `BE lỗi ${r.status}`);
    } catch (e: any) { setOut(`Không gọi được BE: ${e?.message}`); }
    finally { setBusy(false); }
  };
  return (
    <YoucareShell title="Media" subtitle="Studio project/media từ BE — render/dub qua media_intel." actions={<button className="yc-btn primary" onClick={load} disabled={busy || !videoId.trim()}>{busy ? "…" : "Tải project"}</button>}>
      <div className="yc-card" style={{ display: "flex", gap: 8 }}>
        <input value={videoId} onChange={(e) => setVideoId(e.target.value)} placeholder="video_id" style={{ flex: 1, border: "1px solid #eceaf4", borderRadius: 12, padding: "10px 14px", fontFamily: "inherit" }} />
      </div>
      {out ? <div className="yc-card"><pre style={{ fontSize: 12, whiteSpace: "pre-wrap" }}>{out}</pre></div> : <EmptyState text="Nhập video_id rồi tải — mọi phân tích media đi qua adapter media_intel duy nhất, không gọi cv2 trực tiếp từ UI." />}
    </YoucareShell>
  );
}
