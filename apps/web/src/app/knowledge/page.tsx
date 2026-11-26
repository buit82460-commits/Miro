"use client";
import { MiroShell } from "@/components/miro-shell";
import { KnowledgePage } from "@/features/knowledge/KnowledgePage";

export default function KnowledgePageRoute() {
  return (
    <MiroShell>
      <KnowledgePage />
    </MiroShell>
  );
}
