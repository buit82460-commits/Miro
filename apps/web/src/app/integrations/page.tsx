"use client";
import { YoucareShell, EmptyState, StatCard } from "@/components/youcare/YoucareShell";
import { useConnectionAccounts, usePlatforms } from "@/hooks/data/useConnections";
export default function IntegrationsPageRoute() {
  const acc = useConnectionAccounts();
  const plat = usePlatforms();
  const accounts: any[] = Array.isArray(acc.data) ? acc.data as any[] : [];
  return (
    <YoucareShell title="Tích hợp" subtitle="Kết nối tài khoản + registry nền tảng từ BE thật." actions={<button className="yc-btn" onClick={() => { acc.refetch(); plat.refetch(); }}>Tải lại</button>}>
      <div className="yc-stats">
        <StatCard label="Accounts (BE)" value={acc.isError ? "—" : acc.isPending ? "…" : String(accounts.length)} sub="connections/accounts" tone="blue" />
        <StatCard label="Platforms" value={plat.isError ? "—" : "BE"} sub="registry versioned" />
        <StatCard label="Verify" value="—" sub="verify qua tab thật, không mock" />
        <StatCard label="Post thật" value="—" sub="chỉ sau trinh sát REA Q1–Q10" />
      </div>
      {acc.isError ? <EmptyState text="Không nối được BE :8770 — kiểm tra BE rồi tải lại. Không hiện dữ liệu mẫu." /> : null}
      <div className="yc-card">
        <h4>Tài khoản ({accounts.length})</h4>
        {accounts.length === 0 && !acc.isPending ? <p className="yc-sub">Chưa có account nào từ BE. Thêm ở Cài đặt → Kết nối.</p> : null}
        <div style={{ display: "grid", gap: 8, marginTop: 10 }}>
          {accounts.slice(0, 20).map((a: any) => (
            <div key={a.id} style={{ border: "1px solid #eceaf4", borderRadius: 12, padding: "10px 14px", fontSize: 14, background: "#fafaff" }}>
              <b>{a.platform}/{a.account_id}</b> · {a.status} · {a.is_default ? "default" : ""}
            </div>
          ))}
        </div>
      </div>
    </YoucareShell>
  );
}
