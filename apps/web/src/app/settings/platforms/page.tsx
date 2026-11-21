"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import MiroNav from "@/components/miro-nav";
import {
  useClonePlatform,
  usePlatforms,
  useRollbackRegistry,
  useUpsertPlatform,
} from "@/hooks/data/useMiro";
import {
  platformCloneSchema,
  platformUpsertSchema,
  rollbackSchema,
  type PlatformUpsertInput,
} from "@/lib/schemas/miro.schema";

const CAPS = ["list", "download", "draft", "publish", "reconcile", "watch"] as const;
const READ_CAPS = ["list", "download", "reconcile", "watch"];
const PUB_CAPS = ["draft", "publish"];

function badge(s: string) {
  const style =
    s === "SUPPORTED" || s === "READY"
      ? { background: "#e6f4ea", color: "#137333" }
      : s === "PARTIAL" || s === "DEGRADED"
        ? { background: "#fef7e0", color: "#b06000" }
        : s === "BLOCKED"
          ? { background: "#fce8e6", color: "#a50e0e" }
          : { background: "#f1f3f4", color: "#5f6368" };
  return <span style={{ borderRadius: 12, padding: "2px 10px", fontSize: 12, ...style }}>{s}</span>;
}

const CAP_KEY_OPTIONS = ["list", "download", "draft", "publish", "reconcile", "watch"] as const;
const CAP_STATUS_OPTIONS = ["SUPPORTED", "PARTIAL", "BLOCKED", "UNKNOWN"] as const;

export default function PlatformsPage() {
  const { data, isLoading, isError } = usePlatforms();
  const upsert = useUpsertPlatform();
  const clone = useClonePlatform();
  const rollback = useRollbackRegistry();
  const [msg, setMsg] = useState("");
  const [cloneId, setCloneId] = useState("");

  const form = useForm<PlatformUpsertInput>({
    resolver: zodResolver(platformUpsertSchema),
    defaultValues: {
      id: "",
      name: "",
      runtime: "",
      accounts: [],
      track_read: "UNKNOWN",
      track_publish: "UNKNOWN",
      capabilities: [],
    },
  });
  const capsField = useFieldArray<PlatformUpsertInput, "capabilities", "id">({
    control: form.control,
    name: "capabilities",
  });
  const [accountDraft, setAccountDraft] = useState("");
  const accountList = form.watch("accounts") ?? [];

  const rollbackForm = useForm<{ version: number }>({
    resolver: zodResolver(rollbackSchema),
    defaultValues: { version: 1 },
  });

  const onUpsert = (input: PlatformUpsertInput) => {
    setMsg("");
    upsert.mutate(input, {
      onSuccess: (r) => {
        setMsg(`Đã đăng ký/cập nhật ${input.id} — registry v${r.version}.`);
        form.reset({
          id: "",
          name: "",
          runtime: "",
          accounts: [],
          track_read: "UNKNOWN",
          track_publish: "UNKNOWN",
          capabilities: [],
        });
      },
      onError: (e) => setMsg(`Lưu thất bại: ${(e as Error).message}`),
    });
  };

  return (
    <MiroNav>
      <h1 data-testid="platforms-title">Cài đặt → Nền tảng</h1>
      <p>
        Registry version <b data-testid="registry-version">{data?.version ?? "…"}</b> · đọc
        (list/download/reconcile/watch) và đăng (draft/publish) tách riêng · update + rollback giữ
        task cũ (task pin version).
      </p>
      {isLoading ? <p>Đang tải registry nền tảng…</p> : null}
      {isError ? <p style={{ color: "#B52E2E" }}>Chưa nối được BE.</p> : null}
      {msg ? <p data-testid="platforms-msg">{msg}</p> : null}

      <section
        data-testid="platform-form-section"
        style={{ margin: "16px 0", padding: 16, border: "1px solid #dadce0", borderRadius: 8 }}
      >
        <h2>Thêm / cập nhật platform (form phức tạp)</h2>
        <form
          data-testid="platform-form"
          onSubmit={form.handleSubmit(onUpsert)}
          style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 720 }}
        >
          <label>
            id (vd: zalo){" "}
            <input data-testid="platform-id" {...form.register("id")} placeholder="threads" />
          </label>
          {form.formState.errors.id ? (
            <p style={{ color: "#B52E2E" }}>{form.formState.errors.id.message}</p>
          ) : null}
          <label>
            Tên hiển thị{" "}
            <input data-testid="platform-name" {...form.register("name")} placeholder="Threads" />
          </label>
          {form.formState.errors.name ? (
            <p style={{ color: "#B52E2E" }}>{form.formState.errors.name.message}</p>
          ) : null}
          <label>
            Runtime (adapter… ){" "}
            <input
              data-testid="platform-runtime"
              {...form.register("runtime")}
              placeholder="adapter threads v1"
              style={{ minWidth: 320 }}
            />
          </label>
          {form.formState.errors.runtime ? (
            <p style={{ color: "#B52E2E" }}>{form.formState.errors.runtime.message}</p>
          ) : null}

          <div>
            <b>Tài khoản ({accountList.length}/20)</b>
            <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
              <input
                data-testid="platform-account-draft"
                value={accountDraft}
                onChange={(e) => setAccountDraft(e.target.value)}
                placeholder="@miro.demo"
              />
              <button
                type="button"
                data-testid="platform-account-add"
                onClick={() => {
                  if (!accountDraft.trim()) return;
                  form.setValue("accounts", [...accountList, accountDraft.trim()], {
                    shouldValidate: true,
                  });
                  setAccountDraft("");
                }}
              >
                Thêm tài khoản
              </button>
            </div>
            <ul data-testid="platform-accounts">
              {accountList.map((a, i) => (
                <li key={`${a}-${i}`} data-testid={`platform-account-${i}`}>
                  <input {...form.register(`accounts.${i}` as const)} />
                  <button
                    type="button"
                    onClick={() =>
                      form.setValue(
                        "accounts",
                        accountList.filter((_, j) => j !== i),
                        { shouldValidate: true },
                      )
                    }
                  >
                    Xóa
                  </button>
                </li>
              ))}
            </ul>
            {form.formState.errors.accounts ? (
              <p style={{ color: "#B52E2E" }}>Danh sách tài khoản chưa hợp lệ</p>
            ) : null}
          </div>

          <div style={{ display: "flex", gap: 8 }}>
            <label>
              Track đọc{" "}
              <select data-testid="platform-track-read" {...form.register("track_read")}>
                <option value="READY">READY</option>
                <option value="DEGRADED">DEGRADED</option>
                <option value="UNKNOWN">UNKNOWN</option>
              </select>
            </label>
            <label>
              Track đăng{" "}
              <select data-testid="platform-track-publish" {...form.register("track_publish")}>
                <option value="READY">READY</option>
                <option value="DEGRADED">DEGRADED</option>
                <option value="BLOCKED">BLOCKED</option>
                <option value="UNKNOWN">UNKNOWN</option>
              </select>
            </label>
          </div>

          <div>
            <b>Capabilities ({capsField.fields.length}/6)</b>{" "}
            <button
              type="button"
              data-testid="platform-cap-add"
              onClick={() =>
                capsField.append({
                  key: "list",
                  status: "SUPPORTED",
                  runtime: "fixture",
                  input: "",
                  output: "",
                  evidence: "",
                })
              }
            >
              Thêm capability
            </button>
            {capsField.fields.map((f, i) => (
              <div
                key={f.id}
                data-testid={`platform-cap-${i}`}
                style={{ border: "1px solid #eee", borderRadius: 8, padding: 8, marginTop: 8 }}
              >
                <select {...form.register(`capabilities.${i}.key` as const)}>
                  {CAP_KEY_OPTIONS.map((k) => (
                    <option key={k} value={k}>
                      {k}
                    </option>
                  ))}
                </select>{" "}
                <select {...form.register(`capabilities.${i}.status` as const)}>
                  {CAP_STATUS_OPTIONS.map((k) => (
                    <option key={k} value={k}>
                      {k}
                    </option>
                  ))}
                </select>{" "}
                <button type="button" onClick={() => capsField.remove(i)}>
                  Xóa
                </button>
                <br />
                <input
                  {...form.register(`capabilities.${i}.runtime` as const)}
                  placeholder="runtime"
                />{" "}
                <input {...form.register(`capabilities.${i}.input` as const)} placeholder="input" />{" "}
                <input
                  {...form.register(`capabilities.${i}.output` as const)}
                  placeholder="output"
                />{" "}
                <input
                  {...form.register(`capabilities.${i}.evidence` as const)}
                  placeholder="evidence"
                />
              </div>
            ))}
          </div>

          <button data-testid="platform-submit" type="submit" disabled={upsert.isPending}>
            {upsert.isPending ? "Đang lưu…" : "Đăng ký mới / Cập nhật"}
          </button>
        </form>

        <form
          data-testid="clone-form"
          onSubmit={(e) => {
            e.preventDefault();
            const parsed = platformCloneSchema.safeParse({ new_id: cloneId });
            if (!parsed.success) {
              setMsg(parsed.error.issues[0]?.message ?? "new_id chưa hợp lệ");
              return;
            }
            const first = data?.platforms?.[0];
            if (!first) {
              setMsg("Chưa có platform để nhân bản");
              return;
            }
            clone.mutate(
              { id: String(first.id), new_id: parsed.data.new_id },
              {
                onSuccess: (r) => setMsg(`Đã nhân bản — registry v${r.version}.`),
                onError: (e2) => setMsg(`Nhân bản thất bại: ${(e2 as Error).message}`),
              },
            );
          }}
          style={{ display: "flex", gap: 8, marginTop: 12, alignItems: "center" }}
        >
          <input
            data-testid="clone-new-id"
            placeholder="new_id nhân bản (để trống = auto)"
            value={cloneId}
            onChange={(e) => setCloneId(e.target.value)}
          />
          <button data-testid="clone-submit" type="submit">
            Nhân bản platform đầu tiên
          </button>
        </form>

        <form
          data-testid="rollback-form"
          onSubmit={rollbackForm.handleSubmit((v) =>
            rollback.mutate(v, {
              onSuccess: (r) => setMsg(`Đã rollback registry về v${r.version} (giữ task cũ).`),
              onError: (e) => setMsg(`Rollback thất bại: ${(e as Error).message}`),
            }),
          )}
          style={{ display: "flex", gap: 8, marginTop: 12, alignItems: "center" }}
        >
          <input
            data-testid="rollback-version"
            type="number"
            {...rollbackForm.register("version")}
            style={{ width: 200 }}
          />
          <button data-testid="rollback-submit" type="submit">
            Rollback (giữ task cũ)
          </button>
        </form>
        {rollbackForm.formState.errors.version ? (
          <p style={{ color: "#B52E2E" }}>{rollbackForm.formState.errors.version.message}</p>
        ) : null}
      </section>

      {(data?.platforms ?? []).map((p) => (
        <section
          key={String(p.id)}
          data-testid={`platform-${String(p.id)}`}
          style={{ margin: "16px 0", padding: 16, border: "1px solid #dadce0", borderRadius: 8 }}
        >
          <h2>
            {String(p.name)} <small>({String(p.id)} · v{String(p.version)})</small>
          </h2>
          <p style={{ display: "flex", gap: 16 }}>
            <span>Đọc: {badge(String(p.tracks.read))}</span>
            <span>Đăng: {badge(String(p.tracks.publish))}</span>
          </p>
          <p style={{ color: "#5f6368" }}>{String(p.runtime)}</p>
          <p>Tài khoản: {(p.accounts ?? []).join(" · ") || "—"}</p>

          <h3>Đọc (read-only)</h3>
          <table cellPadding={6} style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr>
                <th>Capability</th>
                <th>Trạng thái</th>
                <th>Runtime</th>
                <th>In/Out</th>
                <th>Bằng chứng</th>
              </tr>
            </thead>
            <tbody>
              {READ_CAPS.map((c) => (
                <tr key={c} style={{ borderTop: "1px solid #eee" }}>
                  <td>
                    <b>{c}</b>
                  </td>
                  <td>{badge(String(p.capabilities[c]?.status ?? "?"))}</td>
                  <td>{String(p.capabilities[c]?.runtime ?? "")}</td>
                  <td>
                    {String(p.capabilities[c]?.input ?? "")} →{" "}
                    {String(p.capabilities[c]?.output ?? "")}
                  </td>
                  <td>
                    <small>{String(p.capabilities[c]?.evidence ?? "")}</small>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <h3>Đăng (side-effect)</h3>
          <table cellPadding={6} style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr>
                <th>Capability</th>
                <th>Trạng thái</th>
                <th>Runtime</th>
                <th>In/Out</th>
                <th>Bằng chứng</th>
              </tr>
            </thead>
            <tbody>
              {PUB_CAPS.map((c) => (
                <tr key={c} style={{ borderTop: "1px solid #eee" }}>
                  <td>
                    <b>{c}</b>
                  </td>
                  <td>{badge(String(p.capabilities[c]?.status ?? "?"))}</td>
                  <td>{String(p.capabilities[c]?.runtime ?? "")}</td>
                  <td>
                    {String(p.capabilities[c]?.input ?? "")} →{" "}
                    {String(p.capabilities[c]?.output ?? "")}
                  </td>
                  <td>
                    <small>{String(p.capabilities[c]?.evidence ?? "")}</small>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}

      <p style={{ color: "#5f6368" }}>
        Chi tiết ma trận đầy đủ: <code>docs/platform-matrix.md</code> · capabilities còn lại:{" "}
        {CAPS.join(", ")}
      </p>
    </MiroNav>
  );
}
