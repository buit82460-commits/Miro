"use client";
import { MiroShell } from "@/components/miro-shell";
import { PublishingPage } from "@/features/publishing/PublishingPage";

export default function PublishingPageRoute() {
  return (
    <MiroShell>
      <PublishingPage />
    </MiroShell>
  );
}
