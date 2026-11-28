"use client";

import { useRuntimeStatus } from "@/hooks/data/useRuntime";
import { StatusTag } from "../miro-ui/primitives";

// Banner runtime read-only cho trang browser/overview:
// wiring + bridge tabs từ GET /tasks/runtime/status (không điều khiển tab,
// không hiển thị credential — credential không bao giờ rời BE).
export function RuntimeBridgeBanner() {
  const { data, isLoading, isError } = useRuntimeStatus(10_000);

  if (isLoading) {
    return (
      <div className="rounded-[8px] border border-[var(--color-border)] bg-[var(--color-surface-1)] px-3 py-2 text-[12px] text-[var(--color-text-muted)]">
        Đang đọc trạng thái runtime BE…
      </div>
    );
  }
  if (isError || !data) {
    return (
      <div className="rounded-[8px] border border-[var(--color-error)]/30 bg-[var(--color-error-bg)]/40 px-3 py-2 text-[12px] text-[var(--color-text-secondary)]">
        Chưa nối được BE runtime (kiểm tra BE :8770 / NEXT_PUBLIC_API_BASE). Trang mock vẫn hiển thị.
      </div>
    );
  }

  return (
    <div className="rounded-[8px] border border-[var(--color-border)] bg-[var(--color-surface-1)] px-3 py-2.5 space-y-1.5">
      <div className="flex flex-wrap items-center gap-2 text-[12px]">
        <b className="text-[var(--color-text-primary)]">BE runtime (read-only)</b>
        <StatusTag tone={data.be.status === "ok" ? "success" : "warning"}>
          BE: {data.be.status}
        </StatusTag>
        <StatusTag tone={data.wiring.ok ? "success" : "error"}>
          wiring: {data.wiring.wiring}{data.wiring.ok ? "" : ` (${data.wiring.reason})`}
        </StatusTag>
        <StatusTag tone="neutral">
          bridge tabs: {data.bridge.count}{data.bridge.error ? ` (lỗi: ${data.bridge.error})` : ""}
        </StatusTag>
        <StatusTag tone="neutral">tasks BE: {data.tasks.count}</StatusTag>
      </div>
      {(data.bridge.tabs ?? []).length > 0 ? (
        <ul className="space-y-0.5">
          {(data.bridge.tabs ?? []).slice(0, 6).map((t) => (
            <li
              key={`${t.browser}-${t.tab}`}
              className="font-mono-tech text-[11px] text-[var(--color-text-secondary)] truncate"
            >
              tab {t.tab} · {t.browser} · {t.title || t.url}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-[11px] text-[var(--color-text-muted)]">
          Chưa có bridge tab — verify connections cần tab thật đang mở đúng platform/account.
        </p>
      )}
      <p className="text-[11px] text-[var(--color-text-muted)]">
        Credential không hiển thị ở đây — BE chỉ lưu tham chiếu, không plaintext.
      </p>
    </div>
  );
}
