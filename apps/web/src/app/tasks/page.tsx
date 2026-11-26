"use client";
import { MiroShell } from "@/components/miro-shell";
import { TasksPage } from "@/features/tasks/TasksPage";

export default function TasksPageRoute() {
  return (
    <MiroShell>
      <TasksPage />
    </MiroShell>
  );
}
