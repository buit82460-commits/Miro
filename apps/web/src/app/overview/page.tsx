"use client";
import { MiroShell } from "@/components/miro-shell";
import { OverviewPage } from "@/features/overview/OverviewPage";

export default function OverviewPageRoute() {
  return (
    <MiroShell>
      <OverviewPage />
    </MiroShell>
  );
}
