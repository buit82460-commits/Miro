"use client";
import Link from "next/link";
import { YoucareShell, EmptyState } from "@/components/youcare/YoucareShell";
import { usePublishBatches, useReceipts } from "@/hooks/data/useMiro";
export default function PublishPageRoute() {
  const b = usePublishBatches();
  const r = useReceipts();
  const batches: any[] = Array.isArray(b.data) ? b.data as any[] : [];
  const receipts: any[] = Array.isArray(r.data) ? r.data as any[] : [];
  return (
    <YoucareShell title="Xuất bản" subtitle="Batch + receipt từ BE (dry-run, chưa đăng thật).">
      <h1 data-testid="publish-title" style={{ fontSize: 20, fontWeight: 800, margin: 0 }}>Xuất bản</h1>
      <p data-testid="publish-note" className="yc-sub">BE-first: dry-run (allow_post=false). Post thật chỉ sau approval tươi. BE down → 502.</p>
      <div className="yc-card">
        <h4>Batch đã gửi ({batches.length})</h4>
        {b.isError ? <EmptyState text="Không nối BE. Kiểm tra :8770." /> : null}
        <ul data-testid="batch-list">{batches.map((x: any) => <li key={String(x.id)}>{String(x.id)} · {String(x.platform)} · {String(x.status)}</li>)}{batches.length === 0 && !b.isPending ? <li>Chưa có batch nào.</li> : null}</ul>
      </div>
      <div className="yc-card">
        <h4>Receipt ({receipts.length})</h4>
        <ul data-testid="receipt-list">{receipts.map((x: any) => <li key={x.id}>{x.platform}/{x.account} · {x.status}</li>)}{receipts.length === 0 ? <li>Chưa có receipt — đối soát qua Reconcile.</li> : null}</ul>
        <Link className="yc-btn primary" href="/publishing">Sang luồng Threads</Link>
      </div>
    </YoucareShell>
  );
}
