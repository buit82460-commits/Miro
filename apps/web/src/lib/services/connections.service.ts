import { api } from "@/lib/api/http";

// Connections BE thật — CONN-01..10 (§04 contract).
// - Credential CHỈ tham chiếu (vault:/ref:/env:/keychain:/oauth:/secret:),
//   không plaintext (BE từ chối CREDENTIAL_PLAINTEXT_DENIED).
// - Verify bằng VerifyEvidence từ tab thật đang mở (không mock).
// - CẤM bind POST /connections/mock/verify-tab ở UI production (chỉ test).

const PREFIX = "/api";

export type ConnectionAccount = {
  id: string;
  platform: string;
  account_id: string;
  display_name: string;
  // BE trả ref hoặc null (revoke xong = null). FE chỉ hiển thị ref, không nhập secret.
  credential_ref: string | null;
  profile_binding_id: string;
  browser_instance_id: string;
  is_default: boolean;
  status: string;
  verified_at: number | null;
  verified_target_id: string;
  evidence_sha: string;
};

export type AccountCreateInput = {
  platform: string;
  account_id: string;
  display_name?: string;
  credential_ref: string;
  profile_binding_id?: string;
  browser_instance_id?: string;
};

export type VerifyEvidenceInput = {
  tab_id: string;
  platform_id: string;
  profile_binding_id?: string;
  observed_account_id: string;
  target_id?: string;
  browser_instance_id?: string;
  window_id?: string;
  observed_account_id_after?: string;
  profile_path?: string;
  profile_path_after?: string;
};

export type DefaultResolution = {
  platform: string;
  account: Record<string, unknown> | null;
  source: "user_default" | "business_default" | "none";
};

const CRED_REF_PREFIXES = ["vault:", "ref:", "env:", "keychain:", "oauth:", "secret:"] as const;

// Guard client-side: chặn plaintext trước khi request tới BE.
export function assertCredentialRef(ref: string): string {
  const value = (ref || "").trim();
  if (!value) throw new Error("CREDENTIAL_REF_REQUIRED: nhập tham chiếu credential, không nhập secret thật.");
  const lowered = value.toLowerCase();
  if (!CRED_REF_PREFIXES.some((p) => lowered.startsWith(p))) {
    throw new Error(
      "CREDENTIAL_PLAINTEXT_DENIED: chỉ nhận tham chiếu (vault:/ref:/env:/keychain:/oauth:/secret:), không lưu secret thật.",
    );
  }
  return value;
}

export function isCredentialRef(ref: string): boolean {
  const lowered = (ref || "").trim().toLowerCase();
  return CRED_REF_PREFIXES.some((p) => lowered.startsWith(p));
}

export const ConnectionsService = {
  // GET /connections/accounts?platform=&status=
  list(platform = "", status = ""): Promise<ConnectionAccount[]> {
    const qs = new URLSearchParams();
    if (platform) qs.set("platform", platform);
    if (status) qs.set("status", status);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return api.get<ConnectionAccount[]>(`${PREFIX}/connections/accounts${suffix}`);
  },

  // GET /connections/accounts/{id}
  get(id: string): Promise<ConnectionAccount> {
    return api.get<ConnectionAccount>(`${PREFIX}/connections/accounts/${encodeURIComponent(id)}`);
  },

  // POST /connections/accounts
  create(input: AccountCreateInput): Promise<ConnectionAccount> {
    assertCredentialRef(input.credential_ref);
    return api.post<ConnectionAccount>(`${PREFIX}/connections/accounts`, {
      platform: input.platform,
      account_id: input.account_id,
      display_name: input.display_name ?? "",
      credential_ref: input.credential_ref.trim(),
      profile_binding_id: input.profile_binding_id ?? "",
      browser_instance_id: input.browser_instance_id ?? "",
    });
  },

  // POST /connections/accounts/{id}/verify — evidence từ tab thật đang mở.
  verify(id: string, evidence: VerifyEvidenceInput): Promise<ConnectionAccount> {
    return api.post<ConnectionAccount>(
      `${PREFIX}/connections/accounts/${encodeURIComponent(id)}/verify`,
      evidence,
    );
  },

  // POST /connections/accounts/{id}/pause
  pause(id: string): Promise<ConnectionAccount> {
    return api.post<ConnectionAccount>(`${PREFIX}/connections/accounts/${encodeURIComponent(id)}/pause`);
  },

  // POST /connections/accounts/{id}/reconnect {evidence, credential_ref?}
  reconnect(id: string, evidence: VerifyEvidenceInput, credentialRef = ""): Promise<ConnectionAccount> {
    if (credentialRef) assertCredentialRef(credentialRef);
    return api.post<ConnectionAccount>(
      `${PREFIX}/connections/accounts/${encodeURIComponent(id)}/reconnect`,
      { evidence, credential_ref: credentialRef },
    );
  },

  // POST /connections/accounts/{id}/revoke
  revoke(id: string): Promise<ConnectionAccount> {
    return api.post<ConnectionAccount>(`${PREFIX}/connections/accounts/${encodeURIComponent(id)}/revoke`);
  },

  // POST /connections/accounts/{id}/default
  setDefault(id: string): Promise<ConnectionAccount> {
    return api.post<ConnectionAccount>(`${PREFIX}/connections/accounts/${encodeURIComponent(id)}/default`);
  },

  // GET /connections/defaults/{platform}
  resolveDefault(platform: string): Promise<DefaultResolution> {
    return api.get<DefaultResolution>(`${PREFIX}/connections/defaults/${encodeURIComponent(platform)}`);
  },
};
