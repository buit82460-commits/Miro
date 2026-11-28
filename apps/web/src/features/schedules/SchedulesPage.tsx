"use client";
import { useCallback, useEffect, useState } from "react";
import { ensureDayPlan, fetchDayPlan, mapThreadsError, patchDayPlanStatus } from "@/lib/threads/flow";

type DayPlan = {
  date?: string;
  status?: string;
  slots?: Array<{ intent_id?: string; state?: string; platform?: string } & Record<string, unknown>>;
};

// Schedules — chỉ từ BE: GET /schedule/day-plan + ensure + status.
// 404 NO_DAY_PLAN → empty + CTA ensure. BE down → 502 + message, không mẫu.
export function SchedulesPage() {
  const [plan, setPlan] = useState<DayPlan | null>(null);
  const [msg, setMsg] = useState("");
  const [msgKind, setMsgKind] = useState<"info" | "error">("info");
  const [busy, setBusy] = useState(false);
  const [noPlan, setNoPlan] = useState(false);

  const say = (m: string, kind: "info" | "error" = "info") => {
    setMsg(m);
    setMsgKind(kind);
  };

  const load = useCallback(async () => {
    setBusy(true);
    setMsg("");
    setNoPlan(false);
    try {
      setPlan(await fetchDayPlan());
    } catch (e) {
      const f = mapThreadsError(e);
      if (f.code === "NO_DAY_PLAN" || /NO_DAY_PLAN|chưa có day-plan/i.test(f.message)) {
        setNoPlan(true);
        setPlan(null);
        say("Chưa có day-plan (NO_DAY_PLAN). Bấm “Ensure day-plan” để tạo.", "info");
      } else {
        setPlan(null);
        say(`${f.code}: ${f.message} Hành động: ${f.action}`, "error");
      }
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const onEnsure = async () => {
    setBusy(true);
    try {
      const r = await ensureDayPlan();
      say(`Ensure OK — action=${r.action}${r.date ? ` date=${r.date}` : ""}.`);
      await load();
    } catch (e) {
      const f = mapThreadsError(e);
      say(`${f.code}: ${f.message} Hành động: ${f.action}`, "error");
    } finally {
      setBusy(false);
    }
  };

  const onStatus = async (status: "active" | "paused") => {
    setBusy(true);
    try {
      const r = await patchDayPlanStatus(status);
      say(`Day-plan → ${r.status}.`);
      await load();
    } catch (e) {
      const f = mapThreadsError(e);
      say(`${f.code}: ${f.message} Hành động: ${f.action}`, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-4 sm:p-6">
      <div className="mx-auto max-w-[960px] space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-h1 text-[var(--color-text-primary)]">Lịch chạy (BE thật)</h1>
            <p className="text-[13px] text-[var(--color-text-secondary)]">
              Chỉ đọc từ BE (<code>GET /schedule/day-plan</code>). BE down → lỗi 502, không lịch mẫu.
            </p>
          </div>
          <div className="flex gap-2">
            <button type="button" disabled={busy} onClick={load} className="h-9 rounded-[6px] border border-[var(--color-border)] px-3 text-[13px]">Tải lại</button>
            <button type="button" disabled={busy} onClick={onEnsure} className="h-9 rounded-[6px] bg-[var(--color-accent)] px-3 text-[13px]">Ensure day-plan</button>
          </div>
        </div>

        {msg ? (
          <p data-testid="schedules-msg" className={msgKind === "error" ? "text-[var(--color-error)]" : "text-[var(--color-text-secondary)]"}>{msg}</p>
        ) : null}

        {noPlan ? (
          <div data-testid="schedules-empty" className="rounded-[8px] border border-dashed border-[var(--color-border-strong)] p-6 text-center space-y-3">
            <p className="text-[14px] text-[var(--color-text-secondary)]">Chưa có day-plan nào (NO_DAY_PLAN).</p>
            <button type="button" disabled={busy} onClick={onEnsure} className="h-9 rounded-[6px] bg-[var(--color-accent)] px-4 text-[13px]">Ensure day-plan ngay</button>
          </div>
        ) : plan ? (
          <div className="rounded-[8px] border border-[var(--color-border)] bg-[var(--color-surface-1)] p-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-h4">Day-plan {plan.date ?? ""} · {plan.status ?? "?"}</p>
              <div className="flex gap-2">
                <button type="button" disabled={busy} onClick={() => onStatus("active")} className="h-8 rounded-[6px] border border-[var(--color-border)] px-3 text-[12px]">Active</button>
                <button type="button" disabled={busy} onClick={() => onStatus("paused")} className="h-8 rounded-[6px] border border-[var(--color-border)] px-3 text-[12px]">Pause</button>
              </div>
            </div>
            <div className="space-y-1.5">
              {(plan.slots ?? []).map((s, i) => (
                <p key={i} className="text-[13px] font-mono-tech text-[var(--color-text-secondary)]">
                  {String(s.intent_id ?? `#${i}`)} · {String(s.state ?? "?")} · {String(s.platform ?? "")}
                </p>
              ))}
              {(plan.slots ?? []).length === 0 ? <p className="text-[13px] text-[var(--color-text-muted)]">Day-plan rỗng — không có slot nào.</p> : null}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
