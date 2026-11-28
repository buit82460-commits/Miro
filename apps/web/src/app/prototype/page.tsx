"use client";

/* Mổ từng menu ChatGPT + Claude (Profile 20, read-only):
   ChatGPT home: nền đen #000, chữ #EDEDED, sidebar đen, composer pill bo lớn giữa, greeting "Good to see you".
   ChatGPT Images: heading + tablist Trending/Templates/My images + lưới nút prompt.
   ChatGPT Explore: heading + search + banner "GPTs will be retired".
   ChatGPT Library: heading + search + nút New + 5 tab Suggested/Favorites/Folders/Images/All + empty "Create something new".
   ChatGPT Scheduled (/scheduled): heading + nút New task + empty + gợi ý mẫu (workouts/budget/dinners...).
   ChatGPT sidebar: New chat, Search, Images, Scheduled, Library, Plugins, Explore, Pinned, Projects, Recents.
   Claude /new: nền #191919, sidebar #1F1F1F, greeting serif "Happy Sunday" + sao cam, composer card bo 12 giữa,
     hàng dưới: + | Chat/Cowork toggle | model Sonnet 5.5 Medium | mic.
   Claude menus: New, Search (Ctrl+Shift+K), Projects, Artifacts, Code+Upgrade, Plugins, Chats and tasks, Templates.
   Ráp cho Miro: sidebar hẹp tối + main giữa hẹp + composer pill + giữ đủ thao tác thật
   (giao việc, guard trùng, duyệt/từ chối/dừng, lọc, 5 tab, nhật ký). */

import { useMemo, useState } from "react";
import "./prototype.css";

type Status = "awaiting_review" | "running" | "queued" | "done" | "rejected" | "stopped";
type Task = { id: string; title: string; channel: string; status: Status; rev: string; log: string[] };

const CHANNELS = ["Threads", "TikTok", "YouTube", "Facebook", "Instagram"];
const PLATS = [
  { n: "Threads", r: "READY", p: "DEGRADED", note: "text + 1 media · 500 ký tự" },
  { n: "TikTok", r: "READY", p: "DEGRADED", note: "draft Studio · poll 5s × 12" },
  { n: "YouTube", r: "READY", p: "READY", note: "Data API · không click" },
  { n: "Facebook", r: "DEGRADED", p: "DEGRADED", note: "Reels · Next × 2" },
];

const STATUS_VI: Record<Status, string> = {
  awaiting_review: "Chờ duyệt",
  running: "Đang chạy",
  queued: "Xếp hàng",
  done: "Xong",
  rejected: "Đã từ chối",
  stopped: "Đã dừng",
};

let seq = 1043;
const nid = () => `dub-${seq++}`;

type Tab = "work" | "lib" | "pub" | "editor" | "settings";

export default function PrototypePage() {
  const [tab, setTab] = useState<Tab>("work");
  const [tasks, setTasks] = useState<Task[]>([
    { id: "dub-1042", title: "Dựng video Threads mở đầu", channel: "Threads", status: "awaiting_review", rev: "r2", log: ["tạo từ chat", "render r2 xong", "chờ bạn duyệt"] },
    { id: "dub-1041", title: "Dịch phụ đề EN sang VI", channel: "YouTube", status: "running", rev: "r5", log: ["đang chạy 42%"] },
    { id: "dub-1039", title: "Render final 60 giây TikTok", channel: "TikTok", status: "queued", rev: "r1", log: ["xếp slot 20:00"] },
  ]);
  const [filter, setFilter] = useState<"all" | Status>("all");
  const [text, setText] = useState("");
  const [channel, setChannel] = useState("Threads");
  const [msg, setMsg] = useState<{ kind: "ok" | "warn" | "err"; text: string } | null>(null);
  const [detail, setDetail] = useState<string | null>("dub-1042");
  const [libTab, setLibTab] = useState("Tất cả");

  const visible = useMemo(
    () => tasks.filter((t) => (filter === "all" ? true : t.status === filter)),
    [tasks, filter]
  );
  const current = tasks.find((t) => t.id === detail) ?? null;
  const waiting = tasks.filter((t) => t.status === "awaiting_review").length;

  const submit = () => {
    const title = text.trim();
    if (!title) return setMsg({ kind: "err", text: "Nhập việc cần giao trước đã." });
    const dup = tasks.some((t) => t.title.toLowerCase() === title.toLowerCase());
    if (dup) return setMsg({ kind: "warn", text: "Trùng việc có sẵn — đã bỏ qua, không tạo mới." });
    const t: Task = { id: nid(), title, channel, status: "queued", rev: "r1", log: [`tạo lúc ${new Date().toLocaleTimeString("vi-VN")}`, `kênh ${channel}`] };
    setTasks((p) => [t, ...p]);
    setDetail(t.id);
    setText("");
    setMsg({ kind: "ok", text: `Đã nhận việc ${t.id} — xếp hàng chờ chạy.` });
  };

  const act = (id: string, kind: "approve" | "reject" | "stop") => {
    setTasks((prev) =>
      prev.map((t) => {
        if (t.id !== id) return t;
        if (kind === "approve") return { ...t, status: "running", log: [...t.log, "bạn đã duyệt → chuyển chạy"] };
        if (kind === "reject") return { ...t, status: "rejected", log: [...t.log, "bạn đã từ chối"] };
        return { ...t, status: "stopped", log: [...t.log, "bạn đã dừng (2 pha + watchdog)"] };
      })
    );
  };

  const NAV: [Tab, string][] = [["work", "Việc"], ["lib", "Thư viện"], ["pub", "Xuất bản"], ["editor", "Editor"], ["settings", "Cài đặt"]];

  return (
    <div className="app">
      <aside className="side">
        <div className="brand"><span className="brand-mark" />Miro</div>
        <button type="button" className="newchat" onClick={() => { setTab("work"); setDetail(null); }}>+ Việc mới</button>
        <button type="button" className="searchbtn" onClick={() => setTab("work")}>Tìm việc…</button>
        <nav className="nav" aria-label="Chính">
          {NAV.map(([k, label]) => (
            <button key={k} type="button" onClick={() => setTab(k)} className={`navbtn${tab === k ? " on" : ""}`} aria-current={tab === k}>
              {label}
              {k === "work" && waiting > 0 && <span className="count">{waiting}</span>}
            </button>
          ))}
        </nav>
        <p className="seclabel">Gần đây</p>
        <ul className="recents">
          {tasks.map((t) => (
            <li key={t.id}>
              <button type="button" onClick={() => { setDetail(t.id); setTab("work"); }} className={detail === t.id ? "on" : ""}>
                <span className="mono">{t.id}</span> {t.title}
              </button>
            </li>
          ))}
        </ul>
        <div className="sidefoot"><span className="dot" />Dữ liệu thử trong trang · dry-run</div>
      </aside>

      <main className="main">
        <div className="col">
          {tab === "work" && (
            <>
              <h1 className="greet">Giao việc đi, còn lại để Miro lo.</h1>
              <div className="composer" role="form" aria-label="Giao việc mới">
                <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Giao việc cho Miro…" rows={2} />
                <div className="composer-bar">
                  <select value={channel} onChange={(e) => setChannel(e.target.value)} aria-label="Kênh đăng">
                    {CHANNELS.map((c) => (<option key={c}>{c}</option>))}
                  </select>
                  <span className="hint">Trùng thì bỏ qua · thiếu biên nhận giữ UNKNOWN</span>
                  <button type="button" className="send" onClick={submit} aria-label="Gửi việc">↑</button>
                </div>
                {msg && <p className={`flash ${msg.kind}`} role="status">{msg.text}</p>}
              </div>
              <div className="suggest">
                <button type="button" onClick={() => setFilter("awaiting_review")}>Việc chờ duyệt ({waiting})</button>
                <button type="button" onClick={() => setFilter("running")}>Đang chạy</button>
                <button type="button" onClick={() => setFilter("queued")}>Xếp hàng</button>
                <button type="button" onClick={() => setFilter("all")}>Tất cả</button>
              </div>

              <ul className="rows">
                {visible.map((t) => (
                  <li key={t.id} className={`row${detail === t.id ? " sel" : ""}`}>
                    <button type="button" className="rowmain" onClick={() => setDetail(t.id)}>
                      <strong className="mono">{t.id}</strong>
                      <span className="rowtitle">{t.title}</span>
                      <span className={`st st-${t.status}`}>{STATUS_VI[t.status]}</span>
                    </button>
                    <span className="rowmeta">{t.channel} · {t.rev}</span>
                    {(t.status === "awaiting_review" || t.status === "running" || t.status === "queued") && (
                      <span className="rowact">
                        {t.status === "awaiting_review" && (<>
                          <button type="button" className="btn-ok sm" onClick={() => act(t.id, "approve")}>Duyệt</button>
                          <button type="button" className="btn-ghost sm" onClick={() => act(t.id, "reject")}>Từ chối</button>
                        </>)}
                        <button type="button" className="btn-ghost sm" onClick={() => act(t.id, "stop")}>Dừng</button>
                      </span>
                    )}
                  </li>
                ))}
                {visible.length === 0 && <li className="empty">Không có việc ở trạng thái này.</li>}
              </ul>

              <aside className="detail" aria-label="Chi tiết việc">
                {current ? (<>
                  <p className="mono dim">{current.id} · {current.rev} · {current.channel} · <span className={`st st-${current.status}`}>{STATUS_VI[current.status]}</span></p>
                  <h3>{current.title}</h3>
                  <ol className="log">{current.log.map((l, i) => (<li key={i}>{l}</li>))}</ol>
                </>) : (<p className="dim">Chọn một việc để xem nhật ký.</p>)}
              </aside>
            </>
          )}

          {tab === "lib" && (
            <>
              <h1 className="greet sm">Thư viện</h1>
              <div className="tabs" role="tablist" aria-label="Thư viện">
                {["Gợi ý", "Tất cả", "Ảnh", "Tài liệu"].map((x) => (
                  <button key={x} type="button" role="tab" aria-selected={libTab === x} className={libTab === x ? "on" : ""} onClick={() => setLibTab(x)}>{x}</button>
                ))}
              </div>
              <div className="grid3">
                {tasks.map((t) => (
                  <article key={t.id} className="card">
                    <div className="cover" aria-hidden>{t.title.slice(0, 1)}</div>
                    <strong>{t.title}</strong>
                    <span className="mono dim">{t.id} · {t.channel}</span>
                    <span className={`st st-${t.status}`}>{STATUS_VI[t.status]}</span>
                  </article>
                ))}
              </div>
              {tasks.length === 0 && <p className="dim">Chưa có gì — giao việc đầu tiên từ tab Việc.</p>}
            </>
          )}

          {tab === "pub" && (
            <>
              <h1 className="greet sm">Xuất bản</h1>
              <p className="lede">Một platform một adapter duy nhất. Kênh yếu ghi rõ, không giấu.</p>
              <ul className="plats">
                {PLATS.map((p) => (
                  <li key={p.n}>
                    <strong>{p.n}</strong>
                    <span className="mono">Đọc {p.r} · Đăng {p.p}</span>
                    <span className="dim">{p.note}</span>
                  </li>
                ))}
              </ul>
            </>
          )}

          {tab === "editor" && (
            <>
              <h1 className="greet sm">Editor</h1>
              <p className="lede">Timeline của việc đang chọn — sửa từng câu ngay tại chỗ.</p>
              {current ? <EditorBox title={current.title} /> : <p className="dim">Chưa chọn việc nào.</p>}
            </>
          )}

          {tab === "settings" && (
            <>
              <h1 className="greet sm">Cài đặt</h1>
              <SettingsBox />
            </>
          )}
        </div>
      </main>
    </div>
  );
}

function EditorBox({ title }: { title: string }) {
  const [lines, setLines] = useState(["Mở đầu: chào tuần mới", "Vào việc: dựng khung chính", "Kết: kêu gọi đăng ký"]);
  return (
    <div className="panel">
      <p className="mono dim">{title}</p>
      <ol className="tl">
        {lines.map((l, i) => (
          <li key={i}>
            <span className="mono dim">00:{String(i * 10).padStart(2, "0")}</span>
            <input value={l} onChange={(e) => setLines((p) => p.map((x, j) => (j === i ? e.target.value : x)))} aria-label={`Câu ${i + 1}`} />
          </li>
        ))}
      </ol>
    </div>
  );
}

function SettingsBox() {
  const [dry, setDry] = useState(true);
  const [slot, setSlot] = useState("20:00");
  return (
    <div className="panel">
      <label className="switch">
        <input type="checkbox" checked={dry} onChange={(e) => setDry(e.target.checked)} />
        Chế độ khô — thao tác nguy hiểm dừng ở bước duyệt
      </label>
      <label className="field">Slot đăng mỗi ngày
        <select value={slot} onChange={(e) => setSlot(e.target.value)}>
          <option>08:00</option><option>12:00</option><option>20:00</option>
        </select>
      </label>
      <p className="dim">Đang: {dry ? "giữ an toàn" : "cho phép đăng"} · slot {slot} · UNKNOWN giữ nguyên, không đăng lại tự động.</p>
    </div>
  );
}
