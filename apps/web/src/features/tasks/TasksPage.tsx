"use client";
import { useMemo, useState } from "react";
import {
  useBeApprove,
  useBeEvents,
  useBeRestart,
  useBeResume,
  useBeRevoke,
  useBeStop,
  useBeTask,
  useBeTasks,
  useCreateBeTask,
  useBeWaitStop,
} from "@/hooks/data/useRuntime";
import { RuntimeService, type BeTask } from "@/lib/services/runtime.service";
import { YoucareShell, StatCard, EmptyState } from "@/components/youcare/YoucareShell";

function errText(e: unknown): string {
  const { code, message } = RuntimeService.errMessage(e);
  return code ? `${code}: ${message}` : message;
}

export function TasksPage() {
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  const [newMessage, setNewMessage] = useState("");
  const [createOpen, setCreateOpen] = useState(false);

  const listQ = useBeTasks(50, 2000);
  const detailQ = useBeTask(selectedId ?? undefined, 2000);
  const eventsQ = useBeEvents(selectedId ?? undefined, 1500);
  const createTask = useCreateBeTask();
  const stop = useBeStop();
  const waitStop = useBeWaitStop();
  const restart = useBeRestart();
  const resume = useBeResume();
  const approve = useBeApprove();
  const revoke = useBeRevoke();

  const list: BeTask[] = useMemo(() => (Array.isArray(listQ.data) ? (listQ.data as BeTask[]) : []), [listQ.data]);
  const filtered = list.filter((t) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return String(t.id ?? "").toLowerCase().includes(q) || String(t.status ?? "").toLowerCase().includes(q);
  });
  const selected: BeTask | undefined = (detailQ.data as BeTask | undefined) ?? list.find((t) => t.id === selectedId);
  const beDown = listQ.isError;
  const active = list.filter((t) => ["running", "planning", "recovering", "queued", "waiting_for_resource"].includes(String(t.status))).length;
  const pending = stop.isPending || restart.isPending || resume.isPending || waitStop.isPending;

  const onCreate = () => {
    if (!newMessage.trim()) { setMsg("Nhập nội dung tác vụ trước khi tạo."); return; }
    createTask.mutate(
      { request_id: `req-${Date.now()}`, message: newMessage.trim(), videos: [] },
      {
        onSuccess: (c) => { setNewMessage(""); setCreateOpen(false); setSelectedId(c.id); setMsg(`Đã tạo tác vụ ${c.id}.`); },
        onError: (e) => setMsg(`Tạo thất bại: ${errText(e)}`),
      },
    );
  };

  return (
    <YoucareShell
      title="Tác vụ"
      subtitle="BE sở hữu state qua GET /tasks/recent — stop / restart / resume / approve thật, không mock."
      crumb="Tác vụ"
      actions={<><button className="yc-btn" onClick={() => listQ.refetch()}>Tải lại</button><button className="yc-btn primary" onClick={() => setCreateOpen((v) => !v)}>+ Tác vụ mới</button></>}
    >
      <div className="yc-stats">
        <StatCard label="Tổng (BE)" value={beDown ? "—" : listQ.isPending ? "…" : String(list.length)} sub="50 tác vụ gần nhất" tone="blue" />
        <StatCard label="Đang hoạt động" value={beDown ? "—" : listQ.isPending ? "…" : String(active)} sub="running + queued" />
        <StatCard label="Đã chọn" value={selected ? selected.id.slice(0, 12) + "…" : "—"} sub={selected ? String(selected.status) : "chưa chọn"} />
        <StatCard label="Sự kiện" value={selectedId ? (eventsQ.data?.length != null ? String(eventsQ.data.length) : "…") : "—"} sub="events realtime task đã chọn" />
      </div>

      {msg ? <div className="yc-card"><b>{msg}</b></div> : null}
      {createOpen ? (
        <div className="yc-card"><div className="yc-formrow" style={{ marginTop: 0 }}>
          <input className="yc-input" value={newMessage} onChange={(e) => setNewMessage(e.target.value)} placeholder="VD: tim kiem tiktok 5 video" style={{ flex: 3 }} />
          <button className="yc-btn primary" onClick={onCreate} disabled={createTask.isPending}>{createTask.isPending ? "Đang tạo…" : "Tạo tác vụ"}</button>
        </div></div>
      ) : null}

      <div className="yc-split">
        <div className="yc-left">
          <h3>Danh sách ({filtered.length})</h3>
          <input className="yc-search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Lọc theo id / status…" />
          {beDown ? <EmptyState text="Không tải được task từ BE. Kiểm tra BE :8770 rồi tải lại." /> : null}
          {!beDown && listQ.isPending ? <EmptyState text="Đang tải từ BE…" /> : null}
          {!listQ.isPending && filtered.length === 0 && !beDown ? <EmptyState text="Chưa có tác vụ nào. Tạo tác vụ mới để bắt đầu." /> : null}
          {filtered.slice(0, 30).map((t) => (
            <button key={t.id} onClick={() => setSelectedId(t.id)} className={selected?.id === t.id ? "yc-row sel" : "yc-row"}>
              <div><b style={{ fontSize: 13 }}>{t.id.slice(0, 14)}…</b><br /><small>{t.status}{t.revision !== undefined ? ` · rev ${t.revision}` : ""}</small></div>
              <span className={`yc-st${t.status === "failed" || t.status === "needs_attention" ? " red" : t.status === "completed" ? " green" : ["queued", "waiting_for_resource"].includes(t.status) ? " gray" : ""}`}>{t.error?.code ?? t.status}</span>
            </button>
          ))}
        </div>
        <div className="yc-right">
          <h3 className="lbl">Chi tiết + hành động</h3>
          {!selected ? <div style={{ marginTop: 12 }}><EmptyState text="Chọn một tác vụ bên trái." /></div> : (
            <>
              <div className="yc-big">{selected.id}</div>
              <div className="yc-kv"><span className="yc-pill">{selected.status}</span>{selected.revision !== undefined ? <span className="yc-pill">rev {selected.revision}</span> : null}<span className="yc-pill">tab 0 · autonomous</span></div>
              {selected.error ? <div className="yc-evt">Lỗi <b>{selected.error.code}</b> — {selected.error.message}</div> : null}
              <div className="yc-foot">
                <button className="yc-btn" disabled={pending} onClick={() => stop.mutate(selected.id, { onSuccess: () => setMsg(`Đã dừng ${selected.id}.`), onError: (e) => setMsg(errText(e)) })}>Dừng</button>
                <button className="yc-btn" disabled={pending} onClick={() => waitStop.mutate({ id: selected.id, graceSeconds: 10 }, { onSuccess: () => setMsg(`Đã gửi chờ dừng ${selected.id}.`), onError: (e) => setMsg(errText(e)) })}>Chờ dừng</button>
                <button className="yc-btn" disabled={pending} onClick={() => restart.mutate(selected.id, { onSuccess: () => setMsg(`Đã restart ${selected.id}.`), onError: (e) => setMsg(errText(e)) })}>Restart</button>
                <button className="yc-btn" disabled={pending} onClick={() => resume.mutate(selected.id, { onSuccess: () => setMsg(`Đã resume ${selected.id}.`), onError: (e) => setMsg(errText(e)) })}>Resume</button>
                <button className="yc-btn primary" disabled={approve.isPending} onClick={() => approve.mutate({ id: selected.id }, { onSuccess: () => setMsg(`Đã duyệt ${selected.id}.`), onError: (e) => setMsg(errText(e)) })}>Duyệt</button>
                <button className="yc-btn" disabled={revoke.isPending} onClick={() => revoke.mutate({ id: selected.id }, { onSuccess: () => setMsg(`Đã thu hồi ${selected.id}.`), onError: (e) => setMsg(errText(e)) })}>Thu hồi</button>
              </div>
              <div>{(eventsQ.data ?? []).slice(-5).map((e) => <div key={e.sequence} className="yc-evt">#{e.sequence} {e.type}</div>)}
              {(eventsQ.data ?? []).length === 0 ? <div className="yc-evt">Chưa có sự kiện nào.</div> : null}</div>
            </>
          )}
        </div>
      </div>
    </YoucareShell>
  );
}
