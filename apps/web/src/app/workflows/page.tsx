"use client";
import { MiroShell } from "@/components/miro-shell";
import { WorkflowsPage } from "@/features/workflows/WorkflowsPage";

export default function WorkflowsPageRoute() {
  return (
    <MiroShell>
      <WorkflowsPage />
    </MiroShell>
  );
}
