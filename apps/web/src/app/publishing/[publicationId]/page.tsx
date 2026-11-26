"use client";
import { MiroShell } from "@/components/miro-shell";
import { PublishingPage } from "@/features/publishing/PublishingPage";

export default function PublishingPageDetailRoute() {
  return (
    <MiroShell>
      <PublishingPage />
    </MiroShell>
  );
}
