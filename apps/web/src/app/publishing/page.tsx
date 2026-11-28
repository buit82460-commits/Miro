"use client";
import { useState } from "react";
import { YoucareShell, EmptyState } from "@/components/youcare/YoucareShell";
export default function PublishingPageRoute() {
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState("");
  const [owner, setOwner] = useState("");
  const [shortcode, setShortcode] = useState("");
  const [renderId, setRenderId] = useState("");
  const run = async (path: string, body: any) => {
    setBusy(true); setMsg("");
    try {
      const r = await fetch(`/api/${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const j = await r.json().catch(() => null);
      setMsg(r.ok ? `OK ${path}: ${JSON.stringify(j)?.slice(0, 300)}` : `BE lỗi ${r.status}: ${JSON.stringify(j)?.slice(0, 300)}`);
    } catch (e: any) { setMsg(`Không gọi được BE: ${e?.message ?? e}`); }
    finally { setBusy(false); }
  };
  return (
    <YoucareShell title="Xuất bản" subtitle="Threads BE-first: prepare → approve → publish dry-run → reconcile. Post thật chỉ sau approval tươi." actions={<button className="yc-btn primary" onClick={() => run("threads/reconcile", { text, owner, shortcode })} disabled={busy}>Reconcile read-only</button>}>
      <p data-testid="publish-note" className="yc-sub">Dry-run mặc định (allow_post=false). UNKNOWN → chỉ Reconcile, không đăng lại.</p>
      {msg ? <p data-testid="publishing-msg" className="yc-card"><b>{msg}</b></p> : null}
      <div className="yc-card" style={{ display: "grid", gap: 8 }}>
        <h4>Luồng Threads</h4>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Nội dung bài" style={{ border: "1px solid #eceaf4", borderRadius: 12, padding: "10px 14px", fontFamily: "inherit" }} />
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input value={owner} onChange={(e) => setOwner(e.target.value)} placeholder="owner (vd haodaojrk5)" style={{ flex: 1, minWidth: 160, border: "1px solid #eceaf4", borderRadius: 12, padding: "10px 14px", fontFamily: "inherit" }} />
          <input value={shortcode} onChange={(e) => setShortcode(e.target.value)} placeholder="shortcode" style={{ flex: 1, minWidth: 160, border: "1px solid #eceaf4", borderRadius: 12, padding: "10px 14px", fontFamily: "inherit" }} />
          <input value={renderId} onChange={(e) => setRenderId(e.target.value)} placeholder="render_id" style={{ flex: 1, minWidth: 160, border: "1px solid #eceaf4", borderRadius: 12, padding: "10px 14px", fontFamily: "inherit" }} />
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button className="yc-btn" disabled={busy} onClick={() => run("threads/approve", { text, owner, shortcode, revision: 0 })}>1. Approve</button>
          <button className="yc-btn" disabled={busy} onClick={() => run("threads/publish", { publication_id: `pub-${Date.now()}`, attempt_id: `att-${Date.now()}`, render_id: renderId || shortcode, text, owner, shortcode, allow_post: false })}>2. Publish dry-run</button>
          <button className="yc-btn" disabled={busy} onClick={() => run("threads/reconcile", { text, owner, shortcode })}>3. Reconcile</button>
        </div>
        <EmptyState text="Chưa chọn bài nào — nhập owner + shortcode rồi chạy từng bước. Không dùng dữ liệu mẫu." />
      </div>
      <h1 data-testid="publish-title" style={{ display: "none" }}>Xuất bản</h1>
    </YoucareShell>
  );
}
