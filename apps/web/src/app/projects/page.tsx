"use client";
import { MiroShell } from "@/components/miro-shell";
import { ProjectsPage } from "@/features/projects/ProjectsPage";

export default function ProjectsPageRoute() {
  return (
    <MiroShell>
      <ProjectsPage />
    </MiroShell>
  );
}
