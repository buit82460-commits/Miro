import { api } from "@/lib/api/http";
import { RuntimeService } from "@/lib/services/runtime.service";
import type {
  MiroResourceServiceContract,
  MiroTaskServiceContract,
} from "../contracts/miroApi";

const PREFIX = "/api";

async function backendOk(): Promise<boolean> {
  try {
    await api.get(`${PREFIX}/tasks/recent?limit=1`);
    return true;
  } catch {
    return false;
  }
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
        route: `/tasks/${b.id}`,
      },
      trigger: "chat" as const,
      steps: [],
      currentOperation: String(b.status ?? ""),
      createdAt: b.created_at ?? new Date().toISOString(),
      updatedAt: b.updated_at ?? new Date().toISOString(),
    }));
  },
  async pauseTask() {},
  async resumeTask() {},
  async cancelTask(taskId: string) {
    await RuntimeService.stop(taskId);
  },
  async retryTask() {},
  async stopAllAutomatedTasks() {},
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
    return [];
  },
  async listWorkflows() {
    return [];
  },
  async listResearchProjects() {
    return [];
  },
  async listMediaAssets() {
    return [];
  },
  async listPublications() {
    return [];
  },
  async listKnowledgeDocs() {
    return [];
  },
  async resolveApproval(approvalId, decision) {
    void approvalId;
    void decision;
    throw new Error("Approval resolve via BE not wired yet");
  },
};

export async function submitInstructionToBackend(message: string) {
  const ok = await backendOk();
  if (!ok) return null;
  try {
    const out = await RuntimeService.runMessage(message, 0, "");
    return out;
  } catch {
    return null;
  }
}
