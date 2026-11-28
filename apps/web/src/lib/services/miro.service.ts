import { api } from "@/lib/api/http";
import { ConnectionsService, type ConnectionAccount } from "@/lib/services/connections.service";
import { PlatformsService } from "@/lib/services/platforms.service";
import type {
  ChatSendInput,
  PlatformCloneInput,
  PlatformUpsertInput,
  PublishBatchInput,
  Receipt,
  Registry,
  ReviewInput,
  RollbackInput,
  SubtitleInput,
  TaskItem,
} from "@/lib/schemas/miro.schema";

export type FullProject = Record<string, unknown>;

// Tái dùng pattern dubtool ProjectsService: service mỏng, BE sở hữu state,
// FE chỉ invalidate Query key sau mutation.
const PREFIX = "/api";

export const TasksService = {
  // Canonical production: BE so huu state qua /tasks/recent + /run-message.
  // (Cu: GET /tasks, POST /tasks/chat, POST /tasks/{id}/review khong ton tai tren BE.)
  list(): Promise<TaskItem[]> {
    return api.get<TaskItem[]>(`${PREFIX}/tasks/recent?limit=20`);
  },
  sendChat(input: ChatSendInput): Promise<TaskItem> {
    return api.post<TaskItem>(`${PREFIX}/tasks/run-message`, {
      message: input.message,
      tab_id: 0,
    });
  },
  review(id: string, input: ReviewInput): Promise<TaskItem> {
    if (input.decision === "stop") {
      return api.post<TaskItem>(`${PREFIX}/tasks/${id}/stop`);
    }
    return api.post<TaskItem>(`${PREFIX}/tasks/${id}/approve`);
  },
  stop(id: string): Promise<TaskItem> {
    return api.post<TaskItem>(`${PREFIX}/tasks/${id}/stop`);
  },
};

export const LibraryService = {
  // Repair Slice 04: BE khong co /library rieng; Thu vien hien doc qua
  // threads history (BE so huu state). Trang hien thi unavailable ro rang
  // thay vi gia hoat dong khi BE mat ket noi.
  list(): Promise<FullProject[]> {
    return api.get<FullProject[]>(`${PREFIX}/library`);
  },
};

export const PublishService = {
  // BE dung POST /threads/publish (dry-run) + POST /publications;
  // khong co GET list batches. batches()/receipts() doc BFF tuong ung
  // (tra [] khi BE khong co du lieu, 502 khi BE down).
  batches(): Promise<FullProject[]> {
    return api.get<FullProject[]>(`${PREFIX}/publish/batches`);
  },
  submit(input: PublishBatchInput): Promise<FullProject> {
    return api.post<FullProject>(`${PREFIX}/publish/batches`, input);
  },
  receipts(): Promise<Receipt[]> {
    return api.get<Receipt[]>(`${PREFIX}/publish/receipts`);
  },
};

export const EditorService = {
  get(projectId: string): Promise<FullProject> {
    return api.get<FullProject>(`${PREFIX}/projects/${projectId}`);
  },
  // Thả mới gửi 1 command có revision (BE kiểm tra expected_revision).
  command(projectId: string, operation: Record<string, unknown>, expected_revision?: number): Promise<FullProject> {
    return api.post<FullProject>(`${PREFIX}/projects/${projectId}/operations`, {
      operation,
      expected_revision,
    });
  },
  updateSubtitle(projectId: string, clipId: string, patch: SubtitleInput): Promise<FullProject> {
    return api.put<FullProject>(`${PREFIX}/projects/${projectId}/subtitles/${clipId}`, patch);
  },
  render(projectId: string, preview: boolean): Promise<FullProject> {
    return api.post<FullProject>(`${PREFIX}/projects/${projectId}/renders`, { preview });
  },
  approve(projectId: string): Promise<FullProject> {
    return api.post<FullProject>(`${PREFIX}/projects/${projectId}/approve`);
  },
};

export const StudioService = {
  download(source: string, requestId: string, expectedRevision?: number) {
    return api.post<FullProject>(`${PREFIX}/studio/download`, {
      source,
      request_id: requestId,
      expected_revision: expectedRevision,
    });
  },
  translate(videoId: string, requestId: string, expectedRevision?: number) {
    return api.post<FullProject>(`${PREFIX}/studio/translate`, {
      video_id: videoId,
      request_id: requestId,
      expected_revision: expectedRevision,
    });
  },
  saveSubs(videoId: string, requestId: string, rows: unknown[], expectedRevision?: number) {
    return api.post<FullProject>(`${PREFIX}/studio/subtitles/save`, {
      video_id: videoId,
      request_id: requestId,
      rows,
      expected_revision: expectedRevision,
    });
  },
  loadSubs(videoId: string): Promise<{ video_id: string; segments: unknown[] }> {
    return api.get<{ video_id: string; segments: unknown[] }>(`${PREFIX}/studio/subtitles/${videoId}`);
  },
  render(videoId: string, requestId: string, expectedRevision?: number) {
    return api.post<FullProject>(`${PREFIX}/studio/render`, {
      video_id: videoId,
      request_id: requestId,
      expected_revision: expectedRevision,
    });
  },
  renderFinal(videoId: string, requestId: string, expectedRevision?: number) {
    return api.post<FullProject>(`${PREFIX}/studio/render/final`, {
      video_id: videoId,
      request_id: requestId,
      burn_subtitles: true,
      expected_revision: expectedRevision,
    });
  },
  importCaptions(videoId: string, requestId: string, srtText: string, expectedRevision?: number) {
    return api.post<FullProject>(`${PREFIX}/studio/captions/import`, {
      video_id: videoId,
      request_id: requestId,
      srt_text: srtText,
      expected_revision: expectedRevision,
    });
  },
  exportCaptions(videoId: string) {
    return api.get<unknown>(`${PREFIX}/studio/captions/export/${videoId}`);
  },
  plan(videoId: string, requestId: string, instruction: string, expectedRevision?: number) {
    return api.post<FullProject>(`${PREFIX}/studio/plan`, {
      video_id: videoId,
      request_id: requestId,
      instruction,
      expected_revision: expectedRevision,
    });
  },
  editorRender(videoId: string, requestId: string, plan: Record<string, unknown>, preview: boolean, expectedRevision?: number) {
    return api.post<FullProject>(`${PREFIX}/studio/editor/render`, {
      video_id: videoId,
      request_id: requestId,
      plan,
      preview,
      expected_revision: expectedRevision,
    });
  },
  editorRestore(videoId: string, requestId: string, expectedRevision?: number) {
    return api.post<FullProject>(`${PREFIX}/studio/editor/restore`, {
      video_id: videoId,
      request_id: requestId,
      expected_revision: expectedRevision,
    });
  },
  overlay(videoId: string, requestId: string, overlay: Record<string, unknown>, expectedRevision?: number) {
    return api.post<FullProject>(`${PREFIX}/studio/overlay`, {
      video_id: videoId,
      request_id: requestId,
      overlay,
      expected_revision: expectedRevision,
    });
  },
  revoice(videoId: string, requestId: string, segId: number, voice: string, expectedRevision?: number) {
    return api.post<FullProject>(`${PREFIX}/studio/revoice`, {
      video_id: videoId,
      request_id: requestId,
      seg_id: segId,
      voice,
      expected_revision: expectedRevision,
    });
  },
  timelineOp(videoId: string, requestId: string, op: Record<string, unknown>, expectedRevision?: number) {
    return api.post<FullProject>(`${PREFIX}/studio/timeline/op`, {
      video_id: videoId,
      request_id: requestId,
      op,
      expected_revision: expectedRevision,
    });
  },
  timelineUndo(videoId: string, requestId: string, expectedRevision?: number) {
    return api.post<FullProject>(`${PREFIX}/studio/timeline/undo`, {
      video_id: videoId,
      request_id: requestId,
      expected_revision: expectedRevision,
    });
  },
  timelineRedo(videoId: string, requestId: string, expectedRevision?: number) {
    return api.post<FullProject>(`${PREFIX}/studio/timeline/redo`, {
      video_id: videoId,
      request_id: requestId,
      expected_revision: expectedRevision,
    });
  },
  audioFx(videoId: string, requestId: string, effect: string, params: Record<string, unknown> = {}, expectedRevision?: number) {
    return api.post<FullProject>(`${PREFIX}/studio/audiofx/preview`, {
      video_id: videoId,
      request_id: requestId,
      effect,
      params,
      expected_revision: expectedRevision,
    });
  },
  beat(videoId: string, requestId: string, expectedRevision?: number) {
    return api.post<FullProject>(`${PREFIX}/studio/beat`, {
      video_id: videoId,
      request_id: requestId,
      expected_revision: expectedRevision,
    });
  },
  separate(videoId: string, requestId: string, expectedRevision?: number) {
    return api.post<FullProject>(`${PREFIX}/studio/separate`, {
      video_id: videoId,
      request_id: requestId,
      expected_revision: expectedRevision,
    });
  },
  track(videoId: string, requestId: string, roi: Record<string, unknown>, expectedRevision?: number) {
    return api.post<FullProject>(`${PREFIX}/studio/track`, {
      video_id: videoId,
      request_id: requestId,
      roi,
      expected_revision: expectedRevision,
    });
  },
  canvasSet(videoId: string, requestId: string, presetOrWh: unknown, expectedRevision?: number) {
    return api.post<FullProject>(`${PREFIX}/studio/canvas/set`, {
      video_id: videoId,
      request_id: requestId,
      preset_or_wh: presetOrWh,
      expected_revision: expectedRevision,
    });
  },
  exportPlan(videoId: string, requestId: string, exportCfg: Record<string, unknown> = {}, preview = false, expectedRevision?: number) {
    return api.post<FullProject>(`${PREFIX}/studio/export/plan`, {
      video_id: videoId,
      request_id: requestId,
      export: exportCfg,
      preview,
      expected_revision: expectedRevision,
    });
  },
  exportLadder(videoId: string, requestId: string, rungs: string[] = ["480p", "720p", "1080p"], expectedRevision?: number) {
    return api.post<FullProject>(`${PREFIX}/studio/export/ladder`, {
      video_id: videoId,
      request_id: requestId,
      rungs,
      expected_revision: expectedRevision,
    });
  },
  livePreview(videoId: string, requestId: string, expectedRevision?: number) {
    return api.post<FullProject>(`${PREFIX}/studio/preview/live`, {
      video_id: videoId,
      request_id: requestId,
      expected_revision: expectedRevision,
    });
  },
};

export const SettingsService = {
  // Chuẩn hóa qua services dùng chung (connections/platforms.service).
  // BE sở hữu state; FE chỉ đọc + invalidate Query key sau mutation.
  connections(platform = "", status = ""): Promise<ConnectionAccount[]> {
    return ConnectionsService.list(platform, status);
  },
  platforms(): Promise<Registry> {
    return PlatformsService.list();
  },
  upsertPlatform(input: PlatformUpsertInput): Promise<Registry> {
    return PlatformsService.upsert(input);
  },
  clonePlatform(id: string, input: PlatformCloneInput): Promise<Registry> {
    return PlatformsService.clone(id, input.new_id ?? "");
  },
  rollbackRegistry(input: RollbackInput): Promise<Registry> {
    return PlatformsService.rollback(input.version);
  },
};
