import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { QUERY_KEYS } from "@/lib/api/query-keys";
import {
  ConnectionsService,
  type AccountCreateInput,
  type VerifyEvidenceInput,
} from "@/lib/services/connections.service";
import {
  PlatformsService,
  type CapabilityPatchInput,
} from "@/lib/services/platforms.service";
import type { PlatformUpsertInput, RollbackInput } from "@/lib/schemas/miro.schema";

// ---- Khu vực Kết nối (Connections — CONN-01..10) ----
// BE sở hữu state (RAM dict + JSON persist best-effort); FE invalidate Query key sau mutation.

export function useConnectionAccounts(platform = "", status = "") {
  return useQuery({
    queryKey: [...QUERY_KEYS.connections, "list", platform, status],
    queryFn: () => ConnectionsService.list(platform, status),
  });
}

// Alias theo §04: GET /connections/accounts (giữ tên cũ cho trang live).
export const useConnections = () => useConnectionAccounts();

export function useConnectionAccount(id?: string) {
  return useQuery({
    queryKey: QUERY_KEYS.connectionDetail(id ?? ""),
    queryFn: () => ConnectionsService.get(id!),
    enabled: !!id,
  });
}

export function useConnectionDefault(platform?: string) {
  return useQuery({
    queryKey: QUERY_KEYS.connectionDefault(platform ?? ""),
    queryFn: () => ConnectionsService.resolveDefault(platform!),
    enabled: !!platform,
  });
}

function useInvalidateConnections() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: QUERY_KEYS.connections });
  };
}

export function useCreateAccount() {
  const invalidate = useInvalidateConnections();
  return useMutation({
    mutationFn: (input: AccountCreateInput) => ConnectionsService.create(input),
    onSuccess: () => invalidate(),
  });
}

export function useVerifyAccount() {
  const invalidate = useInvalidateConnections();
  return useMutation({
    mutationFn: (args: { id: string; evidence: VerifyEvidenceInput }) =>
      ConnectionsService.verify(args.id, args.evidence),
    onSuccess: () => invalidate(),
  });
}

export function usePauseAccount() {
  const invalidate = useInvalidateConnections();
  return useMutation({
    mutationFn: (id: string) => ConnectionsService.pause(id),
    onSuccess: () => invalidate(),
  });
}

export function useReconnectAccount() {
  const invalidate = useInvalidateConnections();
  return useMutation({
    mutationFn: (args: { id: string; evidence: VerifyEvidenceInput; credentialRef?: string }) =>
      ConnectionsService.reconnect(args.id, args.evidence, args.credentialRef ?? ""),
    onSuccess: () => invalidate(),
  });
}

export function useRevokeAccount() {
  const invalidate = useInvalidateConnections();
  return useMutation({
    mutationFn: (id: string) => ConnectionsService.revoke(id),
    onSuccess: () => invalidate(),
  });
}

export function useSetDefaultAccount() {
  const invalidate = useInvalidateConnections();
  return useMutation({
    mutationFn: (id: string) => ConnectionsService.setDefault(id),
    onSuccess: () => invalidate(),
  });
}

// ---- Khu vực Nền tảng (Platforms — PLAT-01..06) ----
// Registry versioned; FE hiển thị matrix READ/PUBLISH riêng, BLOCKED/UNSUPPORTED đúng màu.

export function usePlatforms() {
  return useQuery({
    queryKey: QUERY_KEYS.platforms,
    queryFn: () => PlatformsService.list(),
  });
}

export function usePlatformsHistory() {
  return useQuery({
    queryKey: QUERY_KEYS.platformsHistory(),
    queryFn: () => PlatformsService.history(),
  });
}

function useInvalidatePlatforms() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: QUERY_KEYS.platforms });
  };
}

export function useUpsertPlatform() {
  const invalidate = useInvalidatePlatforms();
  return useMutation({
    mutationFn: (input: PlatformUpsertInput) => PlatformsService.upsert(input),
    onSuccess: () => invalidate(),
  });
}

export function useClonePlatform() {
  const invalidate = useInvalidatePlatforms();
  return useMutation({
    mutationFn: (args: { id: string; new_id?: string }) =>
      PlatformsService.clone(args.id, args.new_id ?? ""),
    onSuccess: () => invalidate(),
  });
}

export function usePatchCapability() {
  const invalidate = useInvalidatePlatforms();
  return useMutation({
    mutationFn: (args: { platformId: string; capability: string; patch: CapabilityPatchInput }) =>
      PlatformsService.patchCapability(args.platformId, args.capability, args.patch),
    onSuccess: () => invalidate(),
  });
}

export function useRollbackRegistry() {
  const invalidate = useInvalidatePlatforms();
  return useMutation({
    mutationFn: (input: RollbackInput) => PlatformsService.rollback(input.version),
    onSuccess: () => invalidate(),
  });
}
