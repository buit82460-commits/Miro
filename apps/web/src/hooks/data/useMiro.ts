import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { QUERY_KEYS } from "@/lib/api/query-keys";
import {
  EditorService,
  LibraryService,
  PublishService,
  SettingsService,
  TasksService,
} from "@/lib/services/miro.service";

// ---- Khu vực Công việc: chat / task / duyệt / dừng ----
export const useTasks = () =>
  useQuery({ queryKey: QUERY_KEYS.taskList(), queryFn: () => TasksService.list() });

export const useSendChat = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: TasksService.sendChat,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.tasks });
    },
  });
};

export const useReviewTask = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...input }: { id: string; decision: "approve" | "reject" | "stop"; note?: string }) =>
      TasksService.review(id, { decision: input.decision, note: input.note ?? "" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.tasks });
    },
  });
};

export const useStopTask = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => TasksService.stop(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.tasks });
    },
  });
};

// ---- Khu vực Thư viện ----
export const useLibrary = () =>
  useQuery({ queryKey: QUERY_KEYS.libraryList(), queryFn: () => LibraryService.list() });

// ---- Khu vực Xuất bản: batch video×platform×account, receipt/đối soát ----
export const usePublishBatches = () =>
  useQuery({ queryKey: QUERY_KEYS.publishBatches(), queryFn: () => PublishService.batches() });

export const useSubmitBatch = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: PublishService.submit,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.publish });
    },
  });
};

export const useReceipts = () =>
  useQuery({ queryKey: QUERY_KEYS.receipts(), queryFn: () => PublishService.receipts() });

// ---- Khu vực Editor: BE sở hữu project qua Query key ----
export const useProject = (id?: string) =>
  useQuery({
    queryKey: QUERY_KEYS.projectDetail(id ?? ""),
    queryFn: () => EditorService.get(id!),
    enabled: !!id,
  });

export const useEditorCommand = (projectId: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { operation: Record<string, unknown>; expected_revision?: number }) =>
      EditorService.command(projectId, args.operation, args.expected_revision),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.projectDetail(projectId) });
    },
  });
};

export const useRender = (projectId: string) =>
  useMutation({
    mutationFn: (preview: boolean) => EditorService.render(projectId, preview),
  });

export const useApproveProject = (projectId: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => EditorService.approve(projectId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.projectDetail(projectId) });
    },
  });
};

// ---- Khu vực Cài đặt & kết nối ----
export const useConnections = () =>
  useQuery({ queryKey: QUERY_KEYS.connections, queryFn: () => SettingsService.connections() });

export const usePlatforms = () =>
  useQuery({ queryKey: QUERY_KEYS.platforms, queryFn: () => SettingsService.platforms() });

export const useUpsertPlatform = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: SettingsService.upsertPlatform,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.platforms });
    },
  });
};

export const useClonePlatform = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...input }: { id: string; new_id?: string }) =>
      SettingsService.clonePlatform(id, { new_id: input.new_id ?? "" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.platforms });
    },
  });
};

export const useRollbackRegistry = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: SettingsService.rollbackRegistry,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QUERY_KEYS.platforms });
    },
  });
};
