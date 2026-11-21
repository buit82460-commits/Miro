"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api/http";

type Capability = { status: string; runtime: string; input: string; output: string; evidence: string };
type Platform = {
  id: string; name: string; version: number; runtime: string;
  accounts: string[]; entry_urls: Record<string, string>;
  capabilities: Record<string, Capability>;
  tracks: { read: string; publish: string };
};

const CAPS = ["list", "download", "draft", "publish", "reconcile", "watch"];
const READ_CAPS = ["list", "download", "reconcile", "watch"];
const PUB_CAPS = ["draft", "publish"];

function badge(s: string) {
  const style =
    s === "SUPPORTED" || s === "READY"
      ? { background: "#e6f4ea", color: "#137333" }
      : s === "PARTIAL" || s === "DEGRADED"
        ? { background: "#fef7e0", color: "#b06000" }
        : s === "BLOCKED"
          ? { background: "#fce8e6", color: "#a50e0e" }
          : { background: "#f1f3f4", color: "#5f6368" };
  return <span style={{ borderRadius: 12, padding: "2px 10px", fontSize: 12, ...style }}>{s}</span>;
}

export default function PlatformsPage() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["settings", "platforms"],
    queryFn: () => api.get<{ version: number; platforms: Platform[] }>("/api/settings/platforms"),
  });
  const [form, setForm] = useState({ id: "", name: "", runtime: "" });
  const [rollbackTo, setRollbackTo] = useState("");

  const invalidate = { onSuccess: () => qc.invalidateQueries({ queryKey: ["settings", "platforms"] }) };
  const upsert = useMutation({
    mutationFn: (b: unknown) => api.post("/api/settings/platforms", b),
    ...invalidate,
  });
  const clone = useMutation({
    mutationFn: (id: string) => api.post(`/api/settings/platforms/${id}/clone`, { new_id: "" }),
    ...invalidate,
  });

  if (isLoading) return <main><p>Đang tải registry nền tảng…</p></main>;

  return (
    <main style={{ padding: 24, maxWidth: 1200 }}>
      <h1>Cài đặt → Nền tảng</h1>
      <p>Registry version <b>{data?.version}</b> · đọc (list/download/reconcile/watch) và đăng (draft/publish) tách riêng · update + rollback giữ task cũ (task pin version).</p>

      <section style={{ margin: "16px 0", padding: 16, border: "1px solid #dadce0", borderRadius: 8 }}>
        <h2>Thêm / nhân bản / đăng ký mới</h2>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input placeholder="id (vd: zalo)" value={form.id} onChange={(e) => setForm({ ...form, id: e.target.value })} />
          <input placeholder="Tên hiển thị" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input placeholder="Runtime (adapter…)" value={form.runtime} onChange={(e) => setForm({ ...form, runtime: e.target.value })} style={{ minWidth: 320 }} />
          <button onClick={() => upsert.mutate({ id: form.id, name: form.name, runtime: form.runtime })}>Đăng ký mới / Cập nhật</button>
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 12, alignItems: "center" }}>
          <input placeholder="Rollback về version…" value={rollbackTo} onChange={(e) => setRollbackTo(e.target.value)} style={{ width: 200 }} />
          <button
            onClick={async () => {
              await api.post("/api/settings/platforms/rollback", { version: Number(rollbackTo) });
              qc.invalidateQueries({ queryKey: ["settings", "platforms"] });
            }}
          >
            Rollback (giữ task cũ)
          </button>
        </div>
      </section>

      {(data?.platforms ?? []).map((p) => (
        <section key={p.id} style={{ margin: "16px 0", padding: 16, border: "1px solid #dadce0", borderRadius: 8 }}>
          <h2>{p.name} <small>({p.id} · v{p.version})</small></h2>
          <p style={{ display: "flex", gap: 16 }}>
            <span>Đọc: {badge(p.tracks.read)}</span>
            <span>Đăng: {badge(p.tracks.publish)}</span>
          </p>
          <p style={{ color: "#5f6368" }}>{p.runtime}</p>
          <p>Tài khoản: {(p.accounts ?? []).join(" · ") || "—"}</p>

          <h3>Đọc (read-only)</h3>
          <table cellPadding={6} style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead><tr><th>Capability</th><th>Trạng thái</th><th>Runtime</th><th>In/Out</th><th>Bằng chứng</th></tr></thead>
            <tbody>
              {READ_CAPS.map((c) => (
                <tr key={c} style={{ borderTop: "1px solid #eee" }}>
                  <td><b>{c}</b></td>
                  <td>{badge(p.capabilities[c]?.status ?? "?")}</td>
                  <td>{p.capabilities[c]?.runtime}</td>
                  <td>{p.capabilities[c]?.input} → {p.capabilities[c]?.output}</td>
                  <td><small>{p.capabilities[c]?.evidence}</small></td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3>Đăng (side-effect)</h3>
          <table cellPadding={6} style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead><tr><th>Capability</th><th>Trạng thái</th><th>Runtime</th><th>In/Out</th><th>Bằng chứng</th></tr></thead>
            <tbody>
              {PUB_CAPS.map((c) => (
                <tr key={c} style={{ borderTop: "1px solid #eee" }}>
                  <td><b>{c}</b></td>
                  <td>{badge(p.capabilities[c]?.status ?? "?")}</td>
                  <td>{p.capabilities[c]?.runtime}</td>
                  <td>{p.capabilities[c]?.input} → {p.capabilities[c]?.output}</td>
                  <td><small>{p.capabilities[c]?.evidence}</small></td>
                </tr>
              ))}
            </tbody>
          </table>
          <button onClick={() => clone.mutate(p.id)} style={{ marginTop: 8 }}>Nhân bản {p.id}</button>
        </section>
      ))}

      <p style={{ color: "#5f6368" }}>Chi tiết ma trận đầy đủ: <code>docs/platform-matrix.md</code> · capabilities còn lại: {CAPS.join(", ")}</p>
    </main>
  );
}
