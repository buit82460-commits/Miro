import { api } from "@/lib/api/http";
import type {
  ChatSendInput,
  PublishBatchInput,
  Receipt,
  ReviewInput,
  SubtitleInput,
  TaskItem,
} from "@/lib/schemas/miro.schema";

export type FullProject = Record<string, unknown>;

// Tái dùng pattern dubtool ProjectsService: service mỏng, BE sở hữu state,
// FE chỉ invalidate Query key sau mutation.
const PREFIX = "/api";

export const TasksService = {
  list(): Promise<TaskItem[]> {
    return api.get<TaskItem[]>(`${PREFIX}/tasks`);
  },
  sendChat(input: ChatSendInput): Promise<TaskItem> {
    return api.post<TaskItem>(`${PREFIX}/tasks/chat`, input);
  },
  review(id: string, input: ReviewInput): Promise<TaskItem> {
    return api.post<TaskItem>(`${PREFIX}/tasks/${id}/review`, input);
  },
  stop(id: string): Promise<TaskItem> {
    return api.post<TaskItem>(`${PREFIX}/tasks/${id}/stop`);
  },
};

export const LibraryService = {
  list(): Promise<FullProject[]> {
    return api.get<FullProject[]>(`${PREFIX}/library`);
  },
};

export const PublishService = {
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

export const SettingsService = {
  connections(): Promise<Record<string, unknown>[]> {
    return api.get<Record<string, unknown>[]>(`${PREFIX}/settings/connections`);
  },
};
