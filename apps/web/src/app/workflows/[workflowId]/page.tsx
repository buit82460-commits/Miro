"use client";
import { MiroShell } from "@/components/miro-shell";
import { WorkflowsPage } from "@/features/workflows/WorkflowsPage";

export default function WorkflowsPageDetailRoute() {
  return (
    <MiroShell>
      <WorkflowsPage />
    </MiroShell>
  );
}
