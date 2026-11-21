"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import MiroNav from "@/components/miro-nav";
import { useLibrary } from "@/hooks/data/useMiro";
import { usePublishBatches, useReceipts, useSubmitBatch } from "@/hooks/data/useMiro";
import { publishBatchSchema, type PublishBatchInput } from "@/lib/schemas/miro.schema";

const PLATFORMS = ["threads", "facebook", "tiktok", "youtube", "instagram"] as const;

export default function PublishPage() {
  const { data: videos } = useLibrary();
  const { data: batches } = usePublishBatches();
  const { data: receipts } = useReceipts();
  const submit = useSubmitBatch();
  const [msg, setMsg] = useState("");

  const form = useForm<PublishBatchInput>({
    resolver: zodResolver(publishBatchSchema),
    defaultValues: { video_id: "p1", platform: "threads", account: "@miro.demo" },
  });

  const onSubmit = (input: PublishBatchInput) => {
    setMsg("");
    submit.mutate(input, {
      onSuccess: (b) => {
        const status = String((b as Record<string, unknown>).status);
        const src = String((b as Record<string, unknown>).source ?? "fixture");
        const detail = String((b as Record<string, unknown>).backend_detail ?? "");
        const sample = src === "backend" ? "" : " (DỮ LIỆU MẪU — chưa đăng thật)";
        setMsg(`Đã gửi batch ${String((b as Record<string, unknown>).id)} — trạng thái ${status}${sample}. ${detail}`);
      },
      onError: (e) => setMsg(`Xuất bản thất bại: ${(e as Error).message}`),
    });
  };

  return (
    <MiroNav>
      <h1 data-testid="publish-title">Xuất bản</h1>
      <p data-testid="publish-sample-note" style={{ background: "#FFF7D6", border: "1px solid #E3C400", borderRadius: 8, padding: "6px 10px", maxWidth: 760 }}>
        DỮ LIỆU MẪU — chưa đăng thật. Batch Threads gọi BE <code>POST /threads/publish</code> ở chế độ
        dry-run (không post thật); chỉ khi BE không reachable mới dùng receipt mẫu (có gắn nhãn mẫu).
      </p>
      <p>Batch theo video × platform × account. Receipt bên dưới dùng để đối soát.</p>

      <form
        data-testid="publish-form"
        onSubmit={form.handleSubmit(onSubmit)}
        style={{ display: "flex", gap: 8, flexWrap: "wrap", maxWidth: 760, marginBottom: 8 }}
      >
        <label>
          Video{" "}
          <select data-testid="publish-video" {...form.register("video_id")}>
            {(videos ?? []).map((v) => (
              <option key={String(v.id)} value={String(v.id)}>
                {String(v.title)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Platform{" "}
          <select data-testid="publish-platform" {...form.register("platform")}>
            {PLATFORMS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <label>
          Tài khoản{" "}
          <input
            data-testid="publish-account"
            {...form.register("account")}
            placeholder="@miro.demo"
            style={{ border: "1px solid #ccc", borderRadius: 8, padding: "6px 10px" }}
          />
        </label>
        <button data-testid="publish-submit" type="submit" disabled={submit.isPending}>
          {submit.isPending ? "Đang gửi…" : "Đăng / lên lịch"}
        </button>
      </form>
      {form.formState.errors.video_id ? <p style={{ color: "#B52E2E" }}>Chọn video</p> : null}
      {form.formState.errors.account ? (
        <p style={{ color: "#B52E2E" }}>{form.formState.errors.account.message}</p>
      ) : null}
      {msg ? <p data-testid="publish-msg">{msg}</p> : null}

      <h2>Batch đã gửi</h2>
      <ul data-testid="batch-list">
        {(batches ?? []).map((b) => (
          <li key={String(b.id)} data-testid={`batch-${String(b.id)}`}>
            {String(b.id)} · {String(b.video_id)} · {String(b.platform)} · {String(b.account)} ·{" "}
            <b data-testid={`batch-status-${String(b.id)}`}>{String(b.status)}</b>
            {String((b as Record<string, unknown>).source ?? "fixture") === "backend" ? (
              <span data-testid={`batch-source-${String(b.id)}`}> · BE thật (dry-run)</span>
            ) : (
              <span data-testid={`batch-source-${String(b.id)}`}> · DỮ LIỆU MẪU — chưa đăng thật</span>
            )}
            {(b as Record<string, unknown>).backend_detail ? (
              <span data-testid={`batch-detail-${String(b.id)}`}> · {String((b as Record<string, unknown>).backend_detail)}</span>
            ) : null}
          </li>
        ))}
      </ul>

      <h2>Receipt / đối soát</h2>
      <ul data-testid="receipt-list">
        {(receipts ?? []).map((r) => (
          <li key={r.id} data-testid={`receipt-${r.id}`}>
            {r.platform}/{r.account} ·{" "}
            <b data-testid={`receipt-status-${r.id}`}>{r.status}</b>
            {String((r as Record<string, unknown>).source ?? "fixture") === "backend" ? (
              <span data-testid={`receipt-source-${r.id}`}> · BE thật</span>
            ) : (
              <span data-testid={`receipt-source-${r.id}`}> · DỮ LIỆU MẪU — chưa đăng thật</span>
            )}
            {r.post_url ? (
              <>
                {" · "}
                <a data-testid={`receipt-url-${r.id}`} href={r.post_url} target="_blank" rel="noreferrer">
                  {r.post_url}
                </a>
              </>
            ) : null}
            {r.post_id ? <span data-testid={`receipt-postid-${r.id}`}> · post {r.post_id}</span> : null}
          </li>
        ))}
      </ul>
    </MiroNav>
  );
}
