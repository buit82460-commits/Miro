"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { YoucareShell } from "@/components/youcare/YoucareShell";
import { MiroApiError } from "@/lib/api/http";
import { isCredentialRef } from "@/lib/services/connections.service";
import {
  accountCreateSchema,
  verifyEvidenceSchema,
  type AccountCreateInput,
  type VerifyEvidenceInput,
} from "@/lib/schemas/miro.schema";
import {
  useConnectionAccounts,
  useConnectionDefault,
  useCreateAccount,
  usePauseAccount,
  useReconnectAccount,
  useRevokeAccount,
  useSetDefaultAccount,
  useVerifyAccount,
} from "@/hooks/data/useConnections";

function errMsg(e: unknown): string {
  if (e instanceof MiroApiError) {
    switch (e.kind) {
      case "NETWORK":
        return e.message;
      case "NOT_FOUND":
        return `Không tìm thấy: ${e.message}`;
      case "BAD_REQUEST":
        return `BE từ chối: ${e.message}`;
      case "CONFLICT":
        return `Trùng/phiên cũ: ${e.message}`;
      case "VALIDATION":
        return `Dữ liệu chưa hợp lệ: ${e.message}`;
      case "UNAVAILABLE":
        return `Chưa sẵn sàng: ${e.message}`;
      default:
        return `Lỗi BE: ${e.message}`;
    }
  }
  return `Thất bại: ${(e as Error).message}`;
}

function statusBadge(status: string) {
  const style =
    status === "connected"
      ? { background: "#e6f4ea", color: "#137333" }
      : status === "paused" || status === "pending"
        ? { background: "#fef7e0", color: "#b06000" }
        : status === "revoked"
          ? { background: "#fce8e6", color: "#a50e0e" }
          : { background: "#f1f3f4", color: "#5f6368" };
  return <span style={{ borderRadius: 12, padding: "2px 10px", fontSize: 12, ...style }}>{status}</span>;
}

export default function ConnectionsPage() {
  const [platformFilter, setPlatformFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [defaultPlatform, setDefaultPlatform] = useState("tiktok");
  const [msg, setMsg] = useState("");
  const [evidenceFor, setEvidenceFor] = useState<string | null>(null);

  const { data, isLoading, isError, refetch } = useConnectionAccounts(platformFilter, statusFilter);
  const { data: defaultRes } = useConnectionDefault(defaultPlatform || undefined);
  const create = useCreateAccount();
  const verify = useVerifyAccount();
  const pause = usePauseAccount();
  const reconnect = useReconnectAccount();
  const revoke = useRevokeAccount();
  const setDefault = useSetDefaultAccount();

  const createForm = useForm<AccountCreateInput>({
    resolver: zodResolver(accountCreateSchema),
    defaultValues: {
      platform: "",
      account_id: "",
      display_name: "",
      credential_ref: "",
      profile_binding_id: "",
      browser_instance_id: "",
    },
  });

  const evidenceForm = useForm<VerifyEvidenceInput>({
    resolver: zodResolver(verifyEvidenceSchema),
    defaultValues: {
      tab_id: "",
      platform_id: "",
      profile_binding_id: "",
      observed_account_id: "",
      target_id: "",
      browser_instance_id: "",
      window_id: "",
      observed_account_id_after: "",
      profile_path: "",
      profile_path_after: "",
    },
  });

  const onCreate = (input: AccountCreateInput) => {
    setMsg("");
    create.mutate(input, {
      onSuccess: (a) => {
        setMsg(`Đã thêm ${a.id} (status=${a.status}). Verify bằng evidence tab thật để connected.`);
        createForm.reset();
      },
      onError: (e) => setMsg(errMsg(e)),
    });
  };

  const runVerify = (id: string, input: VerifyEvidenceInput, mode: "verify" | "reconnect") => {
    setMsg("");
    const done = {
      onSuccess: (a: { id: string; status: string }) => {
        setMsg(`${mode === "verify" ? "Đã verify" : "Đã kết nối lại"} ${a.id} → ${a.status}.`);
        setEvidenceFor(null);
      },
      onError: (e: unknown) => setMsg(errMsg(e)),
    };
    if (mode === "verify") verify.mutate({ id, evidence: input }, done);
    else reconnect.mutate({ id, evidence: input }, done);
  };

  return (
    <YoucareShell title="Kết nối" subtitle="Accounts CRUD thật qua BE — verify bằng evidence từ tab thật.">
      <h1 data-testid="connections-title" style={{ display: "none" }}>Cài đặt → Kết nối</h1>
      {isLoading ? <p>Đang tải danh sách tài khoản…</p> : null}
      {isError ? <p style={{ color: "#B52E2E" }}>Chưa nối được BE (kiểm tra BE :8770 / NEXT_PUBLIC_API_BASE).</p> : null}
      {msg ? <p data-testid="connections-msg">{msg}</p> : null}

      <section style={{ display: "flex", gap: 8, margin: "16px 0", alignItems: "center" }}>
        <label>
          Lọc platform{" "}
          <input
            data-testid="connections-filter-platform"
            value={platformFilter}
            onChange={(e) => setPlatformFilter(e.target.value)}
            placeholder="tiktok"
            style={{ width: 140 }}
          />
        </label>
        <label>
          Lọc status{" "}
          <input
            data-testid="connections-filter-status"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            placeholder="connected"
            style={{ width: 140 }}
          />
        </label>
        <button data-testid="connections-refresh" onClick={() => refetch()}>
          Tải lại
        </button>
      </section>

      <section
        data-testid="connections-form-section"
        style={{ margin: "16px 0", padding: 16, border: "1px solid #dadce0", borderRadius: 8 }}
      >
        <h2>Thêm tài khoản (credential = tham chiếu, không secret thật)</h2>
        <form
          data-testid="connections-form"
          onSubmit={createForm.handleSubmit(onCreate)}
          style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 720 }}
        >
          <label>
            Platform{" "}
            <input data-testid="connections-platform" {...createForm.register("platform")} placeholder="tiktok" />
          </label>
          {createForm.formState.errors.platform ? (
            <p style={{ color: "#B52E2E" }}>{createForm.formState.errors.platform.message}</p>
          ) : null}
          <label>
            Account id{" "}
            <input data-testid="connections-account-id" {...createForm.register("account_id")} placeholder="kemkhongta" />
          </label>
          {createForm.formState.errors.account_id ? (
            <p style={{ color: "#B52E2E" }}>{createForm.formState.errors.account_id.message}</p>
          ) : null}
          <label>
            Tên hiển thị{" "}
            <input data-testid="connections-display-name" {...createForm.register("display_name")} placeholder="Kênh TikTok" />
          </label>
          <label>
            Credential ref{" "}
            <input
              data-testid="connections-credential-ref"
              {...createForm.register("credential_ref")}
              placeholder="vault:miro/tiktok/kemkhongta"
              style={{ minWidth: 320 }}
            />
          </label>
          {createForm.formState.errors.credential_ref ? (
            <p style={{ color: "#B52E2E" }}>{createForm.formState.errors.credential_ref.message}</p>
          ) : null}
          <div style={{ display: "flex", gap: 8 }}>
            <label>
              Profile binding{" "}
              <input data-testid="connections-profile-binding" {...createForm.register("profile_binding_id")} placeholder="prof-1" />
            </label>
            <label>
              Browser instance{" "}
              <input data-testid="connections-browser-instance" {...createForm.register("browser_instance_id")} placeholder="inst-1" />
            </label>
          </div>
          <button data-testid="connections-submit" type="submit" disabled={create.isPending}>
            {create.isPending ? "Đang thêm…" : "Thêm tài khoản"}
          </button>
        </form>
      </section>

      <section style={{ margin: "16px 0" }}>
        <h2>Default theo platform</h2>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            data-testid="connections-default-platform"
            value={defaultPlatform}
            onChange={(e) => setDefaultPlatform(e.target.value)}
            placeholder="tiktok"
            style={{ width: 160 }}
          />
          <span data-testid="connections-default-result">
            {defaultRes
              ? `${defaultRes.platform} → ${defaultRes.account ? JSON.stringify(defaultRes.account) : "chưa có"} (${defaultRes.source})`
              : "…"}
          </span>
        </div>
      </section>

      <section style={{ margin: "16px 0" }}>
        <h2>Danh sách ({(data ?? []).length})</h2>
        <ul data-testid="connections-list" style={{ listStyle: "none", padding: 0 }}>
          {(data ?? []).map((a) => (
            <li
              key={a.id}
              data-testid={`connection-${a.id}`}
              style={{ border: "1px solid #ddd", borderRadius: 10, padding: 12, marginBottom: 8, background: "#fff" }}
            >
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <b>{a.id}</b>
                {statusBadge(a.status)}
                {a.is_default ? <span data-testid={`connection-default-${a.id}`}>· default</span> : null}
              </div>
              <p style={{ color: "#5f6368", margin: "4px 0" }}>
                credential_ref:{" "}
                <code data-testid={`connection-cred-${a.id}`}>
                  {a.credential_ref
                    ? isCredentialRef(a.credential_ref)
                      ? a.credential_ref
                      : "ref (đã ẩn giá trị)"
                    : "(đã thu hồi / chưa có)"}
                </code>
                {" · "}profile: {a.profile_binding_id || "—"}
                {" · "}verified: {a.verified_at ? new Date(a.verified_at * 1000).toISOString() : "chưa"}
                {a.evidence_sha ? ` · evidence ${a.evidence_sha.slice(0, 12)}…` : ""}
              </p>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button
                  data-testid={`connection-verify-${a.id}`}
                  onClick={() => {
                    setEvidenceFor(`verify:${a.id}`);
                    evidenceForm.reset({
                      tab_id: "",
                      platform_id: a.platform,
                      profile_binding_id: a.profile_binding_id ?? "",
                      observed_account_id: a.account_id,
                      target_id: "",
                      browser_instance_id: a.browser_instance_id ?? "",
                      window_id: "",
                      observed_account_id_after: "",
                      profile_path: "",
                      profile_path_after: "",
                    });
                  }}
                >
                  Verify (tab thật)
                </button>
                <button
                  data-testid={`connection-reconnect-${a.id}`}
                  onClick={() => {
                    setEvidenceFor(`reconnect:${a.id}`);
                    evidenceForm.reset({
                      tab_id: "",
                      platform_id: a.platform,
                      profile_binding_id: a.profile_binding_id ?? "",
                      observed_account_id: a.account_id,
                      target_id: "",
                      browser_instance_id: a.browser_instance_id ?? "",
                      window_id: "",
                      observed_account_id_after: "",
                      profile_path: "",
                      profile_path_after: "",
                    });
                  }}
                >
                  Kết nối lại
                </button>
                <button
                  data-testid={`connection-pause-${a.id}`}
                  onClick={() =>
                    pause.mutate(a.id, {
                      onSuccess: (r) => setMsg(`Đã tạm dừng ${r.id} → ${r.status}.`),
                      onError: (e) => setMsg(errMsg(e)),
                    })
                  }
                >
                  Tạm dừng
                </button>
                <button
                  data-testid={`connection-set-default-${a.id}`}
                  onClick={() =>
                    setDefault.mutate(a.id, {
                      onSuccess: (r) => setMsg(`Đã đặt ${r.id} làm default ${r.platform}.`),
                      onError: (e) => setMsg(errMsg(e)),
                    })
                  }
                >
                  Đặt default
                </button>
                <button
                  data-testid={`connection-revoke-${a.id}`}
                  onClick={() => {
                    if (!window.confirm(`Thu hồi ${a.id}? Credential ref sẽ bị xóa.`)) return;
                    revoke.mutate(a.id, {
                      onSuccess: (r) => setMsg(`Đã thu hồi ${r.id} → ${r.status}.`),
                      onError: (e) => setMsg(errMsg(e)),
                    });
                  }}
                >
                  Thu hồi
                </button>
              </div>
              {evidenceFor === `verify:${a.id}` || evidenceFor === `reconnect:${a.id}` ? (
                <form
                  data-testid={`connection-evidence-${a.id}`}
                  onSubmit={evidenceForm.handleSubmit((v) =>
                    runVerify(a.id, v, evidenceFor.startsWith("verify") ? "verify" : "reconnect"),
                  )}
                  style={{ marginTop: 8, padding: 8, border: "1px solid #eee", borderRadius: 8, display: "flex", flexDirection: "column", gap: 6, maxWidth: 640 }}
                >
                  <b>VerifyEvidence từ tab thật đang mở ({a.platform})</b>
                  <label>
                    tab_id <input data-testid={`evidence-tab-${a.id}`} {...evidenceForm.register("tab_id")} />
                  </label>
                  <label>
                    observed_account_id (đọc từ tab){" "}
                    <input data-testid={`evidence-observed-${a.id}`} {...evidenceForm.register("observed_account_id")} />
                  </label>
                  <label>
                    target_id <input {...evidenceForm.register("target_id")} />
                  </label>
                  {evidenceForm.formState.errors.tab_id || evidenceForm.formState.errors.observed_account_id ? (
                    <p style={{ color: "#B52E2E" }}>Nhập tab_id + observed_account_id khớp account.</p>
                  ) : null}
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      data-testid={`evidence-submit-${a.id}`}
                      type="submit"
                      disabled={verify.isPending || reconnect.isPending}
                    >
                      {evidenceFor.startsWith("verify") ? "Gửi verify" : "Gửi kết nối lại"}
                    </button>
                    <button type="button" onClick={() => setEvidenceFor(null)}>
                      Hủy
                    </button>
                  </div>
                </form>
              ) : null}
            </li>
          ))}
        </ul>
      </section>
    </YoucareShell>
  );
}
