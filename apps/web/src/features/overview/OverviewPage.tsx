"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useBeTasks } from "@/hooks/data/useRuntime";
import { YoucareShell, StatCard, EmptyState } from "@/components/youcare/YoucareShell";

function statusOf(t: unknown): string {
  return String((t as Record<string, unknown>)?.status ?? "");
}

export function OverviewPage() {
  const tasksQ = useBeTasks(50, 5000);
  const list = useMemo(() => (Array.isArray(tasksQ.data) ? (tasksQ.data as unknown[]) : []), [tasksQ.data]);
  const [sel, setSel] = useState<string | null>(null);
  const running = list.filter((t) => ["running", "planning", "recovering"].includes(statusOf(t))).length;
  const queued = list.filter((t) => ["queued", "waiting_for_resource", "stop_requested"].includes(statusOf(t))).length;
  const attention = list.filter((t) => ["failed", "needs_attention", "awaiting_review"].includes(statusOf(t)));
  const done = list.filter((t) => ["completed", "partial"].includes(statusOf(t))).length;
  const selected = list.find((t) => String((t as Record<string, unknown>)?.id) === sel) as Record<string, unknown> | undefined ?? (list[0] as Record<string, unknown> | undefined);
  const beDown = tasksQ.isError;

  return (
    <YoucareShell
      title="Chào buổi sáng!"
      subtitle="Trạng thái vận hành thời gian thực của Miro — tác vụ, xuất bản và phê duyệt."
      crumb="Tổng quan"
      actions={<><Link className="yc-btn" href="/tasks">Mở tác vụ</Link><Link className="yc-btn primary" href="/tasks-live">+ Giao việc mới</Link></>}
    >
      <div className="yc-stats">
        <StatCard label="Đang thực thi" value={beDown ? "—" : tasksQ.isPending ? "…" : String(running)} sub={`${list.length} tác vụ gần nhất`} tone="blue" />
        <StatCard label="Chờ hàng đợi" value={beDown ? "—" : tasksQ.isPending ? "…" : String(queued)} sub="queued + chờ tài nguyên" />
        <StatCard label="Cần quyết định" value={beDown ? "—" : tasksQ.isPending ? "…" : String(attention.length)} sub="failed + needs_attention + awaiting_review" />
        <StatCard label="Hoàn tất" value={beDown ? "—" : tasksQ.isPending ? "…" : String(done)} sub="completed + partial" />
      </div>
      <div className="yc-split">
        <div className="yc-left">
          <h3>Tác vụ gần nhất</h3>
          {beDown ? <EmptyState text="Không tải được task từ BE. Kiểm tra BE :8770 rồi tải lại." /> : null}
          {!beDown && tasksQ.isPending ? <EmptyState text="Đang tải từ BE…" /> : null}
          {!tasksQ.isPending && list.length === 0 && !beDown ? <EmptyState text="Chưa có tác vụ nào. Giao việc mới để bắt đầu." /> : null}
          {list.slice(0, 5).map((t) => {
            const o = t as Record<string, unknown>;
            const id = String(o.id ?? "");
            return (
              <button key={id} onClick={() => setSel(id)} className={selected && String(selected.id) === id ? "yc-row sel" : "yc-row"}>
                <div><b style={{ fontSize: 13 }}>{id.slice(0, 14)}…</b><br /><small>{statusOf(t)}</small></div>
                <span className={`yc-st${statusOf(t) === "failed" ? " red" : ""}`}>{String((o.error as Record<string, unknown> | undefined)?.code ?? statusOf(t) ?? "—")}</span>
              </button>
            );
          })}
        </div>
        <div className="yc-right">
          <h3 className="lbl">Chi tiết tác vụ</h3>
          {!selected ? <div style={{ marginTop: 12 }}><EmptyState text="Chưa có dữ liệu." /></div> : (
            <>
              <div className="yc-big">{String(selected.id ?? "—")}</div>
              <div className="yc-kv"><span className="yc-pill">{statusOf(selected)}</span><span className="yc-pill">rev {String(selected.revision ?? "—")}</span></div>
              <div className="yc-sub">{String(((selected.request as Record<string, unknown> | undefined)?.message) ?? "")}</div>
              {selected.error ? <div className="yc-evt">Lỗi <b>{String((selected.error as Record<string, unknown>).code)}</b> — {String((selected.error as Record<string, unknown>).message)}</div> : null}
              <div className="yc-foot">
                <Link className="yc-btn primary" href={selected.id ? `/tasks-live/${selected.id}` : "/tasks-live"}>Mở giám sát live</Link>
                <Link className="yc-btn" href="/tasks">Tất cả tác vụ</Link>
              </div>
            </>
          )}
        </div>
      </div>
    </YoucareShell>
  );
}
