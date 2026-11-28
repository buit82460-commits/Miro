import { RuntimeService } from "@/lib/services/runtime.service";
import type {
  MiroResourceServiceContract,
  MiroTaskServiceContract,
} from "../contracts/miroApi";

// BE base: http://127.0.0.1:8770 (BFF /api/* forward BE). Xem
// docs/integration/MIRO-BACKEND-API-CONTRACT.md §04 (TASK-01..14), §08 (W1/W2/W6).
// Nguyen tac cung: khong bia du lieu, khong fallback mock. BE chua co EP
// -> throw Error "BE chua ho tro", khong return [] cung nhu du lieu that.

function unsupported(feature: string): Error {
  return new Error(`BE chưa hỗ trợ: ${feature}`);
}

export const MiroBackendTasks: MiroTaskServiceContract = {
  async listTasks() {
    const recents = await RuntimeService.recent(50);
    return recents.map((b) => ({
      id: b.id,
      title: b.request_id || b.id,
      instruction: b.request_id || b.id,
      scenario: "tiktok_research" as const,
      status: (b.status as "queued" | "running" | "completed" | "failed") ?? "queued",
      priority: "medium" as const,
      progress: {
        mode: "indeterminate" as const,
        current: 0,
        total: null,
        unitLabel: "steps",
        stageLabel: String(b.status ?? ""),
      },
      resource: {
        kind: "browser" as const,
        id: b.id,
        label: b.id,
        route: `/tasks-live/${b.id}`,
      },
      trigger: "chat" as const,
      steps: [],
      currentOperation: String(b.status ?? ""),
      createdAt: b.created_at ?? new Date().toISOString(),
      updatedAt: b.updated_at ?? new Date().toISOString(),
    }));
  },
  async pauseTask() {
    throw unsupported("tạm dừng task (BE không có endpoint pause tương ứng)");
  },
  async resumeTask() {
    throw unsupported("tiếp tục task qua contract này (gọi BE resume cần taskId — dùng RuntimeService.resume)");
  },
  async cancelTask(taskId: string) {
    await RuntimeService.stop(taskId);
  },
  async retryTask() {
    throw unsupported("thử lại task qua contract này (gọi BE restart cần taskId — dùng RuntimeService.restart)");
  },
  async stopAllAutomatedTasks() {
    throw unsupported("dừng toàn bộ task (BE không có endpoint tương ứng)");
  },
};

export const MiroBackendResources: MiroResourceServiceContract = {
  async listProfiles() {
    const st = await RuntimeService.status().catch(() => null);
    const tabs = st?.bridge?.tabs ?? [];
    const nowIso = new Date().toISOString();
    return tabs.map((t, i) => ({
      id: `profile-live-${i}`,
      name: String(t.browser ?? "browser"),
      alias: String(t.browser ?? "browser"),
      connectionState: "connected" as const,
      identityVerification: "unverified" as const,
      tabs: [
        {
          id: `tab-${i}`,
          title: String(t.title ?? ""),
          url: String(t.url ?? ""),
          active: true,
          pageSummary: String(t.title ?? ""),
        },
      ],
      permissions: [],
      lastActivity: nowIso,
      observations: [],
    }));
  },
  async listSchedules() {
    throw unsupported("danh sách schedules (BE chỉ có POST /schedule/ensure + GET /schedule/day-plan)");
  },
  async listWorkflows() {
    throw unsupported("danh sách workflows (BE không có endpoint tương ứng)");
  },
  async listResearchProjects() {
    throw unsupported("danh sách research projects (BE chỉ có POST /research/* theo query)");
  },
  async listMediaAssets() {
    throw unsupported("danh sách media assets (BE không có endpoint tương ứng)");
  },
  async listPublications() {
    throw unsupported("danh sách publications (BE chỉ có GET /publications/{id} theo id)");
  },
  async listKnowledgeDocs() {
    throw unsupported("danh sách knowledge docs (BE không có endpoint tương ứng)");
  },
  async resolveApproval(approvalId, decision) {
    void approvalId;
    void decision;
    throw unsupported("resolve approval theo approvalId (BE duyệt theo task: POST /tasks/{id}/approve)");
  },
};

// W2 run-message: POST /tasks/run-message {message, tab_id, live_origin?, limit?}
// -> {ok, error, task_id, route, evidence}. tab_id=0 = autonomous.
// Thanh cong: tra ve out that. That bai/BE unreachable: THROW loi that,
// tuyet doi khong fallback mock engine.
export async function submitInstructionToBackend(message: string) {
  try {
    return await RuntimeService.runMessage(message, 0, "");
  } catch (e) {
    const { code, message: m, status } = RuntimeService.errMessage(e);
    if (status === undefined) {
      throw new Error(`Không nối được BE (http://127.0.0.1:8770 unreachable): ${m}`);
    }
    throw new Error(`BE lỗi (${status}${code ? `: ${code}` : ""}): ${m}`);
  }
}

// W1 poll: GET /tasks/recent, GET /tasks/{id}, GET /tasks/{id}/events,
// GET /tasks/runtime/status — du lieu that tu BE, khong mock.
export async function getBeRecentTasks(limit = 20) {
  return RuntimeService.recent(limit);
}

export async function getBeTask(taskId: string) {
  return RuntimeService.get(taskId);
}

export async function getBeTaskEvents(taskId: string) {
  return RuntimeService.events(taskId);
}

export async function getBeRuntimeStatus() {
  return RuntimeService.status();
}
