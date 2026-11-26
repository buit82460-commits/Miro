"use client";
import { MiroShell } from "@/components/miro-shell";
import { AiWorkspacePage } from "@/features/ai-workspace/AiWorkspacePage";

export default function AiWorkspacePageRoute() {
  return (
    <MiroShell>
      <AiWorkspacePage />
    </MiroShell>
  );
}
