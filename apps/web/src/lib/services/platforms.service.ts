import { api } from "@/lib/api/http";
import type { PlatformUpsertInput, Registry } from "@/lib/schemas/miro.schema";

// Platforms BE thật — PLAT-01..06 (§04 contract).
// Registry versioned: mọi mutation bump version, giữ history ≤20, rollback
// chỉ dời LIVE pointer (task cũ pin version không ảnh hưởng).
// tracks.read/publish do BE suy ra từ capabilities — FE hiển thị, không gửi.

const PREFIX = "/api";

export type CapabilityPatchInput = {
  status?: string;
  runtime?: string;
  input?: string;
  output?: string;
  evidence?: string;
};

export type PlatformsHistory = {
  history: { version: number }[];
};

// BE PlatformUpsert.capabilities là dict {key: {status,runtime,input,output,evidence}}.
// Form FE dùng mảng + track_read/track_publish → chuyển đổi ở đây.
function toCapabilitiesDict(input: PlatformUpsertInput): Record<string, unknown> {
  const dict: Record<string, unknown> = {};
  for (const cap of input.capabilities ?? []) {
    dict[cap.key] = {
      status: cap.status,
      runtime: cap.runtime,
      input: cap.input,
      output: cap.output,
      evidence: cap.evidence,
    };
  }
  return dict;
}

export const PlatformsService = {
  // GET /platforms
  list(): Promise<Registry> {
    return api.get<Registry>(`${PREFIX}/platforms`);
  },

  // GET /platforms/history
  history(): Promise<PlatformsHistory> {
    return api.get<PlatformsHistory>(`${PREFIX}/platforms/history`);
  },

  // POST /platforms
  upsert(input: PlatformUpsertInput): Promise<Registry> {
    return api.post<Registry>(`${PREFIX}/platforms`, {
      id: input.id,
      name: input.name,
      runtime: input.runtime,
      accounts: input.accounts ?? [],
      capabilities: toCapabilitiesDict(input),
    });
  },

  // POST /platforms/{id}/clone
  clone(id: string, newId: string): Promise<Registry> {
    return api.post<Registry>(`${PREFIX}/platforms/${encodeURIComponent(id)}/clone`, {
      new_id: newId,
    });
  },

  // PATCH /platforms/{id}/capabilities/{cap} (all-optional)
  patchCapability(
    platformId: string,
    capability: string,
    patch: CapabilityPatchInput,
  ): Promise<Registry> {
    return api.patch<Registry>(
      `${PREFIX}/platforms/${encodeURIComponent(platformId)}/capabilities/${encodeURIComponent(capability)}`,
      patch,
    );
  },

  // POST /platforms/rollback
  rollback(version: number): Promise<Registry> {
    return api.post<Registry>(`${PREFIX}/platforms/rollback`, { version });
  },
};
