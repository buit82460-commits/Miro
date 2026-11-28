"use client";
import { useState } from "react";

// Workflows — chỉ liệt kê workflow BE có endpoint production.
// Workflow nào BE chưa có EP → card "BE chưa hỗ trợ", không nút chạy, không mock scenario.
type WorkflowDef = {
  id: string;
  name: string;
  description: string;
  supported: boolean;
  endpoint?: string;
};

const WORKFLOWS: WorkflowDef[] = [
  {
    id: "w-threads-publish",
    name: "Threads Publish (W4)",
    description: "prepare → approve → publish dry-run → reconcile → history.",
    supported: true,
    endpoint: "POST /threads/publish",
  },
  {
    id: "w-threads-reconcile",
    name: "Threads Reconcile (W5)",
    description: "Read-only match post_id→tag, verified merge, không replay.",
    supported: true,
    endpoint: "POST /threads/reconcile",
  },
  {
    id: "w-day-plan",
    name: "Day-plan (W6)",
    description: "ensure → day-plan → publish gate (paused/due).",
    supported: true,
    endpoint: "POST /schedule/ensure",
  },
  {
    id: "w-studio-pipeline",
    name: "Studio pipeline (W7)",
    description: "BE READY_WITH_CONDITIONS (cần engine). Chưa mở UI production trong task này.",
    supported: false,
  },
  {
    id: "w-desktop-act",
    name: "Desktop act (W8)",
    description: "BE INTERNAL_ONLY (Notepad pilot OS-level). Không phơi UI công khai.",
    supported: false,
  },
  {
    id: "w-media-analysis",
    name: "Media analysis (W9)",
    description: "BE chưa expose EP riêng (chỉ qua research/studio). Không chạy mock scenario.",
    supported: false,
  },
];

export function WorkflowsPage() {
  const [msg, setMsg] = useState("");

  return (
    <div className="h-full overflow-y-auto p-4 sm:p-6">
      <div className="mx-auto max-w-[1080px] space-y-5">
        <div>
          <h1 className="text-h1 text-[var(--color-text-primary)]">Workflows (BE thật)</h1>
          <p className="text-[13px] text-[var(--color-text-secondary)]">
            Chỉ workflow BE đã có endpoint production mới chạy được. Mục “BE chưa hỗ trợ” không có nút
            chạy, không chạy mock scenario.
          </p>
        </div>
        {msg ? <p data-testid="workflows-msg" className="text-[var(--color-text-secondary)]">{msg}</p> : null}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {WORKFLOWS.map((w) => (
            <div key={w.id} data-testid={`workflow-${w.id}`} className="rounded-[8px] border border-[var(--color-border)] bg-[var(--color-surface-1)] p-5 space-y-2">
              <h2 className="text-h4 text-[var(--color-text-primary)]">{w.name}</h2>
              <p className="text-[13px] text-[var(--color-text-secondary)]">{w.description}</p>
              {w.supported ? (
                <p className="font-mono-tech text-[11px] text-[var(--color-success)]">{w.endpoint} · READY</p>
              ) : (
                <p className="font-mono-tech text-[11px] text-[var(--color-warning)]">BE chưa hỗ trợ — không chạy</p>
              )}
              <div className="pt-2">
                {w.supported ? (
                  <button
                    type="button"
                    onClick={() => setMsg(`${w.name}: mở trang Xuất bản/Lịch để chạy luồng BE thật (${w.endpoint}).`)}
                    className="h-9 rounded-[6px] bg-[var(--color-accent)] px-3 text-[13px]"
                  >
                    Mở luồng BE
                  </button>
                ) : (
                  <button type="button" disabled className="h-9 rounded-[6px] border border-[var(--color-border)] px-3 text-[13px] opacity-50 cursor-not-allowed">
                    BE chưa hỗ trợ
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
